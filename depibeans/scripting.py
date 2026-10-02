"""Python experiment-building API. Compiles plans; never touches hardware.

Use from trusted local Python scripts. This is not a sandbox for portal input.
The saved JavaScript scripts remain reference inputs, not executable Python.
"""
import copy
import math
import re
from .camera_protocol import seconds

class Experiment:
    def __init__(self, name):
        if not isinstance(name,str) or not name.strip():raise ValueError('Experiment name is required')
        self.name=name; self.delay=0; self.relative=True
        self.events=[]; self.sections={}; self.section_number=-(2**31);self.protocols={}

    def wait(self,duration):
        self.delay=int(self.delay+seconds(duration)*1000)
        return self

    def wait_until(self,time_of_day):
        match=re.fullmatch(r'(\d{1,2}):(\d{2})',time_of_day)
        if not match:raise ValueError('Use 24-hour HH:MM; legacy 12-hour parsing has a known ambiguity')
        hour,minute=map(int,match.groups())
        if hour>23 or minute>59:raise ValueError('Invalid time of day')
        target=(hour*60+minute)*60000;day=self.delay//86400000*86400000
        if self.delay-day>target:day+=86400000
        self.delay=day+target;self.relative=False
        return self

    def _unique_time(self):
        occupied={(e['relative'],e['delay_ms']) for e in self.events}
        occupied.update(self.sections.values())
        delay=self.delay
        while (self.relative,delay) in occupied:delay+=1
        return delay

    def _sections(self):
        if self.relative and not self.sections:
            self.section_number=-1;self.sections[-1]=(True,0)
        elif not self.relative and (not self.sections or self.sections[max(self.sections)][0]):
            if 0 in self.sections:raise ValueError('Conflicting absolute section zero')
            self.section_number=0;self.sections[0]=(False,self.delay)

    def _event(self,**values):
        delay=self._unique_time();self._sections()
        self.events.append(dict(values,sequence=len(self.events),delay_ms=delay,relative=self.relative))
        return self

    def set(self,command,value):
        if command not in {'intensity','FR','UVA','UVB'}:
            raise ValueError('Driver is not in this chamber profile: '+str(command))
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
            raise ValueError('Lighting value must be finite and nonnegative')
        return self._event(kind='set',command=command,value=str(value))

    def end_section(self,number='+'):
        if isinstance(number,str) and re.fullmatch(r'-?\d+',number):number=int(number)
        delay=self._unique_time()
        if number=='+':self.section_number=0 if self.section_number<0 else self.section_number+1
        elif type(number) is int and number!=-(2**31):self.section_number=number
        else:raise ValueError('Invalid section number')
        if self.section_number in self.sections:raise ValueError('Duplicate section')
        self.sections[self.section_number]=(self.relative,delay)
        return self

    def protocol(self,name,fields,*,analysis=None,group='*',sensors=('*',)):
        if not name or name in self.protocols:raise ValueError('Duplicate or empty protocol name')
        self.protocols[name]={'id':name,'analysis':analysis or name,'fields':copy.deepcopy(fields),'group':group,'sensors':list(sensors)}
        return name

    def capture(self,protocol):
        if protocol not in self.protocols:raise ValueError('Unknown protocol')
        return self._event(kind='capture',protocol=protocol,analysis=self.protocols[protocol]['analysis'])

    def compile(self):
        used={e['protocol'] for e in self.events if e['kind']=='capture'}
        return {'schema':'depibeans.experiment-plan/1','name':self.name,'hardware_execution_authorized':False,
                'events':copy.deepcopy(self.events),'protocols':[copy.deepcopy(p) for n,p in self.protocols.items() if n in used],
                'sections':[{'number':n,'relative':r,'delay_ms':d} for n,(r,d) in self.sections.items()]}
