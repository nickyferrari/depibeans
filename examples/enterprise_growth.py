"""Python translation of the executed growth path in the March 20, 2026 script.

No device access. Output is a plan to compare against the captured Timeline.xml.
Unused fluorescence helper definitions in the source do not affect this run.
"""
import json
from depibeans.scripting import Experiment

SIN=[39,80,123,167,210,253,294,333,370,402,431,455,475,489,497,500,500,497,489,475,455,431,402,370,333,294,253,210,167,123,80,39]
HIGH=[78,161,246,333,420,506,588,667,739,805,862,911,949,977,994,1000,1000,994,977,949,911,862,805,739,667,588,506,420,333,246,161,78]

def build():
    e=Experiment('Enterprise growth reference')
    e.set('intensity',500).wait_until('22:00').set('intensity',0)
    for values in [SIN]+[HIGH]*6:
        e.wait_until('5:59').wait('1min')
        for value in values:e.set('intensity',value).wait('30min')
        e.set('intensity',0).end_section()
    return e.compile()

if __name__=='__main__':print(json.dumps(build(),indent=2))
