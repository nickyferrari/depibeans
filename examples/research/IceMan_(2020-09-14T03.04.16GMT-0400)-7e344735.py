"""Converted saved experiment. Compile only; no hardware access."""
from depibeans.scripting import Experiment
from depibeans.research_scripts import ScriptSession, js_add

def build():
    experiment = Experiment('IceMan_(2020-09-14T03.04.16GMT-0400)')
    session = ScriptSession(experiment)
    def v_FlatDay():
        experiment.wait_until(v_Dawn)
        session.capture(v_f0fm)
        experiment.wait('1min')
        v_h = 1
        while (v_h <= v_HoursPerDay):
            session.tick()
            experiment.set('intensity', v_FlatInt)
            experiment.wait('59min')
            experiment.wait('30s')
            session.capture(v_fsfmp)
            experiment.wait('30s')
            v_h += 1
        experiment.set('intensity', 0)
        experiment.end_section('+')
    def v_SinusoidalDay700():
        v_CurrInt = 0
        experiment.wait_until(v_Dawn)
        session.capture(v_f0fm)
        experiment.wait('1min')
        v_ictr = 0
        while (v_ictr <= v_NumSin):
            session.tick()
            v_CurrInt = v_SinInt700Array[v_ictr]
            experiment.set('intensity', v_CurrInt)
            experiment.wait('29min')
            experiment.wait('30s')
            session.capture(v_fsfmp)
            experiment.wait('30s')
            v_ictr += 1
        experiment.set('intensity', 0)
        experiment.end_section('+')
    v_HoursPerDay = 16
    v_Dawn = '5:59'
    v_Dusk = '22:00'
    v_FlatInt = 100
    v_SinInt700Array = [55, 113, 172, 233, 294, 354, 412, 467, 517, 563, 604, 637, 664, 684, 696, 700, 700, 696, 684, 664, 637, 604, 563, 517, 467, 412, 354, 294, 233, 172, 113, 55]
    v_FluctIntArray = [78, 161, 246, 333, 420, 506, 588, 667, 739, 805, 862, 911, 949, 977, 994, 1000, 1000, 994, 977, 949, 911, 862, 805, 739, 667, 588, 506, 420, 333, 246, 161, 78]
    v_NumSin = ((2 * v_HoursPerDay) - 1)
    v_NumFluct = ((2 * v_HoursPerDay) - 1)
    v_f0fm = session.new_protocol('f0fm')
    v_f0fm.fields['NumberLoops'] = 6
    v_f0fm.fields['FramesPerLoop'] = [5, 5, 5, 5, 5, 5]
    v_f0fm.fields['MeasuringLight'] = [1, 1, 1, 0, 0, 0]
    v_f0fm.fields['SaturationFlash'] = [0, 1, 0, 0, 1, 0]
    v_f0fm.fields['Exposure'] = ['50us']
    v_f0fm.fields['FrameInterval'] = ['75ms']
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
    v_fsfmp.fields['FrameInterval'] = ['75ms']
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
    v_fmpp.fields['FrameInterval'] = ['75ms']
    # Legacy setDelayCaptureBy was ignored; timing comes from the chamber profile.
    # Legacy setDelayPostCaptureBy was ignored; timing comes from the chamber profile.
    v_fmpp.analysis = 'fmpp'
    # Legacy upload_camera_protocol was already a no-op.
    v_redref = session.new_protocol('redref')
    v_redref.fields['NumberLoops'] = 6
    v_redref.fields['FramesPerLoop'] = [5, 5, 5, 5, 5, 5]
    v_redref.fields['MeasuringLight'] = [0, 0, 0, 0, 0, 0]
    v_redref.fields['SaturationFlash'] = [0, 0, 0, 0, 0, 0]
    v_redref.fields['Exposure'] = ['50us']
    v_redref.fields['FrameInterval'] = ['70ms']
    # Legacy setDelayCaptureBy was ignored; timing comes from the chamber profile.
    # Legacy setDelayPostCaptureBy was ignored; timing comes from the chamber profile.
    v_redref.analysis = 'redref'
    # Legacy upload_camera_protocol was already a no-op.
    v_FlatDay()
    v_SinusoidalDay700()
    v_SinusoidalDay700()
    experiment.wait_until(v_Dawn)
    experiment.wait('2min')
    experiment.set('intensity', v_FlatInt)
    return session.compile()

if __name__ == "__main__":
    import json
    print(json.dumps(build(), indent=2))
