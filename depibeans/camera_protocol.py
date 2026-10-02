"""Offline port of the deployed CameraProtocol/ProtocolEngine waveform builder.

Preserves the deployed source's dead-time units and aux-bit semantics explicitly.
An instrumented comparison is required before treating compiled pulses as approved.
"""
from dataclasses import dataclass, asdict
from decimal import Decimal
import re
from .lighting import integer

UNITS={'us':Decimal('0.000001'),'ms':Decimal('.001'),'s':Decimal(1),
       'min':Decimal(60),'h':Decimal(3600),'hr':Decimal(3600),'day':Decimal(86400)}

def seconds(value):
    match=re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(us|ms|s|min|hr|h|day)\s*',str(value))
    if not match:raise ValueError('A nonnegative duration with explicit units is required')
    return float(Decimal(match[1])*UNITS[match[2]])

@dataclass(frozen=True)
class ChamberPins:
    fast:int=5
    aux:int=17
    saturation:int=4
    measuring:tuple=(6,21,22,23)
    cameras:tuple=(7,8,9,10,11,12)

    def validate(self):
        pins=(self.fast,self.aux,self.saturation)+tuple(self.measuring)+tuple(self.cameras)
        for pin in pins:integer(pin,0,31,'pin')
        if len(set(pins))!=len(pins):raise ValueError('Pins overlap')


def expand(fields, key, count, convert, default=None):
    value=fields.get(key,default)
    if value is None:raise ValueError('Missing protocol field '+key)
    values=value if isinstance(value,(list,tuple)) else str(value).split(',')
    parsed=[convert(v) for v in values]
    if len(parsed)==1:return parsed*count
    if len(parsed)!=count:raise ValueError(key+' must have one entry or one per loop')
    return parsed


def flag(value):
    if str(value) not in {'0','1','False','True'}:raise ValueError('Expected binary flag')
    return str(value) in {'1','True'}


def compile_camera(fields, *, pins=ChamberPins(), terminal_mask=0x20,
                   clock_hz=50_000_000, pre='35us', post='35us', dead_time_config='0.0000025ms',
                   preserve_legacy_dead_time=True):
    pins.validate(); integer(terminal_mask,0,0xffffffff,'terminal mask')
    integer(clock_hz,1_000_000,200_000_000,'clock frequency')
    count=int(fields['NumberLoops']); integer(count,1,255,'number of loops')
    frames=expand(fields,'FramesPerLoop',count,int)
    measuring=expand(fields,'MeasuringLight',count,int)
    saturation=expand(fields,'SaturationFlash',count,flag)
    aux=expand(fields,'AuxFastSwitch',count,flag,'0')
    shutter=expand(fields,'ActinicShutter',count,flag,'1')
    exposure=expand(fields,'Exposure',count,seconds)
    interval=expand(fields,'FrameInterval',count,seconds)
    dead=seconds(dead_time_config)*(1000 if preserve_legacy_dead_time else 1)
    pre_s,post_s=seconds(pre),seconds(post)
    def mask(light,sat,aux_on,measure,trigger):
        m=terminal_mask
        for pin,on in [(pins.fast,light),(pins.saturation,sat)]+[(p,j+1==measure) for j,p in enumerate(pins.measuring)]+[(p,trigger) for p in pins.cameras]:
            m=(m | (1<<pin)) if on else (m & ~(1<<pin))
        # Java only sets aux when true; caller normally passes an aux-cleared baseline.
        if aux_on:m|=1<<pins.aux
        return m
    loops=[]
    for i in range(count):
        integer(frames[i],1,0xffffffff,'frames per loop'); integer(measuring[i],0,len(pins.measuring),'measuring-light index')
        durations=[interval[i],max(pre_s-dead,0),dead,exposure[i],post_s]
        masks=[mask(True,saturation[i],aux[i],0,False),mask(not shutter[i],False,False,0,False),
               mask(not shutter[i],False,False,0,True),mask(not shutter[i],False,False,measuring[i],True),
               mask(not shutter[i],False,False,0,False)]
        pulses=[]
        for m,d in zip(masks,durations):
            cycles=int(d*clock_hz)
            if not 4<=cycles<=0xffffffff:raise ValueError('Pulse duration outside FPGA range; compare legacy behavior before changing it')
            pulses.append({'bitmask':m,'seconds':d,'cycles':cycles})
        loops.append({'repetitions':frames[i],'pulses':pulses})
    return {'schema':'depibeans.camera-waveform/1','hardware_verified':False,'clock_hz':clock_hz,
            'terminal_mask':terminal_mask,'frame_count':sum(frames),'loops':loops,
            'duration_s':sum(l['repetitions']*sum(p['seconds'] for p in l['pulses']) for l in loops),
            'legacy_dead_time_semantics':preserve_legacy_dead_time}
