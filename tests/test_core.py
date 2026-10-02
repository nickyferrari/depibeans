import tempfile
import unittest
import uuid
import json
from unittest.mock import patch

def uid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name))

from pathlib import Path
from depibeans.core import Engine,Rejected

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.now=1000.0
        self.path=str(Path(self.folder.name)/'state.sqlite')
        self.e=Engine(self.path,lambda:self.now)
        self.e.add_simulator('one','One',{'lights':[0,500]})
        self.e.add_simulator('two','Two',{'lights':[0,500]})
        self.e.grant('operator','one','operator',granted_by='bootstrap')
        self.e.grant('reader','one','viewer',granted_by='bootstrap')
    def tearDown(self):
        self.e.close();self.folder.cleanup()
    def command(self,**kw):
        a=dict(actor='operator',command_id=uid('a'),chamber='one',revision=0,settings={'lights':134},ttl_s=60)
        a.update(kw);return self.e.command(**a)
    def test_access_is_chamber_scoped(self):
        self.assertEqual(len(self.e.status('operator')),1)
        for change in [{'actor':'reader'},{'chamber':'two'},{'actor':'stranger'}]:
            with self.assertRaises(Rejected):self.command(**change)
    def test_retry_returns_same_result_after_expiry_and_restart(self):
        expected=self.command();self.now=1200
        self.e.close();self.e=Engine(self.path,lambda:self.now)
        self.assertEqual(self.command(),expected)
        self.assertEqual(self.e.status('operator')[0]['revision'],1)
    def test_conflicting_retry_rejected(self):
        self.command()
        with self.assertRaises(Rejected):self.command(settings={'lights':0})
    def test_stale_revision_and_expiry(self):
        self.command()
        for changes in [{'command_id':uid('b')},{'command_id':uid('b'),'revision':1,'ttl_s':0}]:
            with self.assertRaises(Rejected):self.command(**changes)
    def test_manual_pauses_and_schedule_applies_absolute_value(self):
        self.e.schedule('operator',uid('s'),'one',1100,{'lights':134})
        self.command(settings={'lights':50})
        self.assertEqual(self.e.schedules('operator')[0]['state'],'paused')
        self.e.set_schedule_state('operator','one',uid('s'),'active')
        self.now=1100;self.e.tick();self.e.tick()
        self.assertEqual(self.e.status('operator')[0]['settings']['lights'],134)
        self.assertEqual(self.e.status('operator')[0]['revision'],2)
        self.assertEqual(self.e.schedules('operator')[0]['state'],'completed')
    def test_missed_not_replayed(self):
        self.e.schedule('operator',uid('s'),'one',1100,{'lights':134})
        self.now=1220;self.e.tick()
        self.assertEqual(self.e.schedules('operator')[0]['state'],'missed')
        self.assertEqual(self.e.status('operator')[0]['settings'],{})
    def test_revocation_prevents_scheduled_execution(self):
        self.e.schedule('operator',uid('s'),'one',1100,{'lights':134})
        self.e.grant('operator','one','viewer',granted_by='bootstrap');self.now=1100;self.e.tick()
        self.assertEqual(self.e.schedules('operator')[0]['state'],'paused')
        self.assertEqual(self.e.status('operator')[0]['revision'],0)
    def test_delete_preserves_audit(self):
        self.e.schedule('operator',uid('s'),'one',1100,{'lights':134})
        self.e.set_schedule_state('operator','one',uid('s'),'deleted')
        self.assertEqual(self.e.schedules('operator'),[])
        self.now=1100;self.assertEqual(self.e.tick(),0)
        self.assertGreater(self.e.db.execute('SELECT count(*) FROM audit').fetchone()[0],0)
    def test_resume_conflict(self):
        self.e.schedule('operator',uid('s'),'one',1100,{'lights':134})
        self.e.set_schedule_state('operator','one',uid('s'),'paused')
        self.e.schedule('operator',uid('t'),'one',1150,{'lights':0})
        with self.assertRaises(Rejected):self.e.set_schedule_state('operator','one',uid('s'),'active')
    def test_invalid_numbers_and_unsupported_capability(self):
        for val in [float('nan'),float('inf'),True,-1,501,10**1000]:
            with self.assertRaises(Rejected):self.command(settings={'lights':val})
        with self.assertRaises(Rejected):self.command(settings={'temperature':25})
        self.assertEqual(self.e.status('operator')[0]['revision'],0)
    def test_zero_ttl_is_rejected(self):
        with self.assertRaises(Rejected):self.command(ttl_s=0)
        self.assertEqual(self.e.status('operator')[0]['revision'],0)
    def test_two_connections_same_revision_only_one_wins(self):
        import concurrent.futures,threading
        gate=threading.Barrier(2)
        def attempt(identifier):
            e=Engine(self.path,lambda:self.now)
            try:
                gate.wait(timeout=5)
                return e.command('operator',uid(identifier),'one',0,{'lights':134},60)['state']
            except Rejected:
                return 'rejected'
            finally:
                e.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(attempt,['first','second']))
        self.assertEqual(sorted(results),['rejected','simulated'])
        self.assertEqual(self.e.status('operator')[0]['revision'],1)
    def test_live_mode_fails_closed(self):
        self.e.db.execute("UPDATE chambers SET mode='live' WHERE id='one'")
        with self.assertRaises(Rejected):self.command()
        self.assertEqual(self.e.status('operator')[0]['revision'],0)

    def test_ids_are_scoped_to_chambers(self):
        self.e.grant('other','two','operator',granted_by='bootstrap')
        self.command()
        result=self.e.command('other',uid('a'),'two',0,{'lights':10})
        self.assertEqual(result['revision'],1)
        self.e.schedule('operator',uid('shared'),'one',1200,{'lights':134})
        self.e.schedule('other',uid('shared'),'two',1200,{'lights':10})
        self.assertEqual(len(self.e.schedules('other')),1)
    def test_manual_cannot_poison_schedule_namespace(self):
        sid=uid('same')
        self.e.schedule('operator',sid,'one',1100,{'lights':134})
        with self.assertRaises(Rejected):self.command(command_id='schedule:'+sid)
        self.command(command_id=sid,settings={'lights':1})
        self.e.set_schedule_state('operator','one',sid,'active')
        self.now=1100;self.e.tick()
        self.assertEqual(self.e.status('operator')[0]['settings']['lights'],134)
    def test_duplicate_and_deleted_schedule_ids_are_typed_rejections(self):
        sid=uid('same')
        self.e.schedule('operator',sid,'one',1100,{'lights':134})
        with self.assertRaises(Rejected):self.e.schedule('operator',sid,'one',1400,{'lights':1})
        self.e.set_schedule_state('operator','one',sid,'deleted')
        with self.assertRaises(Rejected):self.e.schedule('operator',sid,'one',1400,{'lights':1})
    def test_retry_uses_original_server_expiry(self):
        expected=self.command(ttl_s=60)
        self.now=2000
        self.assertEqual(self.command(ttl_s=30),expected)
        self.assertEqual(expected['expires'],1060)
    def test_manual_pause_audited_and_returned(self):
        sid=uid('pause')
        self.e.schedule('operator',sid,'one',1100,{'lights':134})
        result=self.command()
        self.assertEqual(result['paused_schedule_ids'],[sid])
        row=self.e.db.execute("SELECT * FROM audit WHERE event='schedule-paused'").fetchone()
        self.assertEqual(row['actor'],'operator')
        self.assertEqual(json.loads(row['detail'])['command_id'],uid('a'))
    def test_grants_have_actor_audit_and_revocation_pauses(self):
        sid=uid('access')
        self.e.schedule('operator',sid,'one',1100,{'lights':134})
        self.e.grant('operator','one',None,granted_by='administrator')
        row=self.e.db.execute("SELECT * FROM audit WHERE event='membership-changed' ORDER BY id DESC").fetchone()
        self.assertEqual(row['actor'],'administrator')
        self.assertIsNone(json.loads(row['detail'])['role'])
        self.assertEqual(self.e.db.execute('SELECT state FROM schedules').fetchone()[0],'paused')
        with self.assertRaises(Rejected):self.command()
    def test_boundary_errors_use_rejected(self):
        for value in ['134',None,[1],{}]:
            with self.assertRaises(Rejected):self.command(settings={'lights':value})
        for value in ['134',None,[1],True]:
            with self.assertRaises(Rejected):self.command(ttl_s=value)
    def test_one_occurrence_failure_does_not_rollback_another(self):
        self.e.grant('operator','two','operator',granted_by='bootstrap')
        self.e.schedule('operator',uid('one'),'one',1100,{'lights':134})
        self.e.schedule('operator',uid('two'),'two',1100,{'lights':10})
        original=self.e._command
        def failure(*args,**kwargs):
            result=original(*args,**kwargs)
            if args[2]=='two':raise RuntimeError('injected failure after simulator write')
            return result
        self.now=1100
        with patch.object(self.e,'_command',side_effect=failure):self.assertEqual(self.e.tick(),2)
        states={r['id']:r for r in self.e.status('operator')}
        self.assertEqual(states['one']['revision'],1)
        self.assertEqual(states['two']['revision'],0)
        self.assertEqual(self.e.tick(),0)
        schedule_states={r['chamber']:r['state'] for r in self.e.schedules('operator')}
        self.assertEqual(schedule_states,{'one':'completed','two':'failed'})

if __name__=='__main__':unittest.main()
