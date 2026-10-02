"""Real Calibratron-compatible FPGA transport using the installed x64 driver.

HIF is a DWORD (32 bits even on x64). No output is written on connect.
Protocol/status constants come from the archived CBlasterOS.h.
"""
import ctypes as C
import csv
import io
import os
from pathlib import Path
import subprocess
import threading
import time
from .lighting import i2c_waveform, integer

IDLE={0x01,0x09,0xF1}
class HardwareError(RuntimeError):pass

def initialize_status(board):
    """One documented PING for a cold zero status, only when opening a connection.

    Never clear known errors, interrupt RUNNING, or retry uncertain commands.
    The caller owns the device lock; PING does not write output pins.
    """
    if board.status() == 0:
        board.command(0x09)
        if board.status() != 0x09:
            raise HardwareError('FPGA initialization did not acknowledge PING')
    board.require_idle()

class DeviceInfo(C.Structure):
    _fields_=[('name',C.c_char*64),('connection',C.c_char*261),('transport',C.c_uint32)]

def no_java_controller():
    result=subprocess.run(['tasklist','/FO','CSV','/NH'],capture_output=True,text=True,check=True,timeout=10,creationflags=0x08000000)
    if any(row and row[0].lower() in ('java.exe','javaw.exe') for row in csv.reader(io.StringIO(result.stdout))):
        raise HardwareError('Close Lighting Calibratron and other Java controllers before connecting DepiBeans.')

class Native:
    def __init__(self,path):
        if os.name!='nt' or C.sizeof(C.c_void_p)!=8:raise HardwareError('64-bit Windows Python is required')
        path=Path(path).resolve(strict=True)
        self.directory=os.add_dll_directory(str(path.parent))
        self.lib=C.CDLL(str(path))
        self.depp=C.CDLL(str(Path(os.environ['SystemRoot'])/'System32/depp.dll'))
        self.dmgr=C.CDLL(str(Path(os.environ['SystemRoot'])/'System32/dmgr.dll'))
        def bind(lib,name,args,result):
            fn=getattr(lib,name);fn.argtypes=args;fn.restype=result;return fn
        u=C.c_uint32;i=C.c_int32;b=C.c_ubyte
        self.enumerate=bind(self.dmgr,'DmgrEnumDevices',[C.POINTER(i)],i)
        self.info=bind(self.dmgr,'DmgrGetDvc',[i,C.POINTER(DeviceInfo)],i)
        self.free_enum=bind(self.dmgr,'DmgrFreeDvcEnum',[],i)
        self.open=bind(self.lib,'openChrisBlasterConnection',[C.c_char_p,C.POINTER(u)],C.c_bool)
        self.close=bind(self.lib,'closeChrisBlasterConnection',[u],C.c_bool)
        self.send=bind(self.lib,'sendCommandToChrisBlaster',[u,i,u,u,u,u,C.POINTER(i),C.POINTER(u)],C.c_bool)
        self.read=bind(self.depp,'DeppGetReg',[u,b,C.POINTER(b),i],i)
        self.error=bind(self.lib,'getErrorMessage',[C.c_char_p,i],None)
        self.timeout=bind(self.dmgr,'DmgrSetTransTimeout',[u,u],i)
    def devices(self):
        count=C.c_int32()
        if not self.enumerate(C.byref(count)):raise HardwareError('USB enumeration failed')
        try:
            rows=[]
            for index in range(count.value):
                d=DeviceInfo()
                if not self.info(index,C.byref(d)):raise HardwareError('USB device information unavailable')
                rows.append({'name':d.name.decode('ascii'),'connection':d.connection.decode('ascii'),'transport':d.transport})
            return rows
        finally:self.free_enum()
    def detail(self):
        buf=C.create_string_buffer(512);self.error(buf,len(buf));return buf.value.decode(errors='replace')

class LightingBoard:
    def __init__(self,native,device_name,guard=no_java_controller):
        self.native=native;self.name=device_name;self.guard=guard
        self.handle=C.c_uint32();self.fault=None;self.lock=threading.Lock();self.frequency=0
    def connect(self):
        self.guard()
        if self.handle.value:raise HardwareError('Already connected')
        devices=self.native.devices()
        matches=[d for d in devices if d['name']==self.name and d['transport'] & 1]
        if len(matches)!=1:raise HardwareError('The configured testbed USB board was not uniquely found')
        if not self.native.open(self.name.encode('ascii'),C.byref(self.handle)):
            self.handle.value=0;raise HardwareError(self.native.detail())
        try:
            if not self.native.timeout(self.handle,2000):raise HardwareError('Cannot configure USB timeout')
            self.fault=None
            initialize_status(self)
            self.frequency=self.command(0x02)
            if not 1000000<=self.frequency<=200000000:raise HardwareError('Unexpected FPGA clock frequency')
            # This testbed firmware rejects READ_CURRENT_BITMASK (0x33).
            # Clock/status are supported; do not invent output readback.
            return {'device':self.name,'clock_hz':self.frequency,'output_readback_available':False}
        except Exception:
            self.disconnect();raise
    def status(self):
        if not self.handle.value:raise HardwareError('Not connected')
        value=C.c_ubyte()
        if not self.native.read(self.handle,2,C.byref(value),0):raise HardwareError('USB status read failed: '+self.native.detail())
        return value.value
    def require_idle(self):
        if self.fault:raise HardwareError('Reconnect after inspection: '+self.fault)
        value=self.status()
        if value not in IDLE:raise HardwareError(f'FPGA is not idle (status 0x{value:02x})')
    def command(self,code,*parameters):
        if len(parameters)>4:raise ValueError('Too many parameters')
        params=list(parameters)+[0]*(4-len(parameters))
        for p in params:integer(p,0,0xffffffff,'FPGA parameter')
        status=C.c_int32();data=C.c_uint32()
        ok=self.native.send(self.handle,code,*params,C.byref(status),C.byref(data))
        allowed=IDLE|({0x0F} if code==0x12 else set())
        if not ok or status.value not in allowed:
            raise HardwareError(f'FPGA command 0x{code:02x} failed; status 0x{status.value:02x}. '+self.native.detail())
        return data.value
    def send_packet(self,packet):
        pulses,terminal=i2c_waveform(packet,clock_pin=1,data_pin=0,baseline_mask=0,terminal_mask=0x23)
        # Preserve legacy loop boundaries: start, one loop per byte, stop.
        loops=[pulses[:3]]+[pulses[3+i*27:3+(i+1)*27] for i in range(len(packet.wire_bytes))]+[pulses[-3:]]
        return self.execute(loops,terminal)
    def set_all_raw(self,value):
        # Actual Calibratron MainScreenController.updateZones broadcast sequence.
        from .lighting import zone_packet
        integer(value,0,4095,'raw output')
        result=None
        for zone in range(3):
            result=self.send_packet(zone_packet(0,zone,value,allow_broadcast=True))
        return result
    def execute(self,loops,terminal):
        if not 1<=len(loops)<=255 or any(not 1<=len(loop)<=255 for loop in loops):raise ValueError('Invalid FPGA protocol size')
        compiled=[]
        for loop in loops:
            items=[]
            for pulse in loop:
                cycles=int(pulse.duration_s*self.frequency)
                integer(cycles,4,0xffffffff,'duration cycles')
                integer(pulse.bitmask,0,0x73,'lighting bitmask')
                items.append((pulse.bitmask,cycles))
            compiled.append(items)
        with self.lock:
            self.guard();self.require_idle()
            try:
                self.command(0x11,1,len(compiled),max(map(len,compiled)))
                for index,loop in enumerate(compiled):
                    for mask,cycles in loop:self.command(0x22,1,index,mask,cycles)
                    self.command(0x21,1,index,1)
                self.command(0x31,1,terminal)
                self.command(0x12,1)
                deadline=time.monotonic()+sum(p.duration_s for loop in loops for p in loop)+3
                while True:
                    status=self.status()
                    if status in IDLE:break
                    if status!=0x0F:raise HardwareError(f'FPGA error status 0x{status:02x}')
                    if time.monotonic()>deadline:raise HardwareError('FPGA completion timed out; output is uncertain')
                    time.sleep(.01)
                return {'fpga_completed':True,'physical_output_verified':False}
            except Exception as exc:
                self.fault=str(exc);raise
    def disconnect(self):
        if self.handle.value:
            handle=self.handle.value;self.handle.value=0
            if not self.native.close(handle):raise HardwareError('USB close failed; inspect before reopening another controller')
