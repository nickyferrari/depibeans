"""Converted saved experiment. Compile only; no hardware access."""
from depibeans.scripting import Experiment
from depibeans.research_scripts import ScriptSession, js_add

def build():
    experiment = Experiment('Enterprise_(2024-10-16T23.43.17GMT-0400)')
    session = ScriptSession(experiment)
    def v_Capture10min(v_intensity):
        experiment.set('intensity', v_intensity)
        experiment.wait('10s')
        session.capture(v_fsfmp)
        experiment.wait('1min')
        session.capture(v_fsfmp)
        experiment.wait('40s')
        session.capture(v_fsfmp)
        experiment.wait('10s')
    def v_LightPotentialWithoutDark(v_intensity):
        v_Capture10min(v_intensity)
        v_Capture10min(2000)
        v_Capture10min(v_intensity)
    def v_FlatDay():
        experiment.wait_until(v_Dawn)
        session.capture(v_f0fm)
        experiment.wait('1min')
        v_h = 1
        while (v_h <= v_HoursPerDay):
            session.tick()
            v_LightPotentialWithoutDark(v_FlatInt)
            experiment.wait('30min')
            v_h += 1
        experiment.set('intensity', 0)
        experiment.wait('10min')
        session.capture(v_fmpp)
        experiment.end_section('+')
    def v_SinusoidalDay():
        v_CurrInt = 0
        session.capture(v_f0fm)
        experiment.wait('1min')
        v_ictr = 0
        while (v_ictr <= v_NumSin):
            session.tick()
            v_CurrInt = v_SinIntArray[v_ictr]
            v_LightPotentialWithoutDark(v_CurrInt)
            v_ictr += 1
        experiment.set('intensity', 0)
        experiment.wait('1min')
        session.capture(v_fmpp)
        experiment.end_section('+')
    v_HoursPerDay = 14
    v_Dawn = '8:59'
    v_Dusk = '23:00'
    v_FlatInt = 500
    v_SinIntArray = [51, 103, 155, 206, 255, 301, 345, 384, 418, 447, 470, 486, 497, 500, 500, 497, 486, 470, 447, 418, 384, 345, 301, 255, 206, 155, 103, 51]
    v_FluctIntArray = [78, 161, 246, 333, 420, 506, 588, 667, 739, 805, 862, 911, 949, 977, 994, 1000, 1000, 994, 977, 949, 911, 862, 805, 739, 667, 588, 506, 420, 333, 246, 161, 78]
    v_NumSin = ((2 * v_HoursPerDay) - 1)
    v_NumFluct = ((2 * v_HoursPerDay) - 1)
    v_fs = session.new_protocol('fs')
    v_fs.fields['NumberLoops'] = 4
    v_fs.fields['FramesPerLoop'] = [5]
    v_fs.fields['MeasuringLight'] = [1, 1, 1, 0]
    v_fs.fields['SaturationFlash'] = [0]
    v_fs.fields['Exposure'] = ['50us']
    v_fs.fields['FrameInterval'] = ['70ms']
    # Legacy setDelayCaptureBy was ignored; timing comes from the chamber profile.
    # Legacy setDelayPostCaptureBy was ignored; timing comes from the chamber profile.
    v_fs.analysis = 'fs'
    # Legacy upload_camera_protocol was already a no-op.
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
    experiment.end_section((-1))
    experiment.set('intensity', v_FlatInt)
    experiment.wait('1s')
    session.capture(v_fsfmp)
    experiment.wait('1min')
    experiment.set('intensity', 0)
    experiment.end_section(1)
    v_SinusoidalDay()
    return session.compile()

if __name__ == "__main__":
    import json
    print(json.dumps(build(), indent=2))
