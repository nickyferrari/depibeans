"""Connects the durable journal to commissioned Linux FPGA/camera adapters.

The profile supplied by the lab must carry verified limits and ownership. The
shipped intake profile is deliberately uncommissioned and cannot actuate devices.
"""
import hashlib
import math
import time
import json
from pathlib import Path
from .camera_protocol import compile_camera,seconds,ChamberPins,expand
from .chamber_fpga import ChamberFPGA
from .avt_camera import capture
from .capture_outcomes import CaptureCancelled,CaptureSkipped

class ChamberAdapter:
    mode='hardware'
    def __init__(self,profile,data_directory):
        self.profile=profile;self.data_directory=Path(data_directory)
        self.fpga=None;self.protocols={};self.settings={}

    def validate(self,plan):
        p=self.profile
        limited=p.get('commissioned') is not True
        capabilities=p.get('verified_controls',{})
        if limited and not capabilities:raise ValueError('Chamber profile has not passed physical commissioning')
        research=bool(plan.get('execution'))
        config=p.get('experiment_execution',{})
        if research:
            if config.get('enabled') is not True:raise ValueError('Experiment execution is not enabled on this chamber')
            self._validate_experiment(plan,config)
        if limited and not research:
            if len(plan['events'])!=1 or plan['events'][0].get('delay_ms')!=0 or plan['events'][0].get('relative') is not True:
                raise ValueError('Only immediate manual controls have been verified')
            event=plan['events'][0]
            if event['kind']=='set' and (not capabilities.get('main_light') or event.get('command')!='intensity'):
                raise ValueError('Lighting channel has not been verified')
            if event['kind']=='capture':
                protocols=plan.get('protocols',[])
                approved=[p['camera'].get('preview_protocol')] if capabilities.get('snapshot') else []
                if capabilities.get('measuring_burst'):approved.append(p['camera'].get('measuring_burst',{}).get('fields'))
                if len(protocols)!=1 or protocols[0]['fields'] not in approved:
                    raise ValueError('Only an explicitly verified snapshot or measuring-burst protocol may run')
        if not p.get('device_name'):raise ValueError('FPGA device identity is required')
        limits=config.get('limits',p.get('limits',{})) if research else p.get('limits',{})
        self.limits=limits;self.research=research;self.config=config
        self.plan=plan;self.target_time=None;self.cancel=lambda:False
        pins=ChamberPins(**{k:tuple(v) if isinstance(v,list) else v for k,v in p['pins'].items()});pins.validate()
        for name,bounds in limits.items():
            if name not in {'intensity','FR','UVA','UVB'} or len(bounds)!=2 or not all(isinstance(x,(float,int)) and not isinstance(x,bool) and math.isfinite(x) for x in bounds) or not 0<=bounds[0]<=bounds[1]:raise ValueError('Invalid commissioned bounds')
        self.protocols={x['id']:x for x in plan.get('protocols',[])}
        if len(self.protocols)!=len(plan.get('protocols',[])):raise ValueError('Duplicate protocols')
        for event in plan['events']:
            if event['kind']=='set':
                name=event['command'];value=float(event['value'])
                if name not in limits:raise ValueError('Lighting channel unavailable: '+name)
                if not limits[name][0]<=value<=limits[name][1]:raise ValueError(f'{name} must be within {limits[name][0]}–{limits[name][1]} controller units')
            elif event['kind']=='capture':
                proto=self.protocols[event['protocol']]
                if proto['group'] not in {'*','0'} or not set(proto['sensors'])<=set(['*','0']):raise ValueError('Protocol targets a different chamber configuration')
                compile_camera(proto['fields'],pins=pins,clock_hz=p['expected_clock_hz'],terminal_mask=0x20)
                if research:
                    fields=proto['fields'];n=int(fields['NumberLoops'])
                    waveform=compile_camera(fields,pins=pins,clock_hz=p['expected_clock_hz'],terminal_mask=0x20)
                    if waveform['frame_count']>config['max_frames'] or waveform['duration_s']>config['max_capture_s']:raise ValueError('Acquisition exceeds chamber frame or duration limit')
                    ex=expand(fields,'Exposure',n,seconds)
                    if len(set(ex))!=1:raise ValueError('Camera exposure must be identical in every phase')
                    if any(v<config['min_interval_s'] for v in expand(fields,'FrameInterval',n,seconds)):raise ValueError('Frame interval must be at least 95 ms on this camera connection')
                    if any(v not in (0,1) for v in expand(fields,'MeasuringLight',n,int)):raise ValueError('Only measuring channel 1 is available')
                    if any(expand(fields,'AuxFastSwitch',n,int,0)):raise ValueError('Auxiliary channels are unavailable')
                    if any(k in fields for k in ('intensity','FR','UVA','UVB')):raise ValueError('Place light changes on the experiment timeline')
                    if not 1e-6<=ex[0]<=.1:raise ValueError('Exposure must be 1–100000 microseconds')
                for name in ('intensity','FR','UVA','UVB'):
                    if name in proto['fields']:
                        value=float(proto['fields'][name])
                        if name not in limits or not limits[name][0]<=value<=limits[name][1]:raise ValueError('Uncommissioned auxiliary setpoint')
            else:raise ValueError('Unsupported hardware event')
        self.pins=pins

    def _validate_experiment(self,plan,config):
        events=plan.get('events',[]);options=plan['execution']
        stop_light=options.get('on_stop_light',0)
        if isinstance(stop_light,bool) or not isinstance(stop_light,(int,float)) or not math.isfinite(stop_light) or not config['limits']['intensity'][0]<=stop_light<=config['limits']['intensity'][1]:raise ValueError('Stop light must be inside the main-light limit')
        if options.get('capture_failure','stop') not in ('stop','continue'):raise ValueError('Unknown capture failure policy')
        if not events or len(events)>10000:raise ValueError('Use 1–10000 events')
        if any(e.get('relative') is not True or type(e.get('delay_ms')) is not int or not 0<=e['delay_ms']<=366*86400000 for e in events):raise ValueError('Experiments use elapsed time, up to 366 days')
        ordered=sorted(events,key=lambda e:e['delay_ms'])
        if ordered[0]['kind']!='set' or ordered[0].get('command')!='intensity' or ordered[0]['delay_ms']!=0:raise ValueError('Set the initial main light at time zero')
        if ordered[-1]['kind']!='set' or ordered[-1].get('command')!='intensity':raise ValueError('Specify a final main-light setting')
        protocols={p['id']:p for p in plan.get('protocols',[])}
        reserved=[];light=None
        for e in ordered:
            if e['kind']=='set' and e.get('command')=='intensity':light=float(e['value'])
            if e['kind']=='capture':
                if protocols[e['protocol']].get('measurement_type') in ('dark-reference','background') and light!=0:raise ValueError('Dark reference and background need main light zero on the timeline')
                wave=compile_camera(protocols[e['protocol']]['fields'])
                start=e['delay_ms']/1000-config['prepare_s'];end=e['delay_ms']/1000+wave['duration_s']+config['cleanup_s']
                if start<0:raise ValueError('Place the first measurement at least '+str(config['prepare_s'])+' seconds after the start')
                for other in ordered:
                    if other is not e and other['kind']=='set' and start<other['delay_ms']/1000<=end:raise ValueError('A light change overlaps camera preparation/acquisition; separate it from the measurement')
                if any(start<=b and end>=a for a,b in reserved):raise ValueError('Measurements overlap camera preparation or cleanup; increase their spacing')
                reserved.append((start,end))

    def lead_seconds(self,event):
        return self.config.get('prepare_s',0) if self.research and event['kind']=='capture' else 0

    def recoverable_capture_error(self,exc):
        message=str(exc).lower()
        return bool(self.fpga and not self.fpga.fault and not any(x in message for x in ('restore','cleanup','persistence')) and any(x in message for x in ('incomplete camera frame','camera frame gap','frame completion timed out')))

    def _connect(self):
        if self.fpga is not None:return
        fpga=ChamberFPGA(self.profile['device_name'])
        try:
            clock=fpga.connect()
            if clock!=self.profile['expected_clock_hz']:raise RuntimeError('FPGA firmware clock mismatch')
            fpga.set_mask(self.profile['initial_mask'])
            self.fpga=fpga
        except Exception:fpga.close();raise

    def execute(self,event,job_id,sequence):
        self._connect()
        if event['kind']=='set':
            value=float(event['value']);name=event['command']
            result=self.fpga.set_light(name,value,limits=self.limits);self.settings[name]=value
            return result
        protocol=self.protocols[event['protocol']]
        if self.research and protocol.get('measurement_type') in ('dark-reference','background') and self.settings.get('intensity')!=0:raise ValueError('Dark reference and background require a preceding main-light setting of zero')
        fields=protocol['fields'];cam=self.profile['camera']
        burst=cam.get('measuring_burst',{}) if self.research or fields==cam.get('measuring_burst',{}).get('fields') else {}
        aux={k:float(fields[k]) for k in ('intensity','FR','UVA','UVB') if k in fields}
        if any(k not in self.settings for k in aux):raise RuntimeError('Cannot restore an unknown pre-capture light setting')
        original={k:self.settings[k] for k in aux}
        original_mask=self.fpga.last_commanded_mask
        self.fpga.set_mask(original_mask & ~(1<<self.pins.aux))
        try:
            for name,value in aux.items():self.fpga.set_light(name,value,limits=self.limits)
            waveform=compile_camera(fields,pins=self.pins,terminal_mask=self.fpga.last_commanded_mask,
                    clock_hz=self.fpga.clock_hz,pre=cam['pre'],post=cam['post'],dead_time_config=cam['dead_time'])
            folder=self.data_directory/hashlib.sha256(job_id.encode()).hexdigest()/f'capture-{sequence:06d}'
            timing={'intended_trigger':self.target_time,'actual_trigger':None,'trigger_lateness_s':None,'trigger_sent':False}
            self.last_capture_timing=timing;self.fpga.last_trigger_requested_at=None
            def await_trigger():
                if self.target_time is not None:
                    deadline=time.monotonic()+max(0,self.target_time-time.time())
                    while time.monotonic()<deadline:
                        if self.cancel():raise CaptureCancelled('Acquisition cancelled before trigger')
                        time.sleep(min(.05,max(0,deadline-time.monotonic())))
                if self.cancel():raise CaptureCancelled('Acquisition cancelled before trigger')
                if self.research and self.target_time is not None and time.time()-self.target_time>5:raise CaptureSkipped('Camera preparation missed the measurement time by more than 5 seconds; no trigger sent')
                actual=time.time()
                timing.update(intended_trigger=self.target_time,actual_trigger=actual,trigger_lateness_s=actual-self.target_time if self.target_time else None)
            def trigger():
                result=self.fpga.execute(waveform,before_trigger=await_trigger)
                actual=result['trigger_requested_at'];timing.update(trigger_sent=True,actual_trigger=actual,trigger_lateness_s=actual-self.target_time if self.target_time else None,timing_source='software FPGA start-command timestamp; physical edge unmeasured')
                return result
            result=capture(transport_path=cam['transport_path'],serial=cam['serial'],frames=waveform['frame_count'],
                    exposure_us=expand(fields,'Exposure',int(fields['NumberLoops']),seconds)[0]*1e6,destination=folder,
                    trigger=trigger,protocol_duration_s=waveform['duration_s'],
                    width=cam['width'],height=cam['height'],packet_size=cam['packet_size'],commissioning_authorized=True,
                    stream_bytes_per_second=burst.get('stream_bytes_per_second',cam.get('stream_bytes_per_second')),gain=burst.get('gain',cam.get('gain')),protocol_fields=fields)
            result.update(timing);result['protocol_fields']=fields;result['measurement_type']=self.protocols[event['protocol']].get('measurement_type','custom')
            result['settings']=dict(self.settings);result['protocol_id']=event['protocol']
            temp=folder/'metadata.tmp';temp.write_text(json.dumps(result,indent=2));temp.replace(folder/'metadata.json')
            return result
        except Exception as exc:
            stamp=getattr(self.fpga,'last_trigger_requested_at',None)
            if stamp is not None:timing.update(trigger_sent=True,actual_trigger=stamp,trigger_lateness_s=stamp-self.target_time if self.target_time else None)
            metadata=folder/'metadata.json'
            if metadata.exists():
                record=json.loads(metadata.read_text());record.update(timing)
                if isinstance(exc,(CaptureCancelled,CaptureSkipped)):record['state']='cancelled' if isinstance(exc,CaptureCancelled) else 'skipped'
                record.update(measurement_type=protocol.get('measurement_type','custom'),protocol_fields=fields,settings=dict(self.settings),error=str(exc))
                temp=folder/'metadata.tmp';temp.write_text(json.dumps(record,indent=2));temp.replace(metadata)
            raise
        finally:
            # Do not issue new commands after transport uncertainty; leave review required.
            if not self.fpga.fault:
                for name,value in original.items():self.fpga.set_light(name,value,limits=self.limits)
                self.fpga.set_mask((self.fpga.last_commanded_mask & ~(1<<self.pins.aux)) | (original_mask & (1<<self.pins.aux)))

    def stop_lighting(self,value):
        record={'requested':value,'physical_output_verified':False,'time':time.time()}
        if self.fpga is None:
            return {**record,'state':'not_sent','reason':'No FPGA connection was established'}
        if self.fpga.fault:
            return {**record,'state':'not_sent','reason':'FPGA state uncertain; physical intervention required'}
        try:
            result=self.fpga.set_light('intensity',value,limits=self.limits)
            self.settings['intensity']=value
            return {**record,'state':'completed','controller_result':result}
        except Exception as exc:return {**record,'state':'failed','error':str(exc)}

    def close(self):
        if self.fpga is not None:self.fpga.close();self.fpga=None
