import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from depibeans.chamber_adapter import ChamberAdapter
from depibeans.scripting import Experiment
from depibeans.control_app import ControlDesk

PROFILE=Path(__file__).resolve().parents[1]/'profiles/enterprise-linux.manual.json'
class ManualControlsTests(unittest.TestCase):
    def setUp(self):self.p=json.loads(PROFILE.read_text())
    def snapshot(self):
        e=Experiment('Snapshot');e.protocol('snap',self.p['camera']['preview_protocol']);return e.capture('snap').compile()
    def test_only_bounded_immediate_actions_allowed(self):
        a=ChamberAdapter(self.p,'unused')
        a.validate(Experiment('Light').set('intensity',155).compile());a.validate(self.snapshot())
        for plan in [Experiment('high').set('intensity',156).compile(),Experiment('aux').set('FR',0).compile(),Experiment('scheduled').wait('1s').set('intensity',155).compile(),Experiment('multi').set('intensity',155).set('intensity',0).compile()]:
            with self.assertRaises(ValueError):a.validate(plan)
        plan=self.snapshot();plan['protocols'][0]['fields']['SaturationFlash']='1'
        with self.assertRaises(ValueError):a.validate(plan)
    def test_capture_preserves_main_gate_and_restores_aux_on_failure(self):
        class Board:
            clock_hz=50000000;fault=None;last_commanded_mask=35
            def set_mask(self,v):self.last_commanded_mask=v
            def execute(self,w,before_trigger=None):
                assert all(p['bitmask']&32 for l in w['loops'] for p in l['pulses'])
                if before_trigger:before_trigger()
                return {'trigger_requested_at':time.time()}
        for failure in (False,True):
            with tempfile.TemporaryDirectory() as d:
                a=ChamberAdapter(self.p,d);plan=self.snapshot();a.validate(plan);a.fpga=Board()
                def acquire(**kw):
                    self.assertEqual(kw['gain'],12);self.assertEqual(kw['stream_bytes_per_second'],5000000)
                    Path(kw['destination']).mkdir(parents=True)
                    kw['trigger']()
                    if failure:raise RuntimeError('Camera disconnected')
                    return {'state':'completed'}
                with patch('depibeans.chamber_adapter.capture',side_effect=acquire):
                    if failure:
                        with self.assertRaises(RuntimeError):a.execute(plan['events'][0],'snapshot',0)
                    else:a.execute(plan['events'][0],'snapshot',0)
                self.assertEqual(a.fpga.last_commanded_mask,35)
    def test_research_route_stays_closed(self):
        with tempfile.TemporaryDirectory() as d:
            desk=ControlDesk(d,PROFILE)
            with self.assertRaises(ValueError):desk.action('/api/run',{'experiment':next(iter(desk.plans)),'mode':'hardware','request_id':'no'})
            self.assertTrue(desk.status()['camera_capture_ready']);self.assertFalse(desk.status()['commissioned'])
