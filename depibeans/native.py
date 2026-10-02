"""Read-only ChrisBlaster library identification; does not initialize/open a board."""
from pathlib import Path
import ctypes
import os
import platform


def library_version(path):
    if platform.system()!='Windows':
        raise RuntimeError('This legacy DLL runs on Windows')
    if ctypes.sizeof(ctypes.c_void_p)!=8:
        raise RuntimeError('This probe requires 64-bit Python and the x64 DLL')
    path=Path(path).resolve(strict=True)
    if path.name!='ChrisBlasterAdvanced_x64.dll':
        raise ValueError('Select the original ChrisBlasterAdvanced_x64.dll')
    with os.add_dll_directory(str(path.parent)):
        library=ctypes.CDLL(str(path))
        call=library.CBgetVersion
        call.argtypes=[]
        call.restype=ctypes.c_int32
        version=call()
    return {'major':(version>>16)&255,'minor':(version>>8)&255,'build':version&255,
            'device_opened':False,'hardware_output_changed':False}
