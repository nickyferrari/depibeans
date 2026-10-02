"""Linux Adept bindings and bounded ChrisBlaster transport.

ABI from Digilent dpcdecl.h/dmgr.h/depp.h in the preserved native reference.
Enumeration does not open or initialize FPGA outputs. Physical commissioning
is still required before using this transport for chamber experiments.
"""
import ctypes as C
import fcntl
import hashlib
import os
from pathlib import Path
import struct
import threading
import time
from .hardware import DeviceInfo, HardwareError


def no_linux_java_controller():
    for p in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            command = p.read_bytes().replace(b'\0', b' ').lower()
        except (OSError, PermissionError):
            continue
        if b'java' in command and any(x in command for x in (b'phenomics', b'calibratron', b'chrisblaster')):
            raise HardwareError('A Java chamber controller is running; it must release the FPGA first')


def command_parameters(parameters, *, legacy_param2_msb=True):
    """Reproduce reference wire bytes, including its documented param2 quirk."""
    if len(parameters) > 4 or any(type(p) is not int or not 0 <= p <= 0xffffffff for p in parameters):
        raise ValueError('Expected up to four unsigned 32-bit parameters')
    padded = list(parameters) + [0] * (4 - len(parameters))
    data = bytearray(struct.pack('<4I', *padded))
    if legacy_param2_msb:
        data[7] = data[11]
    return bytes(data)


class RegisterTransport:
    """Testable register protocol. A failed/uncertain command is never retried."""
    def __init__(self, read, write, *, timeout=2, clock=time.monotonic, sleep=time.sleep):
        self.read, self.write = read, write
        self.timeout, self.clock, self.sleep = timeout, clock, sleep
        self.lock = threading.Lock()
        self.fault = None

    def _ready(self, deadline):
        while True:
            if self.clock() >= deadline:
                raise HardwareError('ChrisBlaster acknowledgement timeout; physical state is uncertain')
            swap = self.read(0)
            if swap == 0:
                return
            if swap != 1:
                raise HardwareError(f'Unexpected swap register: {swap}')
            self.sleep(.001)

    def command(self, code, *parameters, legacy_param2_msb=True):
        if type(code) is not int or not 0 <= code <= 255:
            raise ValueError('Command must be one byte')
        data = command_parameters(parameters, legacy_param2_msb=legacy_param2_msb)
        with self.lock:
            if self.fault:
                raise HardwareError('Transport faulted; inspect and reconnect: ' + self.fault)
            try:
                deadline = self.clock() + self.timeout
                self._ready(deadline)
                for offset, value in enumerate(data, 3):
                    self.write(offset, value)
                self.write(1, code)
                self.write(0, 1)
                self._ready(deadline)
                status = self.read(2)
                result = int.from_bytes(bytes(self.read(i) for i in range(19, 23)), 'little')
                return status, result
            except Exception as exc:
                self.fault = str(exc)
                raise


class LinuxNative:
    """Native-compatible facade usable by the existing LightingBoard.

    HIF/DWORD remain 32-bit on Linux x86_64. A per-device flock coordinates
    DepiBeans processes; a Java process guard covers known legacy controllers.
    Neither guard substitutes for physical ownership verification.
    """
    def __init__(self, directory='/usr/lib/digilent/adept'):
        if not Path('/proc').exists():
            raise HardwareError('Linux is required')
        self.dmgr = C.CDLL(str(Path(directory)/'libdmgr.so'), mode=C.RTLD_GLOBAL)
        self.depp = C.CDLL(str(Path(directory)/'libdepp.so'), mode=C.RTLD_GLOBAL)
        u, i, b = C.c_uint32, C.c_int32, C.c_ubyte
        def bind(lib, name, args, result=i):
            fn = getattr(lib, name); fn.argtypes=args; fn.restype=result
            return fn
        self.enumerate=bind(self.dmgr,'DmgrEnumDevices',[C.POINTER(i)])
        self.info=bind(self.dmgr,'DmgrGetDvc',[i,C.POINTER(DeviceInfo)])
        self.free_enum=bind(self.dmgr,'DmgrFreeDvcEnum',[])
        self._open=bind(self.dmgr,'DmgrOpen',[C.POINTER(u),C.c_char_p])
        self._close=bind(self.dmgr,'DmgrClose',[u])
        self._enable=bind(self.depp,'DeppEnable',[u])
        self._disable=bind(self.depp,'DeppDisable',[u])
        self.read=bind(self.depp,'DeppGetReg',[u,b,C.POINTER(b),i])
        self._write=bind(self.depp,'DeppPutReg',[u,b,b,i])
        self.timeout=bind(self.dmgr,'DmgrSetTransTimeout',[u,u])
        self._last_error=bind(self.dmgr,'DmgrGetLastError',[])
        self._version=bind(self.dmgr,'DmgrGetVersion',[C.c_char_p])
        self.handles={}
        self.last_error=''

    def detail(self):
        return self.last_error or f'Adept error {self._last_error()}'

    def version(self):
        text=C.create_string_buffer(256)
        if not self._version(text):raise HardwareError(self.detail())
        return text.value.decode(errors='replace')

    def devices(self):
        count=C.c_int32()
        if not self.enumerate(C.byref(count)):raise HardwareError(self.detail())
        try:
            if not 0 <= count.value <= 4096:raise HardwareError('Invalid device enumeration count')
            result=[]
            for index in range(count.value):
                d=DeviceInfo()
                if not self.info(index,C.byref(d)):raise HardwareError(self.detail())
                result.append({'name':d.name.decode(errors='replace'),'connection':d.connection.decode(errors='replace'),'transport':d.transport})
            return result
        finally:self.free_enum()

    def open(self, name, handle_pointer):
        no_linux_java_controller()
        lockdir=Path(os.environ.get('XDG_RUNTIME_DIR', f'/tmp/depibeans-{os.getuid()}'))/'depibeans'
        lockdir.mkdir(mode=0o700,parents=True,exist_ok=True)
        lockfile=(lockdir/(hashlib.sha256(name).hexdigest()+'.lock')).open('a+')
        try:
            fcntl.flock(lockfile,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            lockfile.close(); raise HardwareError('Another DepiBeans process owns this device')
        handle=C.c_uint32()
        try:
            if not self._open(C.byref(handle),name):raise HardwareError(self.detail())
            if not self.timeout(handle,2000):raise HardwareError(self.detail())
            if not self._enable(handle):raise HardwareError(self.detail())
            h=handle.value
            def read(reg):
                value=C.c_ubyte()
                if not self.read(h,reg,C.byref(value),0):raise HardwareError(self.detail())
                return value.value
            def write(reg,value):
                if not self._write(h,reg,value,0):raise HardwareError(self.detail())
            self.handles[h]=(lockfile,RegisterTransport(read,write))
            C.cast(handle_pointer,C.POINTER(C.c_uint32))[0]=h
            return True
        except Exception:
            if handle.value:self._close(handle)
            lockfile.close()
            raise

    def send(self, handle, code, p1, p2, p3, p4, status_pointer, data_pointer):
        h=handle.value if hasattr(handle,'value') else handle
        status,data=self.handles[h][1].command(code,p1,p2,p3,p4)
        C.cast(status_pointer,C.POINTER(C.c_int32))[0]=status
        C.cast(data_pointer,C.POINTER(C.c_uint32))[0]=data
        return True

    def close(self, handle):
        h=handle.value if hasattr(handle,'value') else handle
        lockfile,_=self.handles.pop(h)
        try:
            disabled=self._disable(h)
            closed=self._close(h)
            return bool(disabled and closed)
        finally:lockfile.close()
