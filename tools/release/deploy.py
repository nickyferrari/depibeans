"""Publish tracked web files from an immutable commit, or restore a release receipt.

python3 tools/release/deploy.py deploy --ref HEAD --config /private/targets.json
python3 tools/release/deploy.py rollback --receipt .runtime/releases/<id>.json
Python files require an explicitly configured maintenance release. No service restarts are performed.
"""
import argparse,hashlib,json,subprocess,tarfile,tempfile,time,shlex
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def cmd(args,**kw):return subprocess.run(args,check=True,**kw)
def ssh(t,line):cmd(['ssh',*t.get('options',[]),t['host'],line])
def remote(t,stage,mode):ssh(t,'python3 '+shlex.quote(stage+'/remote.py')+' '+shlex.quote(stage)+' '+mode)
def deploy(ref,config):
 commit=subprocess.check_output(['git','rev-parse',ref+'^{commit}'],cwd=ROOT,text=True).strip()
 ident=commit[:12]+'-'+str(time.time_ns()); receipt=ROOT/'.runtime/releases'/f'{ident}.json';receipt.parent.mkdir(parents=True,exist_ok=True)
 targets=json.loads(Path(config).read_text())['targets']; records=[]
 with tempfile.TemporaryDirectory() as tmp:
  tmp=Path(tmp); archive=tmp/'git.tar'
  with archive.open('wb') as f:cmd(['git','archive',commit],cwd=ROOT,stdout=f)
  source=tmp/'source';source.mkdir()
  with tarfile.open(archive) as tf:tf.extractall(source,filter='data')
  cmd(['node','--check',str(source/'depibeans/ui/dist/app.js')])
  try:
   for i,t in enumerate(targets):
    stage=t['releases'].rstrip('/')+'/'+ident
    bundle=tmp/str(i);(bundle/'files').mkdir(parents=True)
    # Derive preimages from Git, never accept arbitrary live hashes as the baseline.
    baseline=t.get('baseline_ref')
    if not baseline:
     manifest=subprocess.check_output(['ssh',*t.get('options',[]),t['host'],'cat '+shlex.quote(t['root'].rstrip('/')+'/.depi-web-release.json')],text=True)
     baseline=json.loads(manifest)['commit']
    baseline=subprocess.check_output(['git','rev-parse',baseline+'^{commit}'],cwd=ROOT,text=True).strip()
    expected={}
    for src,dst in t['files'].items():
     if dst in t.get('initialize',[]):
      expected[dst]=None  # Remote prepare refuses if the new destination already exists.
      continue
     data=subprocess.check_output(['git','show',baseline+':'+src],cwd=ROOT)
     expected[dst]=hashlib.sha256(data).hexdigest()
    if t.get('expected') and any(expected.get(k)!=v for k,v in t['expected'].items()):
     raise ValueError('Configured hashes differ from Git baseline; preserve and reconcile live edits first')
    hashes={}
    for src,dst in t['files'].items():
     p=Path(src);q=Path(dst)
     if p.is_absolute() or q.is_absolute() or '..' in p.parts or '..' in q.parts:raise ValueError('Unsafe target path')
     data=(source/p).read_bytes()
     if p.suffix=='.py':compile(data,str(p),'exec')
     out=bundle/'files'/q;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(data);hashes[dst]=hashlib.sha256(data).hexdigest()
    # Release identity is installed and rolled back alongside the assets.
    name='.depi-web-release.json';data=json.dumps({'commit':commit,'files':hashes},indent=2).encode();(bundle/'files'/name).write_bytes(data);hashes[name]=hashlib.sha256(data).hexdigest()
    (bundle/'spec.json').write_text(json.dumps({'root':t['root'],'commit':commit,'files':hashes,'expected':expected,'baseline_commit':baseline}))
    (bundle/'remote.py').write_bytes((source/'tools/release/remote.py').read_bytes())
    packed=tmp/f'{i}.tar'
    with tarfile.open(packed,'w') as tf:
     for child in bundle.iterdir():tf.add(child,arcname=child.name)
    ssh(t,'mkdir -p '+shlex.quote(stage))
    cmd(['scp',*t.get('options',[]),str(packed),t['host']+':'+stage+'/bundle.tar'])
    ssh(t,'tar -xf '+shlex.quote(stage+'/bundle.tar')+' -C '+shlex.quote(stage))
    # Syntax check PHP before any live file changes.
    for dst in hashes:
     if dst.endswith('.php'):ssh(t,'php -l '+shlex.quote(stage+'/files/'+dst))
    remote(t,stage,'prepare');records.append({'target':t,'stage':stage})
    receipt.write_text(json.dumps({'commit':commit,'state':'prepared','records':records},indent=2))
   for item in records:remote(item['target'],item['stage'],'apply')
   receipt.write_text(json.dumps({'commit':commit,'state':'active','records':records},indent=2))
   for item in records:remote(item['target'],item['stage'],'unlock')
  except BaseException:
   for item in reversed(records):
    try:remote(item['target'],item['stage'],'abort')
    except Exception as e:print('Rollback needs attention:',e)
   raise
 print('Release receipt:',receipt)
def rollback(path):
 p=Path(path);r=json.loads(p.read_text())
 for item in reversed(r['records']):remote(item['target'],item['stage'],'rollback')
 r['state']='rolled-back';p.write_text(json.dumps(r,indent=2))
 print('Restored previous files; hashes verified.')
if __name__=='__main__':
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='operation',required=True)
 d=sub.add_parser('deploy');d.add_argument('--ref',required=True);d.add_argument('--config',required=True)
 b=sub.add_parser('rollback');b.add_argument('--receipt',required=True)
 a=p.parse_args()
 if a.operation=='deploy':deploy(a.ref,a.config)
 else:rollback(a.receipt)
