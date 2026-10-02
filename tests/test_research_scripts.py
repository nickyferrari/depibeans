import unittest
from depibeans.scripting import Experiment
from depibeans.research_scripts import ScriptSession, js_add
from depibeans.camera_protocol import seconds


class ResearchScriptTests(unittest.TestCase):
    def test_duration_concatenation_preserves_legacy_integer_format(self):
        self.assertEqual(js_add(3.0, 'hr'), '3hr')
        self.assertEqual(seconds(js_add(3.0, 'hr')), 10800)
        self.assertEqual(js_add(2, 3), 5)

    def test_explicit_negative_string_section_and_following_absolute_day(self):
        e=Experiment('legacy day')
        e.end_section('-1').set('intensity',0).wait_until('08:00').set('intensity',100)
        p=e.compile()
        self.assertEqual(p['events'][0]['delay_ms'],1)
        self.assertEqual(p['events'][1]['delay_ms'],28800000)
        self.assertEqual([s['number'] for s in p['sections']],[-1,0])

    def test_protocol_final_definition_is_resolved_at_compile(self):
        e=Experiment('protocol mutation');s=ScriptSession(e)
        p=s.new_protocol('fs');p.fields['NumberLoops']=1;s.capture(p)
        p.analysis='new analysis';p.fields['NumberLoops']=2
        result=s.compile()
        self.assertEqual(result['events'][0]['analysis'],'new analysis')
        self.assertEqual(result['protocols'][0]['fields']['NumberLoops'],2)
        p.fields['NumberLoops']=3
        self.assertEqual(result['protocols'][0]['fields']['NumberLoops'],2)

    def test_unused_protocols_are_not_executed_or_exported(self):
        e=Experiment('growth');s=ScriptSession(e)
        s.new_protocol('unused');e.set('intensity',0)
        self.assertEqual(s.compile()['protocols'],[])

    def test_loop_limit_stops_unbounded_compilation(self):
        s=ScriptSession(Experiment('bounded'));s.iterations=100000
        with self.assertRaises(ValueError):s.tick()

    def test_duplicate_protocols_fail(self):
        s=ScriptSession(Experiment('names'));s.new_protocol('fs')
        with self.assertRaises(ValueError):s.new_protocol('fs')
