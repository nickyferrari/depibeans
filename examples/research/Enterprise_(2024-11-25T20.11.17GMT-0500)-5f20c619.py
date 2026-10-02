"""Converted saved experiment. Compile only; no hardware access."""
from depibeans.scripting import Experiment
from depibeans.research_scripts import ScriptSession, js_add

def build():
    experiment = Experiment('Enterprise_(2024-11-25T20.11.17GMT-0500)')
    session = ScriptSession(experiment)
    def v_SinusoidalNPQtqEtDay():
        v_CurrInt = 0
        experiment.wait_until(v_Dawn)
        session.capture(v_f0fm)
        experiment.wait('1min')
        v_ictr = 0
        while (v_ictr <= v_NumSin):
            session.tick()
            v_CurrInt = v_SinIntArray[v_ictr]
            experiment.set('intensity', v_CurrInt)
            experiment.wait('25min')
            experiment.wait('53s')
            session.capture(v_fsfmp)
            experiment.wait('1min')
            experiment.set('intensity', 0)
            experiment.wait('1s')
            experiment.set('FR', 1000)
            experiment.wait('6s')
            experiment.set('FR', 0)
            experiment.wait('1s')
            session.capture(v_f0p)
            experiment.wait('1min')
            experiment.wait('22s')
            session.capture(v_fmpp)
            experiment.wait('45s')
            experiment.set('FR', 1000)
            experiment.wait('6s')
            experiment.set('FR', 0)
            experiment.wait('1s')
            session.capture(v_f0pp)
            experiment.wait('45s')
            v_ictr += 1
        experiment.set('intensity', 0)
        experiment.end_section('+')
    v_HoursPerDay = 14
    v_Dawn = '8:59'
    v_Dusk = '23:00'
    v_FlatInt = 500
    v_SinIntArray = [0, 10, 10, 15, 20, 30, 40, 50, 100, 200, 600, 200, 400, 200, 400, 600, 200, 400, 200, 400, 600, 400, 200, 100, 50, 20, 10, 0]
    v_NumSin = ((2 * v_HoursPerDay) - 1)
    v_f0fm = session.new_protocol('f0fm')
    v_f0fm.fields['NumberLoops'] = 6
    v_f0fm.fields['FramesPerLoop'] = [5, 5, 5, 5, 5, 5]
    v_f0fm.fields['MeasuringLight'] = [1, 1, 1, 0, 0, 0]
    v_f0fm.fields['SaturationFlash'] = [0, 1, 0, 0, 1, 0]
    v_f0fm.fields['Exposure'] = ['50us']
    v_f0fm.fields['FrameInterval'] = ['70ms', '70ms', '70ms', '70ms', '70ms', '70ms']
    # Legacy setDelayCaptureBy was ignored; timing comes from the chamber profile.
    # Legacy setDelayPostCaptureBy was ignored; timing comes from the chamber profile.
    v_f0fm.analysis = 'f0fm'
    # Legacy upload_camera_protocol was already a no-op.
    v_fsfmp = session.new_protocol('fsfmp')
    v_fsfmp.fields['NumberLoops'] = 6
    v_fsfmp.fields['FramesPerLoop'] = [5]
    v_fsfmp.fields['MeasuringLight'] = [1, 1, 1, 0, 0, 0]
    v_fsfmp.fields['SaturationFlash'] = [0, 1, 0, 0, 1, 0]
    v_fsfmp.fields['Exposure'] = ['50us']
    v_fsfmp.fields['FrameInterval'] = ['70ms']
    # Legacy setDelayCaptureBy was ignored; timing comes from the chamber profile.
    # Legacy setDelayPostCaptureBy was ignored; timing comes from the chamber profile.
    v_fsfmp.analysis = 'fsfmp'
    # Legacy upload_camera_protocol was already a no-op.
    v_fmpp = session.new_protocol('fmpp')
    v_fmpp.fields['NumberLoops'] = 6
    v_fmpp.fields['FramesPerLoop'] = [5, 5, 5, 5, 5, 5]
    v_fmpp.fields['MeasuringLight'] = [1, 1, 1, 0, 0, 0]
    v_fmpp.fields['SaturationFlash'] = [0, 1, 0, 0, 1, 0]
    v_fmpp.fields['Exposure'] = ['50us']
    v_fmpp.fields['FrameInterval'] = ['70ms']
    # Legacy setDelayCaptureBy was ignored; timing comes from the chamber profile.
    # Legacy setDelayPostCaptureBy was ignored; timing comes from the chamber profile.
    v_fmpp.analysis = 'fmpp'
    # Legacy upload_camera_protocol was already a no-op.
    v_f0p = session.new_protocol('f0p')
    v_f0p.fields['NumberLoops'] = 6
    v_f0p.fields['FramesPerLoop'] = [5]
    v_f0p.fields['MeasuringLight'] = [1, 1, 1, 0, 0, 0]
    v_f0p.fields['SaturationFlash'] = [0, 0, 0, 0, 0, 0]
    v_f0p.fields['Exposure'] = ['50us']
    v_f0p.fields['FrameInterval'] = ['70ms']
    # Legacy setDelayCaptureBy was ignored; timing comes from the chamber profile.
    # Legacy setDelayPostCaptureBy was ignored; timing comes from the chamber profile.
    v_f0p.analysis = 'f0p'
    # Legacy upload_camera_protocol was already a no-op.
    v_f0pp = session.new_protocol('f0pp')
    v_f0pp.fields['NumberLoops'] = 6
    v_f0pp.fields['FramesPerLoop'] = [5]
    v_f0pp.fields['MeasuringLight'] = [1, 1, 1, 0, 0, 0]
    v_f0pp.fields['SaturationFlash'] = [0, 0, 0, 0, 0, 0]
    v_f0pp.fields['Exposure'] = ['50us']
    v_f0pp.fields['FrameInterval'] = ['70ms']
    # Legacy setDelayCaptureBy was ignored; timing comes from the chamber profile.
    # Legacy setDelayPostCaptureBy was ignored; timing comes from the chamber profile.
    v_f0pp.analysis = 'f0pp'
    # Legacy upload_camera_protocol was already a no-op.
    experiment.set('intensity', v_FlatInt)
    experiment.wait('10s')
    session.capture(v_fsfmp)
    experiment.wait('2hr')
    experiment.wait('50min')
    experiment.set('intensity', 0)
    experiment.wait_until('6:00')
    experiment.wait('1min')
    experiment.end_section('1')
    v_currDay = 1
    while (v_currDay <= 2):
        session.tick()
        v_SinusoidalNPQtqEtDay()
        experiment.wait('1min')
        v_currDay += 1
    experiment.wait_until(v_Dawn)
    experiment.set('intensity', v_FlatInt)
    return session.compile()

if __name__ == "__main__":
    import json
    print(json.dumps(build(), indent=2))
