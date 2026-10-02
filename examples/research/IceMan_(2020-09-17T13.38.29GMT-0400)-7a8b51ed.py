"""Converted saved experiment. Compile only; no hardware access."""
from depibeans.scripting import Experiment
from depibeans.research_scripts import ScriptSession, js_add

def build():
    experiment = Experiment('IceMan_(2020-09-17T13.38.29GMT-0400)')
    session = ScriptSession(experiment)
    v_Dawn = '6:00'
    v_Dusk = '22:00'
    v_GrowLight = 100
    v_day = 0
    while (v_day <= 17):
        session.tick()
        experiment.set('intensity', v_GrowLight)
        experiment.wait_until(v_Dusk)
        experiment.set('intensity', 0)
        experiment.wait_until(v_Dawn)
        v_day += 1
    return session.compile()

if __name__ == "__main__":
    import json
    print(json.dumps(build(), indent=2))
