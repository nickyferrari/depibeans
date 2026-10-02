import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from http.server import ThreadingHTTPServer
from depibeans.control_app import ControlDesk,Handler

class ControlAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        self.profile=root/'profile.json';self.profile.write_text(json.dumps({'commissioned':False,'limits':{},'camera':{}}))
        self.desk=ControlDesk(root,self.profile)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.desk=self.desk
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):
        deadline=time.monotonic()+5
        while self.desk.active and time.monotonic()<deadline:time.sleep(.01)
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,path,data=None,headers=None):
        defaults={'X-DepiBeans':'1','Content-Type':'application/json'};defaults.update(headers or {})
        request=Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers=defaults)
        with urlopen(request,timeout=5) as response:return json.load(response)
    def test_physical_controls_rejected_before_any_job_is_created(self):
        with self.assertRaises(HTTPError) as error:self.request('/api/light',{'command':'intensity','value':100,'request_id':'light'})
        self.assertEqual(error.exception.code,400)
        with self.assertRaises(HTTPError):self.request('/api/capture',{'request_id':'camera'})
        self.assertEqual(self.desk.status()['recent'],[])
    def test_foreign_origin_and_missing_application_header_rejected(self):
        with self.assertRaises(HTTPError) as error:self.request('/api/preview-light',{'command':'intensity','value':100},{'Origin':'https://elsewhere.example'})
        self.assertEqual(error.exception.code,403)
        with self.assertRaises(HTTPError):self.request('/api/preview-light',{'command':'intensity','value':100},{'X-DepiBeans':''})
        self.assertEqual(self.desk.preview['intensity'],0)
    def test_preview_only_lighting_is_rejected(self):
        with self.assertRaises(HTTPError) as error:self.request('/api/preview-light',{'command':'intensity','value':155})
        self.assertEqual(error.exception.code,400);self.assertEqual(self.desk.preview['intensity'],0)
    def test_simulation_is_rejected_before_any_job_is_created(self):
        key=self.desk.catalog()[0]['id']
        self.desk.plans[key]=dict(self.desk.plans[key],events=self.desk.plans[key]['events'][:3])
        args={'experiment':key,'mode':'simulation','request_id':'same-request'}
        with self.assertRaises(HTTPError) as error:self.request('/api/run',args)
        self.assertEqual(error.exception.code,400);self.assertEqual(self.request('/api/status')['recent'],[])
    def test_arbitrary_script_and_file_paths_are_not_accepted(self):
        with self.assertRaises(HTTPError):self.request('/api/plan?id=../../profile.json')
        with self.assertRaises(HTTPError):self.request('/api/run',{'experiment':'import os','mode':'simulation','request_id':'invalid'})
        with self.assertRaises(HTTPError):self.request('/api/frame')
    def test_invalid_preview_value_fails(self):
        with self.assertRaises(HTTPError):self.request('/api/preview-light',{'command':'intensity','value':-1})
        self.assertEqual(self.desk.preview['intensity'],0)
