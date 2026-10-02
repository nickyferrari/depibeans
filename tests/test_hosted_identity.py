import base64,hashlib,hmac,json,tempfile,time,unittest
from pathlib import Path
from depibeans.hosted_identity import verify_assertion
class HostedIdentityTests(unittest.TestCase):
 def claim(self,role='operator',age=0,chamber='depi-one',nonce='a'*32):
  h=base64.b64encode(json.dumps(dict(user='scientist@example.edu',role=role,chamber=chamber,time=int(time.time())-age,nonce=nonce)).encode()).decode()
  sig=hmac.new(b'test-only-key','\n'.join(('depi-hosted-v1','POST','/api/run',hashlib.sha256(b'{}').hexdigest(),h)).encode(),hashlib.sha256).hexdigest();return h,sig
 def test_request_binding_and_replay(self):
  with tempfile.TemporaryDirectory() as d:
   h,s=self.claim();args=(d,'test-only-key',h,s,'POST','/api/run',b'{}','depi-one')
   self.assertEqual(verify_assertion(*args),('scientist@example.edu','operator'))
   with self.assertRaisesRegex(ValueError,'Repeated'):verify_assertion(*args)
   with self.assertRaises(ValueError):verify_assertion(d,'test-only-key',h,s,'POST','/api/run',b'{"modified":true}','depi-one')
 def test_expired_wrong_chamber_and_viewer_denied(self):
  for values in [dict(age=60),dict(chamber='depi-two'),dict(role='viewer')]:
   with tempfile.TemporaryDirectory()as d:
    h,s=self.claim(**values)
    with self.assertRaises(ValueError):verify_assertion(d,'test-only-key',h,s,'POST','/api/run',b'{}','depi-one')

class HostedGatewayTests(unittest.TestCase):
 def test_configured_node_identity_and_wrong_chamber(self):
  from depibeans.portal import create_app
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'bridge.key').write_text('fixture-bridge-key');(root/'hosted-auth.enabled').touch()
   (root/'controllers.json').write_text(json.dumps({'depi4':{'id':'depi-five','port':8765}}))
   client=create_app(root,'https://fixture.example').test_client()
   target='/api/status?chamber=depi4'
   for chamber,expected in [('depi-one',403),('depi-five',200)]:
    claim=base64.b64encode(json.dumps(dict(user='scientist@example.edu',role='viewer',chamber=chamber,time=int(time.time()),nonce=('c' if chamber=='depi-one' else 'd')*32)).encode()).decode()
    signature=hmac.new(b'fixture-bridge-key','\n'.join(('depi-hosted-v1','GET',target,hashlib.sha256(b'').hexdigest(),claim)).encode(),hashlib.sha256).hexdigest()
    with patch('depibeans.portal.http.client.HTTPConnection') as conn:
     upstream=conn.return_value.getresponse.return_value;upstream.status=200;upstream.read.return_value=b'{"chamber_id":"depi-five"}';upstream.getheader.return_value=None
     r=client.get(target,base_url='https://fixture.example',headers={'X-DepiBeans-Bridge':'fixture-bridge-key','X-Depi-Identity':claim,'X-Depi-Signature':signature})
     self.assertEqual(r.status_code,expected)
     if expected==403:conn.assert_not_called()
     else:self.assertEqual(conn.return_value.request.call_args.args[1],'/api/status')
 def test_gated_identity_handshake_and_account(self):
  from depibeans.portal import create_app
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);(root/'bridge.key').write_text('fixture-bridge-key');(root/'hosted-auth.enabled').touch()
   app=create_app(root,'https://fixture.example');client=app.test_client()
   claim=base64.b64encode(json.dumps(dict(user='scientist@example.edu',role='viewer',chamber='depi-one',time=int(time.time()),nonce='b'*32)).encode()).decode()
   target='/api/account';signature=hmac.new(b'fixture-bridge-key','\n'.join(('depi-hosted-v1','GET',target,hashlib.sha256(b'').hexdigest(),claim)).encode(),hashlib.sha256).hexdigest()
   headers={'X-DepiBeans-Bridge':'fixture-bridge-key','X-Depi-Identity':claim,'X-Depi-Signature':signature}
   response=client.get(target,base_url='https://fixture.example',headers=headers)
   self.assertEqual(response.status_code,200);self.assertEqual(response.json,{'username':'scientist@example.edu','role':'viewer'})
   self.assertEqual(client.get(target,base_url='https://fixture.example',headers=headers).status_code,403)
   health=client.get('/_bridge/health',base_url='https://fixture.example',headers={'X-DepiBeans-Bridge':'fixture-bridge-key'})
   self.assertTrue(health.json['hosted_identity'])
