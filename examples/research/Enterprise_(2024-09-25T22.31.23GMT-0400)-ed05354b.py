"""Converted saved experiment. Compile only; no hardware access."""
from depibeans.scripting import Experiment
from depibeans.research_scripts import ScriptSession, js_add

def build():
    experiment = Experiment('Enterprise_(2024-09-25T22.31.23GMT-0400)')
    session = ScriptSession(experiment)
    v_Dawn = '9:00'
    v_Dusk = '23:00'
    v_GrowLight = 500
    v_day = 0
    while (v_day <= 17):
        session.tick()
        experiment.wait_until(v_Dawn)
        experiment.set('intensity', v_GrowLight)
        experiment.wait_until(v_Dusk)
        experiment.set('intensity', 0)
        v_day += 1
    return session.compile()

if __name__ == "__main__":
    import json
    print(json.dumps(build(), indent=2))
