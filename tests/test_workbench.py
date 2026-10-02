import json,sys,tempfile,time,unittest,threading
from pathlib import Path
from unittest.mock import patch
from depibeans.control_app import ControlDesk
from depibeans.workbench import Workbench,validate_plan,recipe_plan
from depibeans.execution import Journal
PROFILE=Path(__file__).resolve().parents[1]/'profiles/enterprise-linux.manual.json'
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.desk=ControlDesk(self.tmp.name,PROFILE);self.w=self.desk.workbench
  self.plan=recipe_plan({'name':'Custom test','steps':[{'kind':'set','command':'intensity','value':10},{'kind':'wait','duration':'5min'},{'kind':'set','command':'intensity','value':0}],'repeat':2})
 def tearDown(self):self.tmp.cleanup()
 def action(self,**kw):return self.desk.action('/api/run',{'_actor':'tester',**kw})
 def test_save_version_conflict_and_installed_plans_preserved(self):
  count=len(self.desk.catalog());r=self.action(operation='save',plan=self.plan)
  self.assertEqual(self.desk.plan(r['id'])['name'],'Custom test');self.assertEqual(len(self.desk.catalog()),count+1)
  r2=self.action(operation='save',plan=self.plan,id=r['id'],version=1);self.assertEqual(r2['version'],2)
  with self.assertRaises(ValueError):self.action(operation='save',plan=self.plan,id=r['id'],version=1)
  self.action(operation='archive',id=r['id'],version=2);self.assertEqual(len(self.desk.catalog()),count)
  with self.w.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM versions').fetchone()[0],2)
 def test_upload_actor_isolation_and_order(self):
  body=json.dumps(self.plan);self.w.chunk({'upload':'u','sequence':1,'chunk':body[10:]},'a')
  with self.assertRaises(ValueError):self.w.assembled('u','a')
  self.w.chunk({'upload':'u','sequence':0,'chunk':body[:10]},'a');self.assertEqual(self.w.assembled('u','a'),self.plan)
  with self.assertRaises(ValueError):self.w.assembled('u','b')
 def test_hardware_gate_and_malformed_inputs(self):
  result=validate_plan(self.plan,self.desk.profile());self.assertFalse(result['hardware_ready'])
  for plan in [[],{'name':'x','events':[None]},dict(self.plan,events=[{'kind':'set','command':'intensity','value':'NaN','delay_ms':0,'relative':True}])]:
   with self.assertRaises((ValueError,TypeError)):validate_plan(plan,self.desk.profile())
 def test_schedule_copies_plan_and_dispatches_once(self):
  saved=self.action(operation='save',plan=self.plan);due=time.time()+100
  checked={'plan':self.plan,'hardware_ready':True,'hardware_reasons':[]}
  with patch('depibeans.control_app.validate_plan',return_value=checked):self.action(operation='schedule',experiment=saved['id'],mode='hardware',due=due,request_id='schedule1')
  changed=dict(self.plan,name='Changed later');self.action(operation='save',plan=changed,id=saved['id'],version=1)
  with self.w.db() as db:db.execute('UPDATE schedules SET due=?',(time.time()-1,))
  with patch.object(self.desk,'start',return_value={'state':'pending'}) as start:
   self.desk.scheduler_tick();self.desk.scheduler_tick();self.assertEqual(start.call_count,1);self.assertEqual(start.call_args.args[0]['name'],'Custom test')
 def test_disabled_account_cannot_start_what_it_queued(self):
  import json as js,sqlite3
  saved=self.action(operation='save',plan=self.plan)
  checked={'plan':self.plan,'hardware_ready':True,'hardware_reasons':[]}
  with patch('depibeans.control_app.validate_plan',return_value=checked):self.action(operation='schedule',experiment=saved['id'],mode='hardware',due=time.time()+100,request_id='revoked')
  with self.w.db() as db:db.execute('UPDATE schedules SET due=?,actor=?',(time.time()-1,'former@example.edu'))
  portal=self.desk.data/'portal';portal.mkdir(exist_ok=True)
  (portal/'approved-emails.json').write_text(js.dumps(['former@example.edu']))
  db=sqlite3.connect(portal/'portal.sqlite3');db.execute('CREATE TABLE users(username TEXT PRIMARY KEY,password_hash TEXT,role TEXT,enabled INTEGER)');db.execute("INSERT INTO users VALUES('former@example.edu','x','operator',0)");db.commit();db.close()
  with patch.object(self.desk,'start') as start:self.desk.scheduler_tick();start.assert_not_called()
  self.assertEqual(self.desk.workspace()['schedules'][0]['state'],'cancelled')
 def test_unknown_or_untracked_account_keeps_its_schedule(self):
  self.assertTrue(self.desk.actor_authorized('Local operator'));self.assertTrue(self.desk.actor_authorized('hosted@example.edu'))
 def test_missed_start_not_replayed(self):
  saved=self.action(operation='save',plan=self.plan)
  checked={'plan':self.plan,'hardware_ready':True,'hardware_reasons':[]}
  with patch('depibeans.control_app.validate_plan',return_value=checked):self.action(operation='schedule',experiment=saved['id'],mode='hardware',due=time.time()+100,request_id='late')
  with self.w.db() as db:db.execute('UPDATE schedules SET due=?',(time.time()-60,))
  with patch.object(self.desk,'start') as start:self.desk.scheduler_tick();start.assert_not_called()
  self.assertEqual(self.desk.workspace()['schedules'][0]['state'],'missed')
 def test_restart_freezes_overdue_schedule(self):
  with self.w.db() as db:db.execute('INSERT INTO schedules VALUES(?,?,?,?,?,?,?)',('old','{}','simulation',time.time()-5,'queued','tester',None))
  new=Workbench(self.w.path)
  with new.db() as db:self.assertEqual(db.execute('SELECT state FROM schedules').fetchone()[0],'missed')
 def test_preview_settings_do_not_actuate_hardware(self):
  with patch.object(self.desk,'start') as start:
   self.desk.action('/api/capture',{'operation':'preview_settings','exposure_us':500,'gain':13})
   start.assert_not_called();self.assertEqual(self.desk.profile()['live_preview'],{'exposure_us':500,'gain':13})
   with self.assertRaises(ValueError):self.desk.action('/api/capture',{'operation':'preview_settings','exposure_us':float('inf'),'gain':13})
  self.assertEqual(json.loads(PROFILE.read_text())['camera']['preview_protocol']['Exposure'],'50us')
 def test_discard_preserves_completed_attempts_and_uncertainty(self):
  j=Journal(self.desk.database);j.enqueue('interrupted',self.plan,mode='hardware')
  j.db.execute("UPDATE jobs SET state='needs_review' WHERE id='interrupted'")
  j.db.execute("UPDATE attempts SET state='uncertain' WHERE job='interrupted' AND seq=0")
  self.action(operation='discard',id='interrupted');report=self.desk.job_report('interrupted');self.assertEqual(report['state'],'discarded');self.assertEqual(report['attempts'][0]['state'],'uncertain');j.close()
 def test_calibration_fit_stays_offline(self):
  r=self.action(operation='calibration_fit',samples=[[0,0],[50,48],[100,97]]);self.assertFalse(r['uploaded_to_hardware']);self.assertAlmostEqual(r['rmse'],0,places=8)
if __name__=='__main__':unittest.main()
