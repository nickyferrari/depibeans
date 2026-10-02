import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from depibeans.linux_adept import RegisterTransport, command_parameters
from depibeans.hardware import HardwareError
from depibeans.camera_protocol import compile_camera, ChamberPins
from depibeans.legacy_timeline import load_timeline
from depibeans.scripting import Experiment

class TransportTests(unittest.TestCase):
    def test_reference_register_sequence(self):
        regs={0:0,2:1,19:0x80,20:0xf0,21:0xfa,22:2};writes=[]
        def write(reg,value):
            writes.append((reg,value));regs[reg]=value
            if reg==0:regs[0]=0
        t=RegisterTransport(lambda reg:regs[reg],write)
        self.assertEqual(t.command(2),(1,50_000_000))
        self.assertEqual([reg for reg,_ in writes],list(range(3,19))+[1,0])
        self.assertNotIn(2,[reg for reg,_ in writes])
    def test_timeout_never_retries_uncertain_command(self):
        ticks=[0.0];writes=[]
        def sleep(value):ticks[0]+=value
        t=RegisterTransport(lambda reg:1,lambda r,v:writes.append((r,v)),timeout=.002,clock=lambda:ticks[0],sleep=sleep)
        with self.assertRaises(HardwareError):t.command(2)
        with self.assertRaises(HardwareError):t.command(2)
        self.assertEqual(writes,[])
    def test_reference_parameter_quirk_is_explicit(self):
        args=(0,0xAA000000,0xBB000000,0)
        self.assertEqual(command_parameters(args)[7],0xBB)
        self.assertEqual(command_parameters(args,legacy_param2_msb=False)[7],0xAA)
    def test_transport_rejects_bad_values(self):
        with self.assertRaises(ValueError):command_parameters([1<<32])
        with self.assertRaises(ValueError):command_parameters([True])

class WaveformTests(unittest.TestCase):
    def fields(self):return {'NumberLoops':'1','FramesPerLoop':'1','MeasuringLight':'1','SaturationFlash':'0','Exposure':'50us','FrameInterval':'70ms'}
    def test_single_frame_reference(self):
        p=compile_camera(self.fields(),terminal_mask=0x20)
        self.assertEqual(p['frame_count'],1)
        pulses=p['loops'][0]['pulses']
        self.assertEqual(pulses[0]['bitmask'],1<<5)
        self.assertEqual(pulses[1]['bitmask'],0)
        cameras=sum(1<<n for n in range(7,13))
        self.assertEqual(pulses[2]['bitmask'],cameras)
        self.assertEqual(pulses[3]['bitmask'],cameras|(1<<6))
        self.assertEqual(pulses[4]['bitmask'],0)
        self.assertAlmostEqual(p['duration_s'],.070120)
        self.assertEqual(pulses[2]['cycles'],125)
    def test_pins_and_arrays_rejected(self):
        with self.assertRaises(ValueError):compile_camera(self.fields(),pins=ChamberPins(fast=4))
        f=self.fields();f['FramesPerLoop']='1,2'
        with self.assertRaises(ValueError):compile_camera(f)
    def test_high_measuring_index_rejected(self):
        f=self.fields();f['MeasuringLight']='5'
        with self.assertRaises(ValueError):compile_camera(f)

class PlanTests(unittest.TestCase):
    def test_no_silent_same_time_overwrite(self):
        e=Experiment('test').set('intensity',1).set('FR',2)
        self.assertEqual([v['delay_ms'] for v in e.compile()['events']],[0,1])
    def test_midnight_rollover(self):
        e=Experiment('day').wait_until('22:00').set('intensity',0).wait_until('5:59').set('intensity',10)
        self.assertEqual(e.compile()['events'][1]['delay_ms'],107940000)
    def test_growth_reference_matches_real_timeline(self):
        root=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('growth',root/'examples/enterprise_growth.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        plan=m.build();legacy=load_timeline(root/'tests/fixtures/enterprise-growth-Timeline.xml')
        def events(p):return sorted((e['relative'],e['delay_ms'],e['command'],float(e['value'])) for e in p['events'])
        self.assertEqual(events(plan),events(legacy))
    def test_unknown_timeline_version_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.xml';p.write_text('<Timeline version="99"/>')
            with self.assertRaises(ValueError):load_timeline(p)
    def test_missing_hardware_driver_rejected(self):
        with self.assertRaises(ValueError):Experiment('test').set('temperature',20)


class JournalTests(unittest.TestCase):
    def test_idempotency_and_no_replay_after_uncertain_action(self):
        from depibeans.execution import Journal,Simulator
        class Failing(Simulator):
            def execute(self,*args):raise OSError('lost acknowledgement')
        with tempfile.TemporaryDirectory() as d:
            j=Journal(Path(d)/'journal.db');plan=Experiment('one').set('intensity',0).compile()
            self.assertTrue(j.enqueue('request',plan));self.assertFalse(j.enqueue('request',plan))
            with self.assertRaises(OSError):j.run('request',Failing(),accelerate=True)
            self.assertEqual(j.status('request')['state'],'needs_review')
            with self.assertRaises(ValueError):j.run('request',Simulator(),accelerate=True)
            j.close()
    def test_interrupted_attempt_is_frozen_on_recovery(self):
        from depibeans.execution import Journal
        with tempfile.TemporaryDirectory() as d:
            j=Journal(Path(d)/'journal.db');j.enqueue('request',Experiment('one').set('intensity',0).compile())
            j.db.execute("UPDATE attempts SET state='running'")
            with j.owner():self.assertEqual(j.recover(),1)
            self.assertEqual(j.status('request')['attempts'][0]['state'],'uncertain');j.close()
    def test_simulation_completes_but_does_not_claim_physical_success(self):
        from depibeans.execution import Journal,Simulator
        with tempfile.TemporaryDirectory() as d:
            j=Journal(Path(d)/'journal.db');j.enqueue('request',Experiment('one').set('intensity',0).compile())
            self.assertEqual(j.run('request',Simulator(),accelerate=True),'completed')
            self.assertFalse(json.loads(j.status('request')['attempts'][0]['result'])['physical_output_verified']);j.close()

class HardwareGateTests(unittest.TestCase):
    def test_uncommissioned_profile_cannot_execute(self):
        from depibeans.chamber_adapter import ChamberAdapter
        adapter=ChamberAdapter({'commissioned':False},'/tmp/unused')
        with self.assertRaises(ValueError):adapter.validate(Experiment('test').set('intensity',0).compile())
        self.assertIsNone(adapter.fpga)
    def test_camera_capture_requires_explicit_commissioning(self):
        from depibeans.avt_camera import capture
        with self.assertRaises(RuntimeError):
            capture(transport_path='unused',serial='unused',frames=1,exposure_us=50,destination='/tmp/unused',trigger=lambda:None,protocol_duration_s=.1)
    def test_uploader_uses_correct_reference_erase_opcode(self):
        from depibeans.chamber_fpga import ChamberFPGA
        class Fake(ChamberFPGA):
            def __init__(self):
                import threading
                self.clock_hz=50_000_000;self.lock=threading.RLock();self.fault=None;self.commands=[]
            def require_idle(self):pass
            def command(self,*args):self.commands.append(args);return 0
            def status(self):return 1
        f=Fake();wave=compile_camera(WaveformTests().fields());f.execute(wave)
        self.assertEqual(f.commands[-1],(0x10,1))
        self.assertEqual(f.commands[-2],(0x12,1))

if __name__=='__main__':unittest.main()
