import unittest
from depibeans.lighting import zone_packet,all_zones_packet,intensity_packet,calibration_packet,i2c_waveform
from depibeans.calibration import load_points,dump_points,quadratic_fit

class LightingTests(unittest.TestCase):
    def test_legacy_packets(self):
        self.assertEqual(zone_packet(2,1,1024).wire_bytes,bytes.fromhex('04 01 04 00'))
        self.assertEqual(all_zones_packet(1,4095).wire_bytes,bytes.fromhex('02 07 0f ff'))
        self.assertEqual(intensity_packet(134).wire_bytes,bytes.fromhex('00 a1 43 06 00 00'))
        self.assertEqual(calibration_packet(1,2,[0,1,0]).wire_bytes,bytes.fromhex('02 40 02 00000000 3f800000 00000000'))
    def test_waveform_preserves_other_pins_and_terminal(self):
        packet=zone_packet(1,0,0)
        pulses,terminal=i2c_waveform(packet,clock_pin=1,data_pin=0,baseline_mask=0x80,terminal_mask=0xa3)
        self.assertEqual(len(pulses),6+27*len(packet.wire_bytes))
        self.assertTrue(all(p.bitmask&0x80 for p in pulses))
        self.assertEqual(terminal,0xa3)
        self.assertEqual([p.bitmask for p in pulses[:3]],[0x83,0x82,0x80])
    def test_invalid_address_zone_float(self):
        for action in [lambda:zone_packet(128,0,0),lambda:zone_packet(1,7,1),lambda:intensity_packet(float('nan')),lambda:intensity_packet(-1)]:
            with self.assertRaises(ValueError):action()
    def test_legacy_roundtrip(self):
        points=[(0,{1:(0,0,0)}),(134,{1:(100,200,300)})]
        self.assertEqual(load_points(dump_points(points)),points)
    def test_known_quadratic(self):
        fit=quadratic_fit([(x,2+3*x+0.5*x*x) for x in [0,100,500,1000]])
        for a,b in zip(fit['coefficients'],[2,3,0.5]):self.assertAlmostEqual(a,b,places=7)
        self.assertLess(fit['rmse'],1e-7)
    def test_degenerate_fit(self):
        with self.assertRaises(ValueError):quadratic_fit([(1,2),(1,3),(2,4)])

    def test_broadcast_raw_writes_need_opt_in(self):
        for action in [lambda:zone_packet(0,1,10),lambda:all_zones_packet(0,10),lambda:calibration_packet(0,1,[0,1,0])]:
            with self.assertRaises(ValueError):action()
        self.assertEqual(zone_packet(0,1,10,allow_broadcast=True).address,0)
    def test_malformed_calibration_has_consistent_error(self):
        for text in ['{}','null','{"calibration_data":[{}]}','{"calibration_data":[{"intensity":1,"settings":null}]}']:
            with self.assertRaises(ValueError):load_points(text)
    def test_calibration_preserves_intensity_number_type(self):
        import json
        doc='{"calibration_data":[{"intensity":134,"settings":[{"I2Caddress":1,"zones":[1,2,3]}]}]}'
        result=json.loads(dump_points(load_points(doc)))
        self.assertIs(type(result['calibration_data'][0]['intensity']),int)

    def test_full_java_waveform_golden_vector(self):
        import json
        from pathlib import Path
        expected=json.loads((Path(__file__).parent/'fixtures/legacy-zone-2-1-1024.json').read_text())
        pulses,terminal=i2c_waveform(zone_packet(2,1,1024),clock_pin=1,data_pin=0,baseline_mask=0,terminal_mask=35)
        self.assertEqual([[p.bitmask,p.duration_s] for p in pulses],expected)
        self.assertEqual(terminal,35)

if __name__=='__main__':unittest.main()
