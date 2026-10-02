import sys,unittest,tempfile,json,hashlib,zipfile,io,os,time
from pathlib import Path
from depibeans.control_app import ControlDesk
from depibeans.execution import Journal
from depibeans.run_exports import RunExports
from depibeans.scripting import Experiment
from depibeans.portal import create_app
PROFILE=Path(__file__).resolve().parents[1]/'profiles/enterprise-linux.manual.json'
class Release(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.desk=ControlDesk(self.tmp.name,PROFILE)
  e=Experiment('Recovery example');e.set('intensity',5).wait('10s').set('intensity',10).wait('20s').set('intensity',15);self.plan=e.compile()
  self.j=Journal(self.desk.database);self.j.enqueue('test',self.plan,mode='hardware',start=100000)
  self.j.db.execute("UPDATE jobs SET state='needs_review' WHERE id='test'")
  self.j.db.execute("UPDATE attempts SET state='completed' WHERE seq=0")
  self.j.db.execute("UPDATE attempts SET state='uncertain' WHERE seq=1")
 def tearDown(self):self.j.close();self.tmp.cleanup()
 def test_recovery_omits_completed_and_uncertain_requires_review(self):
  with self.assertRaises(ValueError):self.desk.recovery_plan('test')
  r=self.desk.recovery_plan('test',True);events=r['plan']['events']
  self.assertEqual(len(events),1);self.assertEqual(events[0]['value'],'15');self.assertEqual(events[0]['delay_ms'],0)
  self.assertEqual(r['plan']['recovery']['uncertain_events_omitted'],[2]);self.assertTrue(r['plan']['recovery']['initial_state_review_required'])
  with self.assertRaises(ValueError):self.desk.start(r['plan'],'hardware','new')
  self.assertEqual(self.j.status('test')['state'],'needs_review')
 def test_recovery_preserves_spacing(self):
  self.j.db.execute("UPDATE attempts SET state='pending' WHERE seq=1")
  p=self.desk.recovery_plan('test')['plan'];self.assertEqual([e['delay_ms'] for e in p['events']],[0,20000])
 def test_versions_preserve_old_body(self):
  w=self.desk.workbench;s=w.save('experiment',self.plan,'author');w.save('experiment',{**self.plan,'name':'Changed'},'second',s['id'],1)
  rev=w.revision(s['id'],1);self.assertEqual(rev['body']['name'],'Recovery example');self.assertEqual(rev['head_version'],2)
  self.assertEqual([x['version'] for x in w.revisions(s['id'])],[2,1])
 def test_bundle_contains_originals_and_checksums_no_temp_files(self):
  folder=self.desk.data/'captures'/hashlib.sha256(b'test').hexdigest()/'capture-000000';folder.mkdir(parents=True)
  payload=b'original tif bytes';(folder/'frame-000000.tif').write_bytes(payload);(folder/'metadata.json').write_text('{"state":"failed"}')
  outside=Path(self.tmp.name)/'outside.tif';outside.write_bytes(b'not allowed');(folder/'escape.tif').symlink_to(outside)
  r=self.desk.job_report('test');before=list(folder.iterdir());data=self.desk.exports.archive(r,0)
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   self.assertEqual(z.read('capture-000000/frame-000000.tif'),payload)
   self.assertNotIn('capture-000000/escape.tif',z.namelist())
   manifest=json.loads(z.read('bundle.json'));self.assertEqual(manifest['sha256']['capture-000000/frame-000000.tif'],hashlib.sha256(payload).hexdigest())
   self.assertIn('events.csv',z.namelist());self.assertIn('run-report.json',z.namelist())
  self.assertEqual(list(folder.iterdir()),before)
 def test_export_lock_and_part_bounds(self):
  r=self.desk.job_report('test');self.desk.exports.lock.acquire()
  with self.assertRaises(ValueError):self.desk.exports.archive(r,0)
  self.desk.exports.lock.release()
  with self.assertRaises(ValueError):self.desk.exports.archive(r,1)
 def test_public_depi_icon_without_login(self):
  app=create_app(Path(self.tmp.name)/'portal','https://relay.example.com')
  c=app.test_client();r=c.get('/auth.css?asset=depi-icon',base_url='https://relay.example.com')
  self.assertEqual(r.status_code,200);self.assertEqual(r.content_type,'image/png');self.assertTrue(r.data.startswith(b'\x89PNG'))
  r=c.get('/login',base_url='https://relay.example.com');self.assertIn(b'asset=depi-icon',r.data);self.assertIn(b'Sign in \xc2\xb7 DEPI',r.data)
if __name__=='__main__':unittest.main()
