"""Pure-Python helpers for converted historical experiment scripts.

No JavaScript runtime or hardware access. Preserve the original protocol
registration and JavaScript string concatenation used in wait durations.
"""
from dataclasses import dataclass, field
import math


def js_string(value):
    if isinstance(value,bool):return 'true' if value else 'false'
    if isinstance(value,float) and math.isfinite(value) and value.is_integer():return str(int(value))
    return str(value)


def js_add(left,right):
    if isinstance(left,str) or isinstance(right,str):return js_string(left)+js_string(right)
    return left+right


@dataclass
class ScriptProtocol:
    name:str
    fields:dict=field(default_factory=dict)
    analysis:str|None=None


class ScriptSession:
    def __init__(self,experiment):
        self.experiment=experiment
        self.protocols={}
        self.iterations=0

    def tick(self):
        self.iterations+=1
        if self.iterations>100000:raise ValueError('Converted script exceeded iteration limit')

    def new_protocol(self,name):
        if name in self.protocols:raise ValueError('Duplicate protocol '+name)
        protocol=ScriptProtocol(name)
        self.protocols[name]=protocol
        return protocol

    def capture(self,protocol):
        if self.protocols.get(protocol.name) is not protocol:raise ValueError('Unknown protocol')
        if protocol.name not in self.experiment.protocols:
            self.experiment.protocol(protocol.name,protocol.fields,analysis=protocol.analysis)
        self.experiment.capture(protocol.name)

    def compile(self):
        # Legacy compilation resolves final protocol definitions/analysis IDs.
        import copy
        for name,p in self.protocols.items():
            if name in self.experiment.protocols:
                self.experiment.protocols[name]['fields']=copy.deepcopy(p.fields)
                self.experiment.protocols[name]['analysis']=p.analysis or name
        for event in self.experiment.events:
            if event['kind']=='capture':event['analysis']=self.experiment.protocols[event['protocol']]['analysis']
        return self.experiment.compile()
