"""Basement-only addressed SmartLight controls, using existing chamber profiles.

Addresses are firmware candidates, not discovered rails. No ACK or light readback.
This entry point extends the installed control desk without replacing it.
"""
from contextlib import contextmanager
import math
import sqlite3
import time
from . import control_app
from .chamber_fpga import ChamberFPGA
from .lighting import intensity_packet, i2c_waveform


class BasementDesk(control_app.ControlDesk):
    @contextmanager
    def _light_db(self):
        db = sqlite3.connect(self.data / 'manual-lights.sqlite3')
        db.row_factory = sqlite3.Row
        db.execute('CREATE TABLE IF NOT EXISTS commands (id TEXT PRIMARY KEY, address INTEGER, value REAL, actor TEXT, time REAL, state TEXT, error TEXT)')
        try:
            with db:
                yield db
        finally:
            db.close()

    def status(self):
        result = super().status()
        if result.get('chamber_id') not in ('depi-two', 'depi-five'):
            return result
        with self._light_db() as db:
            rows = [dict(row) for row in db.execute('SELECT * FROM commands ORDER BY time DESC LIMIT 500')]
        labels = self.workbench.setting('manual_rail_labels', {})
        # A legacy all-light command supersedes earlier addressed requests.
        last = result.get('last_commanded_light') or {}
        if last.get('command') == 'intensity' and last.get('time'):
            rows.append(dict(address=0, value=last['value'], time=last['time'], state='completed', actor='Existing light control'))
            rows.sort(key=lambda row: row['time'], reverse=True)
        result['manual_lights'] = dict(addresses=list(range(1, 27)), labels=labels,
                                      commands=rows, limits=result['limits']['intensity'],
                                      physical_output_verified=False)
        return result

    def _action(self, path, data):
        if path != '/api/light' or data.get('operation') not in ('rail', 'rail_label'):
            return super()._action(path, data)
        p = self.profile()
        if p.get('chamber_id') not in ('depi-two', 'depi-five'):
            raise ValueError('Manual rail controls are available only on DEPI 02 and 04')
        address = data.get('address')
        if type(address) is not int or not 0 <= address <= 26:
            raise ValueError('Choose broadcast 0 or a rail address from 1 to 26')
        if data['operation'] == 'rail_label':
            label = data.get('label')
            if address == 0 or not isinstance(label, str) or len(label) > 80:
                raise ValueError('Use a label up to 80 characters for an individual address')
            labels = self.workbench.setting('manual_rail_labels', {})
            labels[str(address)] = label.strip()
            self.workbench.set_setting('manual_rail_labels', labels)
            return {'saved': True}
        value = data.get('value')
        low, high = p['limits']['intensity']
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'Light level must be {low}–{high} controller units')
        if p.get('verified_controls', {}).get('main_light') is not True:
            raise ValueError('Main light control is not enabled')
        request_id = data.get('request_id')
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise ValueError('A unique request ID is required')
        if not self.run_lock.acquire(blocking=False):
            raise ValueError('Wait for the active experiment or command to finish')
        locked = False
        fpga = None
        try:
            locked = self.job_lock.acquire(blocking=False)
            if not locked or self.active or self.event_pending or self.live.status()['running']:
                raise ValueError('Wait for camera capture or active hardware work to finish')
            with self._light_db() as db:
                old = db.execute('SELECT * FROM commands WHERE id=?', (request_id,)).fetchone()
                if old:
                    if old['address'] != address or old['value'] != value:
                        raise ValueError('Request ID already used for a different command')
                    return dict(old)
                db.execute('INSERT INTO commands VALUES (?,?,?,?,?,?,?)',
                           (request_id, address, value, data.get('_actor', 'Local operator'), time.time(), 'pending', None))
            try:
                fpga = ChamberFPGA(p['device_name'])
                clock = fpga.connect()
                if clock != p['expected_clock_hz']:
                    raise ValueError('FPGA clock does not match the chamber profile')
                fpga.set_mask(p['initial_mask'])
                terminal = fpga.last_commanded_mask | 3
                fpga.set_mask(terminal)
                packet = intensity_packet(value, address=address)
                pulses, _ = i2c_waveform(packet, clock_pin=1, data_pin=0,
                                         baseline_mask=terminal, terminal_mask=terminal)
                chunks = [pulses[:3]] + [pulses[3+i*27:3+(i+1)*27] for i in range(len(packet.wire_bytes))] + [pulses[-3:]]
                wave = dict(clock_hz=clock, terminal_mask=terminal, loops=[dict(repetitions=1, pulses=[dict(bitmask=v.bitmask, cycles=int(v.duration_s*clock)) for v in chunk]) for chunk in chunks])
                result = fpga.execute(wave, slot=5)
                fpga.close()
                fpga = None
                with self._light_db() as db:
                    db.execute('UPDATE commands SET state=? WHERE id=?', ('completed', request_id))
                return dict(id=request_id, address=address, value=value, state='completed', **result)
            except Exception as exc:
                with self._light_db() as db:
                    db.execute('UPDATE commands SET state=?,error=? WHERE id=?', ('unknown', str(exc), request_id))
                raise
        finally:
            try:
                if fpga is not None:
                    fpga.close()
            finally:
                if locked:
                    self.job_lock.release()
                self.run_lock.release()


if __name__ == '__main__':
    control_app.ControlDesk = BasementDesk
    control_app.main()
