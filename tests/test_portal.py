import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from depibeans.portal import create_app,add_user,database

class PortalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.app=create_app(self.root,'https://chamber.example');self.app.testing=True;self.c=self.app.test_client()
        (self.root/'approved-emails.json').write_text(json.dumps(['observer','operator','lab.user@example.edu','user@example.edu']))
        add_user(self.root,'observer','long-test-password-123','viewer')
    def tearDown(self):self.tmp.cleanup()
    def get(self,path):return self.c.get(path,base_url='https://chamber.example')
    def post(self,path,data=None,origin='https://chamber.example',json_data=None):
        return self.c.post(path,base_url='https://chamber.example',data=data,json=json_data,headers={'Origin':origin,'X-DepiBeans':'1'})
    def login(self,user='observer'):
        r=self.get('/login');csrf=re.search('name="csrf" value="([^"]+)"',r.text).group(1)
        return self.post('/login',{'username':user,'password':'long-test-password-123','csrf':csrf})
    def test_anonymous_has_no_images_or_commands(self):
        self.assertEqual(self.get('/api/frame').status_code,401)
        self.assertEqual(self.get('/api/status').status_code,401)
        self.assertEqual(self.post('/api/light',json_data={'value':155}).status_code,401)
        self.assertEqual(self.get('/').location,'/login')
    def test_login_cookie_and_role_enforcement(self):
        response=self.login();self.assertEqual(response.status_code,302)
        cookie=response.headers['Set-Cookie'];self.assertIn('Secure',cookie);self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Lax',cookie)
        self.assertEqual(self.get('/api/account').json,{'username':'observer','role':'viewer'})
        self.assertEqual(self.post('/api/capture',json_data={'request_id':'snap'}).status_code,403)
        self.assertEqual(self.get('/data/portal.sqlite3').status_code,404)
    def test_cross_site_login_and_operator_command_denied(self):
        self.assertEqual(self.post('/login',{},origin='https://evil.example').status_code,403)
        add_user(self.root,'operator','long-test-password-123','operator');self.login('operator')
        self.assertEqual(self.post('/api/light',json_data={'value':155},origin='https://evil.example').status_code,403)
        self.assertEqual(self.c.get('/api/account',base_url='https://evil.example').status_code,400)
    def test_logout_and_disable_revoke_sessions(self):
        self.login();self.assertEqual(self.post('/logout',json_data={}).status_code,200)
        self.assertEqual(self.get('/api/account').status_code,401)
        self.login()
        with database(self.root/'portal.sqlite3') as db:db.execute("UPDATE users SET enabled=0 WHERE username='observer'")
        self.assertEqual(self.get('/api/account').status_code,401)
    def test_failed_password_is_generic_and_throttled(self):
        r=self.get('/login');csrf=re.search('name="csrf" value="([^"]+)"',r.text).group(1)
        with database(self.root/'portal.sqlite3') as db:
            import time
            db.executemany('INSERT INTO login_attempts VALUES (?,?)',[(time.time(),'observer')]*10)
        self.assertEqual(self.post('/login',{'username':'observer','password':'wrong','csrf':csrf}).status_code,429)
    def test_shared_attempt_budget_never_blocks_a_valid_login(self):
        import time
        with database(self.root/'portal.sqlite3') as db:
            db.executemany('INSERT INTO login_attempts VALUES (?,?)',[(time.time(),'guess%d'%i) for i in range(120)])
        self.assertEqual(self.login().status_code,302)
        r=self.get('/login');csrf=re.search('name="csrf" value="([^"]+)"',r.text).group(1)
        self.assertEqual(self.post('/login',{'username':'stranger','password':'wrong','csrf':csrf}).status_code,429)
    def test_authenticated_proxy_drops_user_supplied_authority(self):
        add_user(self.root,'operator','long-test-password-123','operator');self.login('operator')
        with patch('depibeans.portal.http.client.HTTPConnection') as conn:
            upstream=conn.return_value.getresponse.return_value;upstream.status=200;upstream.read.return_value=b'{}';upstream.getheader.return_value='application/json'
            r=self.post('/api/capture',json_data={'request_id':'snap'});self.assertEqual(r.status_code,200)
            args=conn.return_value.request.call_args
            self.assertEqual(json.loads(args.kwargs['body'])['request_id'],'operator:snap')
            self.assertEqual(args.kwargs['headers']['Host'],'127.0.0.1:8765')
            self.assertNotIn('Cookie',args.kwargs['headers'])

    def test_invitation_is_email_bound_single_use_and_does_not_auto_login(self):
        from depibeans.portal import create_invitation
        link=create_invitation(self.root,'Lab.User@example.edu','operator','https://chamber.example')
        path=link.removeprefix('https://chamber.example');r=self.get(path)
        csrf=re.search('name="csrf" value="([^"]+)"',r.text).group(1)
        r=self.post(path,{'csrf':csrf,'password':'new-password-long-123','confirm':'new-password-long-123','email':'attacker@example.edu','role':'admin'})
        self.assertEqual(r.status_code,302);self.assertEqual(self.get(path).status_code,410)
        self.assertEqual(self.get('/api/status').status_code,401)
        with database(self.root/'portal.sqlite3') as db:
            row=db.execute("SELECT username,role FROM users WHERE username='lab.user@example.edu'").fetchone()
            self.assertEqual(tuple(row),('lab.user@example.edu','operator'))
            self.assertIsNone(db.execute("SELECT username FROM users WHERE username='attacker@example.edu'").fetchone())
    def test_invitation_expiration_and_reissue(self):
        from depibeans.portal import create_invitation
        first=create_invitation(self.root,'user@example.edu','viewer','https://chamber.example')
        second=create_invitation(self.root,'user@example.edu','viewer','https://chamber.example')
        self.assertEqual(self.get(first.removeprefix('https://chamber.example')).status_code,410)
        with database(self.root/'portal.sqlite3') as db:db.execute('UPDATE invitations SET expires=0')
        self.assertEqual(self.get(second.removeprefix('https://chamber.example')).status_code,410)

    def test_unlisted_invitation_rejected(self):
        from depibeans.portal import create_invitation
        with self.assertRaises(ValueError):create_invitation(self.root,'stranger@example.edu','operator','https://chamber.example')

    def test_private_bridge_requires_credential_before_login_or_health(self):
        (self.root/'bridge.key').write_text('private-bridge-test')
        app=create_app(self.root,'https://chamber.example');client=app.test_client()
        self.assertEqual(client.get('/login',base_url='https://chamber.example').status_code,403)
        self.assertEqual(client.get('/_bridge/health',base_url='https://chamber.example').status_code,403)
        response=client.get('/_bridge/health',base_url='https://chamber.example',headers={'X-DepiBeans-Bridge':'private-bridge-test'})
        self.assertEqual(response.json,{'service':'depibeans-portal','chambers':[]})

    def test_invitation_accepts_short_password_but_rejects_empty_mismatch_and_oversize(self):
        from depibeans.portal import create_invitation
        path=create_invitation(self.root,'user@example.edu','operator','https://chamber.example').removeprefix('https://chamber.example')
        page=self.get(path)
        self.assertNotIn('minlength="14"',page.text)
        csrf=re.search('name="csrf" value="([^"]+)"',page.text).group(1)
        for password,confirm in [('', ''), ('a','b'), ('x'*257,'x'*257)]:
            response=self.post(path,{'csrf':csrf,'password':password,'confirm':confirm})
            self.assertEqual(response.status_code,200)
            with database(self.root/'portal.sqlite3') as db:
                self.assertIsNone(db.execute("SELECT username FROM users WHERE username='user@example.edu'").fetchone())
        self.assertEqual(self.post(path,{'csrf':csrf,'password':'a','confirm':'a'}).status_code,302)
        csrf=re.search('name="csrf" value="([^"]+)"',self.get('/login').text).group(1)
        self.assertEqual(self.post('/login',{'csrf':csrf,'username':'user@example.edu','password':'a'}).status_code,302)
        self.assertEqual(self.get('/api/account').json,{'username':'user@example.edu','role':'operator'})
