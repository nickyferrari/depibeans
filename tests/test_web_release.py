import importlib.util,json,tempfile,unittest,hashlib
from pathlib import Path
spec=importlib.util.spec_from_file_location('remote',Path(__file__).parents[1]/'tools/release/remote.py');remote=importlib.util.module_from_spec(spec);spec.loader.exec_module(remote)
class ReleaseTests(unittest.TestCase):
 def setup_release(self,base):
  root=base/'live';root.mkdir();(root/'app.js').write_text('old')
  stage=base/'stage';(stage/'files').mkdir(parents=True);(stage/'files/app.js').write_text('new')
  (stage/'spec.json').write_text(json.dumps({'root':str(root),'commit':'abc','expected':{'app.js':hashlib.sha256(b'old').hexdigest()},'files':{'app.js':hashlib.sha256(b'new').hexdigest()}}));return root,stage
 def test_deploy_and_rollback(self):
  with tempfile.TemporaryDirectory() as d:
   root,stage=self.setup_release(Path(d));remote.run(stage,'prepare');remote.run(stage,'apply');self.assertEqual((root/'app.js').read_text(),'new');remote.run(stage,'unlock');remote.run(stage,'rollback');self.assertEqual((root/'app.js').read_text(),'old')
 def test_concurrent_change_refused(self):
  with tempfile.TemporaryDirectory() as d:
   root,stage=self.setup_release(Path(d));remote.run(stage,'prepare');(root/'app.js').write_text('someone else')
   with self.assertRaises(ValueError):remote.run(stage,'apply')
   self.assertEqual((root/'app.js').read_text(),'someone else');remote.run(stage,'abort')
 def test_corrupt_upload_refused(self):
  with tempfile.TemporaryDirectory() as d:
   root,stage=self.setup_release(Path(d));(stage/'files/app.js').write_text('bad')
   with self.assertRaises(ValueError):remote.run(stage,'prepare')
   self.assertEqual((root/'app.js').read_text(),'old');self.assertFalse((root/'.depi-release-lock').exists())
 def test_rollback_refuses_later_change(self):
  with tempfile.TemporaryDirectory() as d:
   root,stage=self.setup_release(Path(d));remote.run(stage,'prepare');remote.run(stage,'apply');(root/'app.js').write_text('later')
   with self.assertRaises(ValueError):remote.run(stage,'rollback')
   self.assertEqual((root/'app.js').read_text(),'later')

 def test_recorded_drift_refused_even_with_matching_expected(self):
  with tempfile.TemporaryDirectory() as d:
   root,stage=self.setup_release(Path(d))
   (root/'.depi-web-release.json').write_text(json.dumps({'files':{'app.js':hashlib.sha256(b'original').hexdigest()}}))
   with self.assertRaisesRegex(ValueError,'Live drift'):remote.run(stage,'prepare')
   self.assertEqual((root/'app.js').read_text(),'old')
   self.assertFalse((root/'.depi-release-lock').exists())
 def test_missing_baseline_refused(self):
  with tempfile.TemporaryDirectory() as d:
   root,stage=self.setup_release(Path(d));p=stage/'spec.json';s=json.loads(p.read_text());s.pop('expected');p.write_text(json.dumps(s))
   with self.assertRaisesRegex(ValueError,'Missing Git baseline'):remote.run(stage,'prepare')
