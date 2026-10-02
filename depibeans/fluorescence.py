"""Read completed, explicitly analysed fluorescence datasets; never infer missing Fs."""
import json,hashlib
from pathlib import Path

def datasets(captures):
 root=Path(captures).resolve();results=[]
 for path in root.glob('*/fluorescence.json'):
  try:
   if not path.resolve().is_relative_to(root):continue
   item=json.loads(path.read_text())
   if item.get('state')!='completed':continue
   item['id']=path.parent.name
   for metric in item.get('metrics',{}).values():
    for point in metric.get('points',[]):
     file=(path.parent/point.pop('file','')).resolve()
     if file.is_file() and file.is_relative_to(root):point['image_id']=hashlib.sha256(str(file.relative_to(root)).encode()).hexdigest()
   segmentation=item.get('segmentation',{})
   for field,target in (('detected_label_file','detected_image_id'),('measurement_label_file','measurement_image_id')):
    file=(path.parent/segmentation.get(field,'')).resolve()
    if file.is_file() and file.is_relative_to(root):segmentation[target]=hashlib.sha256(str(file.relative_to(root)).encode()).hexdigest()
   results.append(item)
  except (OSError,ValueError,KeyError,TypeError):continue
 return sorted(results,key=lambda item:item.get('completed_at',0),reverse=True)

def images(captures):
 root=Path(captures).resolve();items=[]
 for manifest in root.glob('*/fluorescence.json'):
  try:
   if not manifest.resolve().is_relative_to(root):continue
   data=json.loads(manifest.read_text())
   if data.get('state')!='completed':continue
   for metric in data.get('metrics',{}).values():
    for point in metric.get('points',[]):
     file=(manifest.parent/point.get('file','')).resolve()
     if not file.is_file() or not file.is_relative_to(root):continue
     rel=str(file.relative_to(root));items.append({'id':hashlib.sha256(rel.encode()).hexdigest(),'path':rel,'created':data['completed_at'],'bytes':file.stat().st_size,'experiment':data['name'],'filename':file.name,'kind':'analysis','label':metric['label'],'display_max':metric['display_max'],'display_min':metric.get('display_min',0),'color':metric.get('color',False),'masked':True})
   segmentation=data.get('segmentation',{})
   for field,label in (('detected_label_file','Detected leaf regions'),('measurement_label_file','Leaf measurement regions')):
    file=(manifest.parent/segmentation.get(field,'')).resolve()
    if not file.is_file() or not file.is_relative_to(root):continue
    rel=str(file.relative_to(root));items.append({'id':hashlib.sha256(rel.encode()).hexdigest(),'path':rel,'created':data['completed_at'],'bytes':file.stat().st_size,'experiment':data['name'],'filename':file.name,'kind':'segmentation','label':label,'display_max':255,'display_min':0,'color':False,'masked':False})
  except (OSError,ValueError,KeyError,TypeError):continue
 return items


def analyze_run(root,plan,run_start=None):
 """Incremental analysis of typed, completed captures. Never infer dark adaptation.

 Ratios require an explicit background plus a compatible dark-reference capture.
 Raw frames and per-phase arithmetic means are never modified.
 """
 import time
 import numpy as np
 import tifffile
 from .camera_protocol import expand,seconds,flag
 root=Path(root);root.mkdir(parents=True,exist_ok=True)
 manifest=root/'fluorescence.json';statefile=root/'analysis-state.json'
 labels={'F0':'F₀','Fm':'Fm','Fm_prime':'Fm′','Fs':'Fs','Fv':'Fv','Fv_Fm':'Fv/Fm','NPQ':'NPQ','PhiII':'ΦII','Measuring':'Measuring fluorescence','Background':'Background'}
 method='Measuring phases: arithmetic mean. Saturation phases: brightest contiguous window of up to 3 frames. No claim of physiological saturation.'
 data=json.loads(manifest.read_text()) if manifest.exists() else {'name':plan['name'],'state':'completed','completed_at':0,'qualification':'Automatic analysis. Background and compatible references required for ratios; dark adaptation is declared by the protocol type. Signal mask is not a plant identity mask.','metrics':{},'quality':[]}
 state=json.loads(statefile.read_text()) if statefile.exists() else {'processed':[],'background':None,'reference':None,'origin':run_start}
 data.setdefault('time_origin','run_start' if run_start is not None else 'first_capture');data.setdefault('run_start',run_start)
 def readfile(name):
  p=(root/name).resolve()
  if not p.is_relative_to(root.resolve()):raise ValueError('Analysis file outside capture directory')
  return tifffile.imread(p).squeeze().astype(np.float32)
 def atomic(path,obj):
  tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,indent=2,allow_nan=False));tmp.replace(path)
 def image_point(key,image,stamp,seq,explanation):
  finite=np.isfinite(image)
  if not finite.any():return None
  folder=root/'analysis';folder.mkdir(exist_ok=True)
  name=f'analysis/{seq:06d}-{key}.tif';tifffile.imwrite(root/name,image.astype(np.float32),photometric='minisblack')
  values=image[finite];ratio=key in ('NPQ','PhiII','Fv_Fm')
  item=data['metrics'].setdefault(key,{'label':labels[key],'units':'ratio' if ratio else 'camera units','points':[],'display_min':0,'display_max':1,'color':ratio,'method':explanation})
  item['method']=explanation;item['display_min']=min(item['display_min'],float(np.percentile(values,1)))
  item['display_max']=max(item['display_max'],float(np.percentile(values,99)))
  item['points'].append({'value':float(np.mean(values,dtype=np.float64)),'time_s':stamp-state['origin'],'label':f'{stamp-state["origin"]:.1f} s from '+('run start' if data['time_origin']=='run_start' else 'first capture'),'file':name,'capture_sequence':seq,'valid_pixels':int(finite.sum())})
  return name
 for meta_path in sorted(root.glob('capture-*/metadata.json')):
  seq=int(meta_path.parent.name.split('-')[-1]);token=meta_path.parent.name
  if token in state['processed']:continue
  meta=json.loads(meta_path.read_text())
  if meta.get('state')!='completed':
   if meta.get('state') in ('failed','cancelled','skipped'):
    data['quality'].append({'capture_sequence':seq,'state':meta['state'],'notes':[meta.get('error','Acquisition failed')],'intended_trigger':meta.get('intended_trigger'),'actual_trigger':meta.get('actual_trigger'),'trigger_sent':meta.get('trigger_sent'),'lateness_s':meta.get('trigger_lateness_s')});state['processed'].append(token);data['completed_at']=meta_path.stat().st_mtime;atomic(manifest,data);atomic(statefile,state)
   continue
  if not meta.get('protocol_fields'):continue
  kind=meta.get('measurement_type','custom');fields=meta['protocol_fields'];loops=int(fields['NumberLoops'])
  counts=expand(fields,'FramesPerLoop',loops,int);sats=expand(fields,'SaturationFlash',loops,flag);measuring=expand(fields,'MeasuringLight',loops,int)
  if sum(counts)!=len(meta['frames']):continue
  stamp=meta.get('actual_trigger') or meta_path.stat().st_mtime
  if state['origin'] is None:state['origin']=stamp
  signature=json.dumps({'exposure':expand(fields,'Exposure',loops,seconds)[0],'gain':meta.get('preview_feature_readback',{}).get('Gain'),'serial':meta.get('serial'),'width':meta.get('frames',[{}])[0].get('shape')},sort_keys=True)
  background=state.get('background');bg=readfile(background['file']) if background and background['signature']==signature else None
  phases=[];rawphases=[];offset=0;clipping=False
  for count,sat in zip(counts,sats):
   stack=np.stack([readfile(str((meta_path.parent/f['file']).relative_to(root))) for f in meta['frames'][offset:offset+count]]);offset+=count
   clipped=np.any(stack>=4095,axis=0);clipping=clipping or bool(clipped.any())
   if sat:
    scores=np.mean(stack,axis=(1,2));window=min(3,count);first=int(np.argmax(np.convolve(scores,np.ones(window)/window,mode='valid')));raw=np.mean(stack[first:first+window],axis=0)
   else:raw=np.mean(stack,axis=0)
   rawphases.append(raw);out=raw-(bg if bg is not None else 0);out[clipped]=np.nan;phases.append(out)
  explanation=method+(' Background subtracted.' if bg is not None else ' Uncorrected: acquire a matching background for derived ratios.')
  notes=[]
  if kind=='background' and all(not s and m==0 for s,m in zip(sats,measuring)):
   path=image_point('Background',rawphases[0],stamp,seq,'Mean camera background, measuring and saturation lights disabled by protocol.')
   if path:state['background']={'file':path,'signature':signature};state['reference']=None
  elif kind=='dark-reference' and len(phases)==2 and sats==[False,True] and measuring==[1,1]:
   f0,fm=phases;image_point('F0',f0,stamp,seq,explanation);image_point('Fm',fm,stamp,seq,explanation)
   if bg is not None:
    mask=np.isfinite(f0)&np.isfinite(fm)&(f0>16)&(fm>f0)
    f0m=np.where(mask,f0,np.nan);fmm=np.where(mask,fm,np.nan)
    refname=f'analysis/{seq:06d}-reference-Fm.tif';tifffile.imwrite(root/refname,fmm.astype(np.float32))
    image_point('Fv',fmm-f0m,stamp,seq,explanation+' Fv = Fm − F₀.')
    image_point('Fv_Fm',(fmm-f0m)/fmm,stamp,seq,explanation+' Fv/Fm = (Fm − F₀)/Fm; valid reference signal mask.')
    sat_signature=json.dumps({k:expand(fields,k,loops,seconds if k in ('Exposure','FrameInterval') else int)[1] for k in ('Exposure','FrameInterval','FramesPerLoop','MeasuringLight','ActinicShutter')},sort_keys=True)
    state['reference']={'file':refname,'signature':signature,'background':background['file'],'saturation':sat_signature}
   else:state['reference']=None;notes.append('Dark reference has no matching background; Fv/Fm and NPQ withheld.')
  elif kind in ('light-adapted','saturation'):
   paired=kind=='light-adapted' and len(phases)==2 and sats==[False,True] and measuring==[1,1]
   single=kind=='saturation' and len(phases)==1 and sats==[True] and measuring==[1]
   if paired or single:
    fmprime=phases[-1];image_point('Fm_prime',fmprime,stamp,seq,explanation)
    if paired:image_point('Fs',phases[0],stamp,seq,explanation)
    ref=state.get('reference');sat_signature=json.dumps({k:expand(fields,k,loops,seconds if k in ('Exposure','FrameInterval') else int)[-1] for k in ('Exposure','FrameInterval','FramesPerLoop','MeasuringLight','ActinicShutter')},sort_keys=True)
    valid=bg is not None and ref and ref['signature']==signature and ref['background']==background['file'] and ref['saturation']==sat_signature
    if valid:
     fm=readfile(ref['file']);mask=np.isfinite(fm)&np.isfinite(fmprime)&(fmprime>16);den=np.where(mask,fmprime,np.nan)
     image_point('NPQ',(fm-den)/den,stamp,seq,explanation+' NPQ = (dark Fm − Fm′)/Fm′; latest compatible dark reference.')
     if paired:image_point('PhiII',(den-phases[0])/den,stamp,seq,explanation+' ΦII = (Fm′ − Fs)/Fm′; shared dark-reference mask.')
    elif paired and bg is not None:
     fs=phases[0];den=np.where(np.isfinite(fs)&np.isfinite(fmprime)&(fs>16),fmprime,np.nan)
     image_point('PhiII',(den-fs)/den,stamp,seq,explanation+' ΦII = (Fm′ − Fs)/Fm′; local signal threshold mask.')
    if not valid:notes.append('NPQ withheld: no compatible background and dark Fm reference.')
   else:notes.append('Protocol phases do not match the declared measurement type; no physiological labels assigned.')
  elif kind=='measuring' and len(phases)==1 and not sats[0] and measuring[0]==1:
   image_point('Measuring',phases[0],stamp,seq,explanation+' Adaptation state unclassified.')
  else:notes.append('Custom acquisition retained as raw frames and phase averages.')
  if clipping:notes.append('Sensor-clipped pixels excluded from calculated images.')
  data['quality'].append({'capture_sequence':seq,'state':'completed','notes':notes,'trigger_sent':meta.get('trigger_sent'),'intended_trigger':meta.get('intended_trigger'),'actual_trigger':meta.get('actual_trigger'),'lateness_s':meta.get('trigger_lateness_s')})
  state['processed'].append(token);data['completed_at']=stamp
  # Each manifest contains only completed measurements, even while the run continues.
  atomic(manifest,data);atomic(statefile,state)
 try:
  from .leaf_segmentation import update_observation
  data=update_observation(root,data)
 except Exception as exc:
  # Segmentation is supplemental: preserve the completed whole-image analysis.
  data['segmentation']={'schema':'depibeans.leaf-segmentation/1','state':'unavailable','status':'unavailable','reason':f'{type(exc).__name__}: {exc}','measurement_inset_pixels':8}
  atomic(manifest,data)
 return data
