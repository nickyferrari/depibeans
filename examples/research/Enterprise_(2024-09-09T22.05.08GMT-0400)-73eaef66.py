"""Converted saved experiment. Compile only; no hardware access."""
from depibeans.scripting import Experiment
from depibeans.research_scripts import ScriptSession, js_add

def build():
    experiment = Experiment('Enterprise_(2024-09-09T22.05.08GMT-0400)')
    session = ScriptSession(experiment)
    def v_QuickFluctTest():
        experiment.wait_until(v_Dawn)
        session.capture(v_f0fm)
        experiment.wait('1min')
        v_ictr = 0
        while (v_ictr < v_HoursPerDay):
            session.tick()
            v_i = 0
            while (v_i < 19):
                session.tick()
                experiment.set('intensity', v_LowInt)
                experiment.wait('1min')
                experiment.wait('45s')
                experiment.wait('15s')
                experiment.set('intensity', v_HighInt)
                experiment.wait('1min')
                v_i += 1
            experiment.set('intensity', v_LowInt)
            experiment.wait('1min')
            experiment.wait('45s')
            session.capture(v_fsfmp)
            experiment.wait('15s')
            experiment.set('intensity', v_HighInt)
            experiment.wait('1min')
            v_ictr += 1
        experiment.set('intensity', v_LowInt)
        experiment.wait('3min')
        experiment.wait('40s')
        session.capture(v_fsfmp)
        experiment.wait('20s')
        experiment.set('intensity', 0)
        experiment.wait('5min')
        session.capture(v_fmpp)
        experiment.wait('20s')
    def v_QuickFluctTest1HrExtension():
        experiment.wait_until(v_Dawn)
        session.capture(v_f0fm)
        experiment.wait('1min')
        v_ictr = 0
        while (v_ictr < 17):
            session.tick()
            v_i = 0
            while (v_i < 19):
                session.tick()
                experiment.set('intensity', v_LowInt)
                experiment.wait('1min')
                experiment.wait('45s')
                experiment.wait('15s')
                experiment.set('intensity', v_HighInt)
                experiment.wait('1min')
                v_i += 1
            experiment.set('intensity', v_LowInt)
            experiment.wait('1min')
            experiment.wait('45s')
            session.capture(v_fsfmp)
            experiment.wait('15s')
            experiment.set('intensity', v_HighInt)
            experiment.wait('1min')
            v_ictr += 1
        experiment.set('intensity', v_LowInt)
        experiment.wait('3min')
        experiment.wait('40s')
        session.capture(v_fsfmp)
        experiment.wait('20s')
        experiment.set('intensity', 0)
        experiment.wait('5min')
        session.capture(v_fmpp)
        experiment.wait('20s')
    def v_FlatLight_1DarkMeasurmentatEOD():
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
        experiment.wait('5min')
        session.capture(v_fmpp)
        experiment.wait('20s')
        experiment.set('intensity', 0)
    v_HoursPerDay = 16
    v_Dawn = '5:59'
    v_Dusk = '22:00'
    v_FlatInt = 100
    v_LowInt = 30
    v_HighInt = 1000
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
    experiment.end_section('-1')
    experiment.set('intensity', 0)
    experiment.wait('10s')
    session.capture(v_fsfmp)
    experiment.wait('1min')
    experiment.wait_until('1:00')
    experiment.set('intensity', 0)
    experiment.end_section('1')
    v_QuickFluctTest1HrExtension()
    v_QuickFluctTest1HrExtension()
    v_QuickFluctTest1HrExtension()
    v_QuickFluctTest1HrExtension()
    v_QuickFluctTest1HrExtension()
    v_FlatLight_1DarkMeasurmentatEOD()
    v_FlatLight_1DarkMeasurmentatEOD()
    experiment.set('intensity', 0)
    experiment.wait_until(v_Dawn)
    experiment.set('intensity', v_FlatInt)
    experiment.wait_until(v_Dusk)
    experiment.set('intensity', 0)
    experiment.wait_until(v_Dawn)
    experiment.set('intensity', v_FlatInt)
    return session.compile()

if __name__ == "__main__":
    import json
    print(json.dumps(build(), indent=2))
