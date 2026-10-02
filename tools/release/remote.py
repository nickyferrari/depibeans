"""Remote file-only release helper. No service or hardware operations."""
import hashlib,json,os,shutil,sys
from pathlib import Path

def digest(p):
 return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None

def atomic_copy(src,dst):
 dst.parent.mkdir(parents=True,exist_ok=True)
 tmp=dst.with_name(dst.name+'.release-pending')
 shutil.copy2(src,tmp)
 os.replace(tmp,dst)

def run(stage,mode):
 stage=Path(stage); spec=json.loads((stage/'spec.json').read_text())
 root=Path(spec['root']); lock=root/'.depi-release-lock'; journal=stage/'journal.json'
 if mode=='prepare':
  lock.mkdir()  # refuse concurrent deployment
  (lock/'owner').write_text(str(stage))
  try:
   rows=[]
   manifest=root/'.depi-web-release.json'
   recorded=json.loads(manifest.read_text()).get('files',{}) if manifest.exists() else {}
   for rel,expected in recorded.items():
    path=Path(rel)
    if path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe recorded release path')
    if digest(root/path)!=expected:raise ValueError('Live drift from recorded release; preserve and reconcile before deploying: '+rel)
   for rel,expected in spec['files'].items():
    path=Path(rel)
    if path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe release path')
    src=stage/'files'/rel;dst=root/rel
    if digest(src)!=expected:raise ValueError('Staged hash mismatch: '+rel)
    old=digest(dst)
    if rel!='.depi-web-release.json' and rel not in spec.get('expected',{}):raise ValueError('Missing Git baseline: '+rel)
    if rel in spec.get('expected',{}) and old!=spec['expected'][rel]:raise ValueError('Live source differs from reviewed baseline: '+rel)
    if old is not None:atomic_copy(dst,stage/'backup'/rel)
    rows.append({'path':rel,'old':old,'new':expected})
   journal.write_text(json.dumps({'commit':spec['commit'],'state':'prepared','files':rows},indent=2))
  except BaseException:
   shutil.rmtree(lock);raise
 elif mode=='apply':
  if not lock.exists() or (lock/'owner').read_text()!=str(stage):raise ValueError('Missing deployment lock')
  j=json.loads(journal.read_text())
  for row in j['files']:
   if digest(root/row['path'])!=row['old']:raise ValueError('Live file changed: '+row['path'])
  j['state']='applying';journal.write_text(json.dumps(j))
  for row in j['files']:
   atomic_copy(stage/'files'/row['path'],root/row['path'])
   if digest(root/row['path'])!=row['new']:raise ValueError('Installed hash mismatch')
  j['state']='active';journal.write_text(json.dumps(j,indent=2))
 elif mode in ('rollback','abort'):
  if not lock.exists():
   lock.mkdir();(lock/'owner').write_text(str(stage))
  elif (lock/'owner').read_text()!=str(stage):raise ValueError('Another release owns the lock')
  j=json.loads(journal.read_text())
  if j['state'] in ('active','applying'):
   for row in j['files']:
    if digest(root/row['path']) not in (row['old'],row['new']):raise ValueError('Refusing to overwrite later changes: '+row['path'])
   for row in reversed(j['files']):
    dst=root/row['path']
    if row['old'] is None:dst.unlink(missing_ok=True)
    else:atomic_copy(stage/'backup'/row['path'],dst)
    if digest(dst)!=row['old']:raise ValueError('Rollback hash mismatch')
  j['state']='rolled-back';journal.write_text(json.dumps(j,indent=2))
  if lock.exists() and (lock/'owner').read_text()==str(stage):shutil.rmtree(lock)
 elif mode=='unlock':
  if lock.exists() and (lock/'owner').read_text()==str(stage):shutil.rmtree(lock)
 else:raise ValueError('Unknown operation')
 print(json.dumps({'operation':mode,'commit':spec['commit'],'stage':str(stage)}))
if __name__=='__main__':run(sys.argv[1],sys.argv[2])
