import sys,tempfile,json,time,threading,unittest
from pathlib import Path
from depibeans.operations import Operations
from depibeans.control_app import ControlDesk
from depibeans.portal import create_app,add_user
from unittest.mock import patch
class Checks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.o=Operations(self.root/'ops.db')
 def tearDown(self):self.tmp.cleanup()
 def test_durable_log(self):
  key=self.o.record('one','/api/light',{'value':12},'request','received');self.o.finish(key,'accepted')
  self.assertEqual(Operations(self.root/'ops.db').recent()[0]['outcome'],'accepted')
 def desk(self):
  p=self.root/'profile.json';p.write_text(json.dumps({'camera':{},'limits':{}}));return ControlDesk(self.root,p)
 def test_command_needs_no_reservation(self):
  d=self.desk()
  with patch.object(d,'_action',return_value={'ok':True}) as action:
   d.action('/api/light',{'_actor':'one','value':12});action.assert_called_once()
 def test_gallery_excludes_outside_capture_root(self):
  d=self.desk();outside=self.root/'outside.tif';outside.write_bytes(b'private')
  folder=d.data/'captures'/'job'/'capture-000';folder.mkdir(parents=True)
  (folder/'good.tif').write_bytes(b'image');(folder/'bad.tif').symlink_to(outside)
  (folder/'metadata.json').write_text(json.dumps({'state':'completed','frames':[{'file':'good.tif'},{'file':'bad.tif'}]}))
  self.assertEqual(len(d.gallery()),1)
  with self.assertRaises(ValueError):d.saved_frame('../outside.tif')
 def test_status_works_without_camera(self):
  d=self.desk();status=d.status();self.assertEqual(status['chamber_id'],'depi-one');self.assertIsNone(status['progress']);self.assertFalse(status['live']['running'])
 def test_new_chamber_does_not_impersonate_first_controller(self):
  d=self.desk();d.profile_path.write_text(json.dumps({'camera':{},'limits':{},'chamber':'DEPI 5','chamber_id':'depi-five','commissioned':False}))
  status=d.status();self.assertEqual(status['chamber_id'],'depi-five');self.assertEqual(status['chamber'],'DEPI 5');self.assertFalse(status['manual_light_ready']);self.assertFalse(status['experiment_ready'])
 def test_actor_is_server_authenticated(self):
  (self.root/'approved-emails.json').write_text('["operator@example.com"]');add_user(self.root,'operator@example.com','long-test-password','operator')
  app=create_app(self.root,'https://example.com');client=app.test_client()
  client.get('/login',base_url='https://example.com')
  with client.session_transaction(base_url='https://example.com') as sess:csrf=sess['csrf']
  client.post('/login',base_url='https://example.com',headers={'Origin':'https://example.com'},data={'username':'operator@example.com','password':'long-test-password','csrf':csrf})
  with patch('depibeans.portal.http.client.HTTPConnection') as conn:
   upstream=conn.return_value.getresponse.return_value;upstream.status=200;upstream.read.return_value=b'{}';upstream.getheader.return_value=None
   response=client.post('/api/light',base_url='https://example.com',headers={'Origin':'https://example.com','X-DepiBeans':'1'},json={'command':'intensity','value':12,'_actor':'spoof'})
   self.assertEqual(response.status_code,200)
   call=conn.return_value.request.call_args;self.assertEqual(call.args[1],'/api/light');self.assertEqual(json.loads(call.kwargs['body'])['_actor'],'operator@example.com')
if __name__=='__main__':unittest.main()
