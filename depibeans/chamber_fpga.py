"""Full waveform uploader for a commissioned chamber; no implicit connection."""
import ctypes as C
import threading
import time
from .hardware import HardwareError, IDLE, initialize_status
from .lighting import integer, intensity_packet, zone_packet, i2c_waveform
from .linux_adept import LinuxNative, no_linux_java_controller

class ChamberFPGA:
    def __init__(self,device_name,*,native=None):
        self.native=native;self.device_name=device_name;self.handle=C.c_uint32()
        self.clock_hz=None;self.last_commanded_mask=None;self.fault=None;self.lock=threading.RLock()

    def connect(self):
        no_linux_java_controller()
        if self.handle.value:raise HardwareError('Already connected')
        if self.native is None:self.native=LinuxNative()
        matches=[d for d in self.native.devices() if d['name']==self.device_name and d['transport']&1]
        if len(matches)!=1:raise HardwareError('Configured FPGA was not uniquely found')
        if not self.native.open(self.device_name.encode(),C.byref(self.handle)):raise HardwareError(self.native.detail())
        try:
            initialize_status(self);self.clock_hz=self.command(2)
            integer(self.clock_hz,1_000_000,200_000_000,'FPGA clock')
            return self.clock_hz
        except Exception:self.close();raise

    def status(self):
        if not self.handle.value:raise HardwareError('FPGA is not connected')
        value=C.c_ubyte()
        if not self.native.read(self.handle,2,C.byref(value),0):raise HardwareError(self.native.detail())
        return value.value

    def require_idle(self):
        if self.fault:raise HardwareError('FPGA state is uncertain: '+self.fault)
        if self.status() not in IDLE:raise HardwareError('FPGA is busy or faulted')

    def command(self,code,*args):
        if not self.handle.value:raise HardwareError('Not connected')
        args=list(args)+[0]*(4-len(args))
        if len(args)!=4:raise ValueError('Too many parameters')
        for p in args:integer(p,0,0xffffffff,'parameter')
        status=C.c_int32();value=C.c_uint32()
        try:
            if not self.native.send(self.handle,code,*args,C.byref(status),C.byref(value)):
                raise HardwareError(self.native.detail())
            if status.value not in IDLE|({15} if code==0x12 else set()):raise HardwareError(f'Command status {status.value:#x}')
            return value.value
        except Exception as exc:self.fault=str(exc);raise

    def set_mask(self,mask):
        integer(mask,0,0xffffffff,'mask')
        with self.lock:
            self.require_idle();self.command(0x32,mask);self.last_commanded_mask=mask

    def execute(self,waveform,*,slot=1,before_trigger=None):
        integer(slot,0,255,'protocol slot')
        if waveform['clock_hz']!=self.clock_hz:raise ValueError('Waveform clock does not match connected FPGA')
        loops=waveform['loops'];integer(len(loops),1,255,'loop count')
        integer(waveform['terminal_mask'],0,0xffffffff,'terminal mask')
        duration=0
        for loop in loops:
            integer(loop['repetitions'],1,0xffffffff,'repetitions');integer(len(loop['pulses']),1,255,'pulse count')
            for pulse in loop['pulses']:
                integer(pulse['bitmask'],0,0xffffffff,'bitmask');integer(pulse['cycles'],4,0xffffffff,'cycles')
                duration+=pulse['cycles']/self.clock_hz*loop['repetitions']
        if duration>3600:raise ValueError('Waveform exceeds one-hour bounded execution limit')
        with self.lock:
            self.require_idle()
            self.last_trigger_requested_at=None
            try:
                self.command(0x11,slot,len(loops),max(len(l['pulses']) for l in loops))
                for index,loop in enumerate(loops):
                    for p in loop['pulses']:self.command(0x22,slot,index,p['bitmask'],p['cycles'])
                    self.command(0x21,slot,index,loop['repetitions'])
                self.command(0x31,slot,waveform['terminal_mask'])
            except Exception as exc:self.fault=str(exc);raise
            # An operator cancellation is not a hardware fault. Release the uploaded slot.
            if before_trigger is not None:
                try:before_trigger()
                except Exception:
                    self.command(0x10,slot)
                    raise
            try:
                trigger_requested_at=time.time();self.last_trigger_requested_at=trigger_requested_at;self.command(0x12,slot)
                deadline=time.monotonic()+duration+5
                while True:
                    status=self.status()
                    if status in IDLE:break
                    if status!=15 or time.monotonic()>deadline:raise HardwareError('FPGA completion uncertain')
                    time.sleep(.005)
                self.command(0x10,slot)
                self.last_commanded_mask=waveform['terminal_mask']
                return {'fpga_completed':True,'physical_output_verified':False,'trigger_requested_at':trigger_requested_at}
            except Exception as exc:self.fault=str(exc);raise

    def set_light(self,command,value,*,limits):
        if command not in limits:raise ValueError('Uncommissioned lighting channel')
        low,high=limits[command]
        if isinstance(value,bool) or not low<=value<=high:raise ValueError('Outside commissioned range')
        if self.last_commanded_mask is None:raise HardwareError('Explicit baseline initialization is required')
        if command=='intensity':packet=intensity_packet(value)
        elif command in {'FR','UVA','UVB'}:
            packet=zone_packet(0x7f,{'FR':0,'UVA':1,'UVB':2}[command],int(value))
        else:raise ValueError('Unknown lighting channel')
        with self.lock:
            terminal=self.last_commanded_mask|3
            self.set_mask(terminal)
            pulses,_=i2c_waveform(packet,clock_pin=1,data_pin=0,baseline_mask=terminal,terminal_mask=terminal)
            loops=[pulses[:3]]+[pulses[3+i*27:3+(i+1)*27] for i in range(len(packet.wire_bytes))]+[pulses[-3:]]
            waveform={'clock_hz':self.clock_hz,'terminal_mask':terminal,
                      'loops':[{'repetitions':1,'pulses':[{'bitmask':p.bitmask,'cycles':int(p.duration_s*self.clock_hz)} for p in loop]} for loop in loops]}
            return self.execute(waveform,slot=5)

    def close(self):
        if self.handle.value:
            h=self.handle.value;self.handle.value=0
            if not self.native.close(h):raise HardwareError('FPGA close failed')
