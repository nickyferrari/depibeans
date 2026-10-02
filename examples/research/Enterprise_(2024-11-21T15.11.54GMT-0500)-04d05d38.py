"""Converted saved experiment. Compile only; no hardware access."""
from depibeans.scripting import Experiment
from depibeans.research_scripts import ScriptSession, js_add

def build():
    experiment = Experiment('Enterprise_(2024-11-21T15.11.54GMT-0500)')
    session = ScriptSession(experiment)
    def v_FastNQPCycle(v_Intensity):
        experiment.set('intensity', v_Intensity)
        experiment.wait('15min')
        session.capture(v_fsfmp)
        experiment.wait('15s')
        session.capture(v_fsfmp)
        experiment.wait('15s')
        session.capture(v_fsfmp)
        experiment.wait('15s')
        session.capture(v_fsfmp)
        experiment.wait('15s')
        session.capture(v_fsfmp)
        experiment.wait('15s')
        session.capture(v_fsfmp)
        experiment.wait('15s')
        experiment.set('intensity', 2000)
        experiment.wait('5s')
        v_h = 1
        while (v_h <= 10):
            session.tick()
            session.capture(v_fsfmp)
            experiment.wait('15s')
            v_h += 1
        experiment.set('intensity', v_Intensity)
        experiment.wait('5s')
        session.capture(v_fsfmp)
        experiment.wait('15s')
        session.capture(v_fsfmp)
        experiment.wait('15s')
        session.capture(v_fsfmp)
        experiment.wait('15s')
        session.capture(v_fsfmp)
        experiment.wait('15s')
        session.capture(v_fsfmp)
        experiment.wait('30s')
        session.capture(v_fsfmp)
        experiment.wait('30s')
        session.capture(v_fsfmp)
        experiment.wait('30s')
        session.capture(v_fsfmp)
        experiment.wait('30s')
        session.capture(v_fsfmp)
        experiment.wait('30s')
        session.capture(v_fsfmp)
        experiment.wait('15s')
        experiment.set('intensity', 0)
        experiment.wait('1s')
        experiment.set('FR', 1000)
        experiment.wait('6s')
        experiment.set('FR', 0)
        session.capture(v_f0p)
        experiment.wait('15s')
    def v_FullFastNPQCycle():
        experiment.set('intensity', 0)
        experiment.wait('19min')
        experiment.wait('30s')
        session.capture(v_f0fm)
        experiment.wait('30s')
        v_FastNQPCycle(50)
        v_FastNQPCycle(100)
        v_FastNQPCycle(200)
    v_HoursPerDay = 14
    v_Dawn = '8:59'
    v_Dusk = '23:00'
    v_FlatInt = 500
    v_LowInt = 50
    v_SinIntArray = [51, 103, 155, 206, 255, 301, 345, 384, 418, 447, 470, 486, 497, 500, 500, 497, 486, 470, 447, 418, 384, 345, 301, 255, 206, 155, 103, 51]
    v_FluctIntArray = [78, 161, 246, 333, 420, 506, 588, 667, 739, 805, 862, 911, 949, 977, 994, 1000, 1000, 994, 977, 949, 911, 862, 805, 739, 667, 588, 506, 420, 333, 246, 161, 78]
    v_IntArray = [50, 100, 200, 400, 600, 1000]
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
    experiment.end_section((-1))
    experiment.set('intensity', 500)
    experiment.wait('1s')
    session.capture(v_fsfmp)
    experiment.wait('1min')
    experiment.wait_until('15:15')
    experiment.set('intensity', 500)
    experiment.end_section(1)
    experiment.wait('1min')
    experiment.set('intensity', 50)
    experiment.wait_until('15:45')
    v_FullFastNPQCycle()
    experiment.wait_until('17:15')
    v_FullFastNPQCycle()
    experiment.wait_until('18:45')
    v_FullFastNPQCycle()
    experiment.wait_until('20:15')
    v_FullFastNPQCycle()
    experiment.wait('2min')
    experiment.set('intensity', v_FlatInt)
    return session.compile()

if __name__ == "__main__":
    import json
    print(json.dumps(build(), indent=2))
