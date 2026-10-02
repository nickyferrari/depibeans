"""Hardware-blocked local preview of repository UI. Run: python3 preview/serve.py"""
import json,sys,os
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent
LOCAL=HERE
sys.path.insert(0,str(SOURCE))
from depibeans.control_app import ControlDesk, Handler
DIST=SOURCE/'depibeans/ui/dist'
DEPLOYED=False
BLOCKED='Local preview: chamber execution, scheduling, lights and camera access are disabled.'
class Desk(ControlDesk):
 def profile(self):
  p=super().profile();p['commissioned']=False;p['verified_controls']={};p['experiment_execution']['enabled']=False
  return p
 def refresh(self):return self.status()
 def start(self,*args,**kwargs):raise ValueError(BLOCKED)
 def scheduler_tick(self):raise ValueError(BLOCKED)
 def action(self,path,data):
  if path=='/api/run' and data.get('operation') in {'upload_chunk','validate','save','recipe','archive'}:
   return self.workspace_action(data)
  if path=='/api/capture' and data.get('operation') in {'protocol_save','protocol_validate'}:
   return super().action(path,data)
  if path=='/api/refresh':return self.status()
  raise ValueError(BLOCKED)
 def status(self):
  d=super().status();d.update(chamber='DEPI 1 · Local preview',physical_state='Disconnected',latest_frame={'created':(LOCAL/'fixtures/frame.png').stat().st_mtime},hostname='Local preview')
  return d
class LocalHandler(Handler):
 def do_POST(self):
  if os.environ.get('DEPI_HOSTED_OUTAGE_FIXTURE'):return self.respond(503,{'error':BLOCKED})
  return super().do_POST()
 def do_GET(self):
  if not self.allowed():return self.respond(403,{'error':'Local access only'})
  path=urlsplit(self.path).path
  outage=os.environ.get('DEPI_HOSTED_OUTAGE_FIXTURE')
  if outage:
   if path=='/api/connection':return self.respond(200,{'portal':'available','connection':'unavailable','last_contact':None})
   assets={'/':'rendered.html','/login':'rendered.html','/app.js':'rendered.js','/style.css':'rendered.css'}
   if path in assets:
    kind='text/javascript' if path=='/app.js' else 'text/css' if path=='/style.css' else 'text/html'
    return self.respond(200,(Path(outage)/assets[path]).read_bytes(),kind)
   return self.respond(503,{'error':'Disconnected chamber fixture. No hardware access.'})
  if path=='/':
   html=(DIST/'index.html').read_text()
   html=html.replace('<body>','<body><aside class="dev-banner">LOCAL PREVIEW · '+('deployed editor' if DEPLOYED else 'editor under development')+' · No chamber connection</aside>')
   html=html.replace('</body>', '<button id="verify-suite" style="position:fixed;bottom:5px;right:5px;z-index:10001">Run local verification</button><pre id="verify-results"></pre><script type="module" src="/__runner.js"></script></body>')
   return self.respond(200,html.encode(),'text/html; charset=utf-8')
  if path=='/app.js':
   js=(DIST/'app.js').read_text()
   return self.respond(200,js.encode(),'text/javascript; charset=utf-8')
  if path=='/style.css':
   css=(DIST/'style.css').read_bytes()+b'\n.dev-banner{padding:9px 18px;background:#233b32;color:white;font:12px system-ui;text-align:center;position:relative;z-index:9999}\n'
   return self.respond(200,css,'text/css')
  if path=='/__runner.js':return self.respond(200,(HERE/'runner.js').read_bytes(),'text/javascript; charset=utf-8')
  if path=='/__ui-test.js':return self.respond(200,(HERE/'ui-test.js').read_bytes(),'text/javascript; charset=utf-8')
  if path=='/api/frame':return self.respond(200,(LOCAL/'fixtures/frame.png').read_bytes(),'image/png')
  if path=='/api/frame.tif':return self.respond(404,{'error':'Synthetic preview has no scientific image export'})
  if path=='/api/account':return self.respond(200,{'username':'Local preview','role':'operator'})
  return super().do_GET()
if __name__=='__main__':
 desk=Desk(Path(__import__('os').environ.get('DEPI_PREVIEW_ROOT') or SOURCE/'.runtime/preview'),SOURCE/'profiles/enterprise-linux.manual.json')
 if not desk.workbench.list('experiment'):
  desk.workbench.save('experiment',json.loads((LOCAL/'fixtures/acceptance-plan.json').read_text()),'Local preview')
 server=ThreadingHTTPServer(('127.0.0.1',int(__import__('os').environ.get('DEPI_PREVIEW_PORT','18822'))),LocalHandler);server.desk=desk
 print('Graph editor preview: http://127.0.0.1:18822 - hardware blocked',flush=True)
 server.serve_forever()
