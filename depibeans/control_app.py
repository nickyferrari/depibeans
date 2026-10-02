"""Local Linux control desk. Loopback only; commissioning required for hardware.

This trusted workstation interface is not the internet-facing portal. It does
not execute submitted code or expose a shell. Experiment choices come from the
installed, previously compiled research plans.
"""
from contextlib import nullcontext
import argparse
import copy
import hashlib
import json
import math
import sqlite3
import os
import re
from pathlib import Path
import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from .execution import Journal
from .scripting import Experiment
from .live_view import LiveView
from .operations import Operations
from .workbench import Workbench,validate_plan,recipe_plan
from .run_exports import RunExports
from .capture_outcomes import CaptureCancelled

class ControlDesk:
    def __init__(self,root,profile):
        self.root=Path(root);self.profile_path=Path(profile)
        self.data=self.root/'data';self.data.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.job_lock=threading.Lock();self.run_lock=threading.Lock();self.analysis_lock=threading.Lock();self.event_pending=False;self.stop=threading.Event()
        self.live=LiveView(self.job_lock)
        self.workbench=Workbench(self.data/'workbench.sqlite3')
        self.exports=RunExports(self.data/'captures')
        self.started=time.time();self.operations=Operations(self.data/'operations.sqlite3');self.gallery_cache=(0,[])
        self.active=None;self.last_error=None;self.latest_frame=None;self.preview={'intensity':0,'FR':0,'UVA':0,'UVB':0}
        self.devices={'fpga_devices':[],'cameras':[],'checked_at':None,'errors':[]}
        self.plans={}
        research=Path(__file__).resolve().parent.parent/'examples/research'
        for file in sorted(research.glob('*.plan.json'),reverse=True):
            plan=json.loads(file.read_text());key=hashlib.sha256(file.name.encode()).hexdigest()[:16]
            self.plans[key]=plan
        self.database=self.data/'control-desk.sqlite3'
        journal=Journal(self.database)
        with journal.owner():
            interrupted=journal.db.execute("SELECT id FROM jobs WHERE state='running' ORDER BY created DESC LIMIT 1").fetchone()
            journal.recover()
            if interrupted:self.workbench.set_setting('last_run_end',{'id':interrupted['id'],'state':'interrupted','time':time.time(),'light':{'state':'not_sent','reason':'Controller restarted; last physical light state is unknown. Review required.'}})
        journal.close()
        self.load_latest_frame()

    def load_latest_frame(self):
        captures=self.data/'captures'
        selected=self.data/'display-frame.json'
        if selected.exists():
            try:
                record=json.loads(selected.read_text());frame=(captures/record['path']).resolve()
                if frame.is_relative_to(captures.resolve()) and frame.is_file():
                    self.latest_frame=record;return
            except (ValueError,KeyError,OSError):pass
        completed=[]
        for record in captures.glob('*/capture-*/metadata.json'):
            try:
                meta=json.loads(record.read_text())
                if meta.get('state')=='completed' and meta.get('frames'):
                    frame=(record.parent/meta['frames'][-1]['file']).resolve()
                    if frame.is_relative_to(captures.resolve()) and frame.is_file():
                        completed.append({'path':str(frame.relative_to(captures.resolve())), 'created':frame.stat().st_mtime})
            except (ValueError,KeyError,OSError):continue
        if completed:self.latest_frame=max(completed,key=lambda x:x['created'])

    def profile(self):
        profile=json.loads(self.profile_path.read_text())
        profile['live_preview']=self.workbench.setting('live_preview',{'exposure_us':250,'gain':12})
        return profile

    def workspace(self):
        p=self.profile()
        with self.workbench.db() as db:
            schedules=[dict(r) for r in db.execute('SELECT id,mode,due,state,actor,error FROM schedules ORDER BY due DESC LIMIT 100')]
        return {'preview':p['live_preview'],'preview_limits':{'exposure_us':[10,1000000],'gain':[0,33]},
            'camera':{k:v for k,v in p['camera'].items() if k!='transport_path'},
            'protocols':self.workbench.list('protocol'),'experiments':self.workbench.list('experiment'),
            'schedules':schedules,'profile':{k:p[k] for k in ('device_name','pins','limits','expected_clock_hz','commissioned','verified_controls','experiment_execution') if k in p},
            'storage':{'destination':'Local controller','remote_configured':False,'remote_label':'Kramer server: destination not configured'}}

    def run_records(self,offset=0):
        j=Journal(self.database)
        try:
            rows=j.db.execute('SELECT id,mode,state,created,plan FROM jobs ORDER BY created DESC,id LIMIT 40 OFFSET ?',(offset,)).fetchall()
            items=[]
            for row in rows:
                p=json.loads(row['plan']);counts=dict(j.db.execute('SELECT state,count(*) FROM attempts WHERE job=? GROUP BY state',(row['id'],)).fetchall())
                items.append({k:row[k] for k in ('id','mode','state','created')}|{'name':p['name'],'events':len(p['events']),'counts':counts})
            return {'items':items,'next_offset':offset+40 if len(items)==40 else None}
        finally:j.close()

    def job_report(self,key):
        j=Journal(self.database)
        try:
            result=j.status(key);row=j.db.execute('SELECT plan FROM jobs WHERE id=?',(key,)).fetchone()
            result['plan']=json.loads(row['plan']);result['termination']=self.workbench.setting('run_end:'+key,None)
            for a in result['attempts']:
                if a['result']:a['result']=json.loads(a['result'])
            prefix=hashlib.sha256(key.encode()).hexdigest()+'/'
            result['images']=[{k:v for k,v in r.items() if k!='path'} for r in self.gallery() if r['path'].startswith(prefix)]
            return result
        finally:j.close()

    def recovery_plan(self,key,omit_uncertain=False):
        report=self.job_report(key)
        if report['state'] not in ('paused','needs_review','pending'):raise ValueError('Only an unfinished, stopped run has remaining events')
        uncertain=[a['seq'] for a in report['attempts'] if a['state']=='uncertain']
        if uncertain and omit_uncertain is not True:raise ValueError('Review the uncertain events first, then explicitly choose to leave them out of the draft')
        pending=sorted((a for a in report['attempts'] if a['state'] in ('pending','cancelled')),key=lambda a:(a['intended'],a['seq']))
        if not pending:raise ValueError('There are no unattempted events to recover')
        plan=copy.deepcopy(report['plan']);plan['name']=(plan['name'][:145]+' · remaining events')
        start=pending[0]['intended'];events=[]
        for index,a in enumerate(pending):
            event=copy.deepcopy(report['plan']['events'][a['seq']]);event.update(sequence=index,relative=True,delay_ms=max(0,round((a['intended']-start)*1000)));events.append(event)
        plan.update(events=events,sections=[],hardware_execution_authorized=False,recovery={'source_job':key,'original_event_numbers':[a['seq']+1 for a in pending],'uncertain_events_omitted':[n+1 for n in uncertain],'completed_events_omitted':sum(a['state']=='completed' for a in report['attempts']),'initial_state_review_required':True})
        return {'plan':plan,'requires_initial_state_review':True,'note':'Draft only. Completed and uncertain events are excluded. Review initial light and camera settings before saving. Timing starts from the first remaining event.'}

    def workspace_action(self,data):
        op=data['operation'];actor=data.get('_actor','Local operator');w=self.workbench
        if op=='upload_chunk':return w.chunk(data,actor)
        if op=='recovery_plan':return self.recovery_plan(data['id'],data.get('omit_uncertain',False))
        if op in ('validate','save','recipe'):
            plan=w.assembled(data['upload'],actor) if data.get('upload') else data.get('plan')
            if op=='recipe':plan=recipe_plan(data['recipe'])
            result=validate_plan(plan,self.profile())
            if op=='save':result.update(w.save('experiment',result['plan'],actor,data.get('id'),data.get('version')))
            return result
        if op=='archive':return w.archive(data['id'],data['version'])
        if op=='schedule':
            if data.get('version') is not None and self.workbench.get(data['experiment'])['version']!=data['version']:raise ValueError('Experiment changed in another window; save again')
            plan=self.plan(data['experiment']);mode=data['mode'];due=data['due'];key=data['request_id']
            if mode != 'hardware':raise ValueError('Only real chamber execution can be scheduled')
            if not isinstance(key,str) or not 1<=len(key)<=128:raise ValueError('Request ID required')
            if mode not in ('simulation','hardware') or isinstance(due,bool) or not isinstance(due,(int,float)) or not math.isfinite(due) or not time.time()+10<=due<=time.time()+366*86400:raise ValueError('Choose a start at least 10 seconds ahead, within one year')
            result=validate_plan(plan,self.profile())
            if mode=='hardware' and not result['hardware_ready']:raise ValueError('; '.join(result['hardware_reasons']))
            with w.db() as db:
                old=db.execute('SELECT plan,mode,due FROM schedules WHERE id=?',(key,)).fetchone()
                encoded=json.dumps(result['plan'],sort_keys=True)
                if old and (old['plan'],old['mode'],old['due'])!=(encoded,mode,due):raise ValueError('Schedule ID reused with different settings')
                if not old:db.execute('INSERT INTO schedules VALUES(?,?,?,?,?,?,NULL)',(key,encoded,mode,due,'queued',actor))
            return {'id':key,'state':'queued','due':due}
        if op=='cancel_schedule':
            with w.db() as db:
                if not db.execute("UPDATE schedules SET state='cancelled' WHERE id=? AND state='queued'",(data['id'],)).rowcount:raise ValueError('Schedule already started or cancelled')
            return {'cancelled':True}
        if op=='discard':
            j=Journal(self.database)
            try:
                with j.owner(),j.transaction():
                    if not j.db.execute("UPDATE jobs SET state='discarded' WHERE id=? AND state IN ('paused','needs_review','pending')",(data['id'],)).rowcount:raise ValueError('Only stopped runs can be discarded')
                return {'discarded':True,'images_preserved':True}
            finally:j.close()
        if op=='resume':
            raise ValueError('Prepare a reviewed recovery plan before restarting chamber execution')
        if op=='calibration_fit':
            from .calibration import quadratic_fit
            samples=data['samples']
            if not isinstance(samples,list) or not 3<=len(samples)<=1000:raise ValueError('Use 3–1000 measured pairs')
            return {**quadratic_fit(samples),'uploaded_to_hardware':False}
        if op=='calibration_import':
            from .calibration import load_points,dump_points
            raw=w.assembled(data['upload'],actor) if data.get('upload') else data['document']
            normalized=json.loads(dump_points(load_points(json.dumps(raw))))
            w.set_setting('calibration_document',normalized)
            return {'points':len(normalized['calibration_data']),'uploaded_to_hardware':False}
        raise ValueError('Unknown workspace operation')

    def actor_authorized(self,actor):
        """Whether the account that queued a start may still start hardware.

        Only positive evidence revokes: a portal account marked disabled, or an approved-access
        list that no longer names the account. Local desk actors and accounts the portal does not
        track (hosted identities) keep their schedules, and a read problem never cancels a run.
        """
        if not actor or actor=='Local operator':return True
        portal=self.data/'portal'
        try:
            approved=portal/'approved-emails.json'
            if approved.is_file() and actor not in json.loads(approved.read_text()):return False
            users=portal/'portal.sqlite3'
            if users.is_file():
                db=sqlite3.connect(f'file:{users}?mode=ro',uri=True,timeout=2)
                try:
                    row=db.execute('SELECT enabled FROM users WHERE username=?',(actor,)).fetchone()
                    if row is not None and not row[0]:return False
                finally:db.close()
        except (OSError,ValueError,sqlite3.Error):pass
        return True

    def scheduler_tick(self):
        w=self.workbench
        with self.operations.lock:
            with w.db() as db:
                row=db.execute("SELECT * FROM schedules WHERE state='queued' AND due<=? ORDER BY due LIMIT 1",(time.time(),)).fetchone()
                if not row:return
                db.execute("UPDATE schedules SET state='dispatching' WHERE id=?",(row['id'],))
            try:
                if time.time()-row['due']>30:raise ValueError('Scheduled start was missed; review and schedule again')
                # Authority is rechecked at dispatch: disabling an account also stops what it queued.
                if not self.actor_authorized(row['actor']):raise PermissionError('Scheduling account is no longer authorized; schedule again from an active account')
                if self.active:raise ValueError('Chamber was busy at scheduled start; review and schedule again')
                result=self.start(json.loads(row['plan']),row['mode'],row['id'])
                outcome='started';error=None
                self.operations.record(row['actor'],'/api/run',{'operation':'scheduled_start','mode':row['mode']},row['id'],'accepted')
            except PermissionError as exc:
                outcome='cancelled';error=str(exc)
                self.operations.record(row['actor'],'/api/run',{'operation':'scheduled_start','mode':row['mode']},row['id'],'rejected')
            except Exception as exc:outcome='missed';error=str(exc)
            with w.db() as db:db.execute('UPDATE schedules SET state=?,error=? WHERE id=?',(outcome,error,row['id']))

    def scheduler_loop(self):
        while True:
            try:self.scheduler_tick()
            except Exception as exc:self.last_error='Scheduler: '+str(exc)
            time.sleep(1)


    def refresh(self):
        if self.active:raise ValueError('Device discovery is unavailable while an experiment is running')
        if not self.job_lock.acquire(blocking=False):raise ValueError('Wait for the current run to finish before checking devices')
        try:
            found={'fpga_devices':[],'cameras':[],'checked_at':time.time(),'errors':[]}
            try:
                from .linux_adept import LinuxNative
                found['fpga_devices']=LinuxNative().devices()
            except Exception as exc:found['errors'].append('FPGA: '+str(exc))
            try:
                from .avt_camera import discover
                camera=discover(self.profile()['camera']['transport_path'])
                found['cameras']=camera.get('cameras',[])
            except Exception as exc:found['errors'].append('Camera: '+str(exc))
            with self.lock:self.devices=found
            return self.status()
        finally:self.job_lock.release()

    def status(self):
        p=self.profile();disk=shutil.disk_usage(self.data)
        j=Journal(self.database)
        try:
            recent=[]
            for row in j.db.execute('SELECT id,mode,state,created,plan FROM jobs ORDER BY created DESC LIMIT 6'):
                plan=json.loads(row['plan']);counts=dict(j.db.execute('SELECT state,count(*) FROM attempts WHERE job=? GROUP BY state',(row['id'],)).fetchall())
                recent.append({'id':row['id'],'mode':row['mode'],'state':row['state'],'created':row['created'],'name':plan['name'],'events':len(plan['events']),'counts':counts})
        finally:j.close()
        with self.lock:
            return {'chamber':p.get('chamber','DEPI 1'),'chamber_id':p.get('chamber_id','depi-one'),'uptime_seconds':time.time()-self.started,'progress':self.progress(), 'last_command':self.last_command(), 'health':self.health(),'hostname':os.uname().nodename,'commissioned':p.get('commissioned') is True,'experiment_ready':p.get('experiment_execution',{}).get('enabled') is True,'experiment_limits':p.get('experiment_execution',{}),'event_pending':self.event_pending,'run_end':self.workbench.setting('last_run_end',None),'last_commanded_light':self.workbench.setting('last_commanded_light',None),
                'devices':copy.deepcopy(self.devices),'preview':dict(self.preview),'active':copy.deepcopy(self.active),
                'last_error':self.last_error,'recent':recent,'free_gb':round(disk.free/1024**3,1),
                'limits':p.get('limits',{}),'scripts':len(self.plans)+len(self.workbench.list('experiment')),'server_time':time.time(),
                'manual_light_ready':p.get('commissioned') is True or p.get('verified_controls',{}).get('main_light') is True,
                'verified_controls':p.get('verified_controls',{}),'migration_complete':False,'physical_state':'Not verified','latest_frame':self.latest_frame,'live':self.live.status(),'live_ready':p.get('verified_controls',{}).get('live_view') is True,
                'measuring_burst_ready':p.get('verified_controls',{}).get('measuring_burst') is True and bool(p.get('camera',{}).get('measuring_burst',{}).get('fields')),'camera_capture_ready':(p.get('commissioned') is True or p.get('verified_controls',{}).get('snapshot') is True) and bool(p.get('camera',{}).get('preview_protocol'))}

    def health(self):
        result={'memory_available_mb':None,'memory_total_mb':None,'load_1m':os.getloadavg()[0]}
        try:
            mem=dict((line.split(':')[0],int(line.split()[1])) for line in Path('/proc/meminfo').read_text().splitlines())
            result.update(memory_available_mb=round(mem['MemAvailable']/1024),memory_total_mb=round(mem['MemTotal']/1024))
        except (OSError,ValueError,KeyError):pass
        return result

    def progress(self):
        active=self.active
        if not active:return None
        j=Journal(self.database)
        try:
            job=j.status(active['id']);row=j.db.execute('SELECT plan FROM jobs WHERE id=?',(active['id'],)).fetchone();plan=json.loads(row['plan'])
            attempts=job['attempts'];current=next((a for a in attempts if a['state']=='running'),None)
            next_event=next((a for a in sorted(attempts,key=lambda a:(a['intended'],a['seq'])) if a['state']=='pending'),None)
            def describe(a):
                if not a:return None
                return {'step':a['seq']+1,'due':a['intended'],'event':plan['events'][a['seq']]}
            return {'id':job['id'],'state':job['state'],'started':job['created'],'total':len(attempts),'completed':sum(a['state']=='completed' for a in attempts),'current':describe(current),'next':describe(next_event),'next_measurement':describe(next((a for a in sorted(attempts,key=lambda a:(a['intended'],a['seq'])) if a['state']=='pending' and plan['events'][a['seq']]['kind']=='capture'),None))}
        finally:j.close()

    def last_command(self):
        record=self.operations.last_light()
        if not record:
            j=Journal(self.database)
            try:
                for row in j.db.execute("SELECT j.plan,j.id,a.seq,a.ended FROM attempts a JOIN jobs j ON j.id=a.job WHERE j.mode='hardware' AND a.state='completed' ORDER BY a.ended DESC LIMIT 200"):
                    event=json.loads(row['plan'])['events'][row['seq']]
                    if event.get('command')=='intensity':return {'detail':{'command':'intensity','value':event['value']},'created':row['ended'],'request_id':row['id'],'execution':'completed','actor':None}
            finally:j.close()
            return None
        j=Journal(self.database)
        try:
            try:record['execution']=j.status(record['request_id'])['state']
            except ValueError:record['execution']='unknown'
        finally:j.close()
        return record

    def history(self,before=None):
        rows=self.operations.recent(before=before);j=Journal(self.database)
        try:
            for row in rows:
                if row['request_id'] and row['outcome']=='accepted':
                    try:
                        job=j.status(row['request_id']);row['execution']=job['state'];row['completed_events']=sum(a['state']=='completed' for a in job['attempts'])
                        row['errors']=[json.loads(a['result']).get('error') for a in job['attempts'] if a['state']=='uncertain' and a['result']]
                    except ValueError:pass
            return {'items':rows,'next_before':rows[-1]['id'] if len(rows)==100 else None}
        finally:j.close()

    def gallery(self):
        now=time.monotonic()
        if now-self.gallery_cache[0]<15:return self.gallery_cache[1]
        root=(self.data/'captures').resolve();items=[]
        j=Journal(self.database)
        try:names={hashlib.sha256(row['id'].encode()).hexdigest():json.loads(row['plan'])['name'] for row in j.db.execute('SELECT id,plan FROM jobs')}
        finally:j.close()
        for meta_path in root.glob('*/capture-*/metadata.json'):
            try:
                meta=json.loads(meta_path.read_text())
                if meta.get('state')!='completed':continue
                for frame in meta.get('averages',[])+meta.get('frames',[]):
                    file=(meta_path.parent/frame['file']).resolve()
                    if not file.is_relative_to(root) or not file.is_file():continue
                    rel=str(file.relative_to(root));items.append({'id':hashlib.sha256(rel.encode()).hexdigest(),'path':rel,'created':file.stat().st_mtime,'bytes':file.stat().st_size,'experiment':names.get(file.relative_to(root).parts[0],meta.get('experiment','Saved capture')),'filename':file.name,**{k:frame[k] for k in ('kind','label','phase','frame_count','display_max','clipped_fraction') if k in frame}})
            except (OSError,ValueError,KeyError):continue
        from .fluorescence import images
        items.extend(images(root))
        items.sort(key=lambda x:x['created'],reverse=True);self.gallery_cache=(now,items)
        return items

    def saved_frame(self,key):
        for item in self.gallery():
            if item['id']==key:return item
        self.gallery_cache=(0,[])
        for item in self.gallery():
            if item['id']==key:return item
        raise ValueError('Saved image not found')

    def catalog(self):
        items=[]
        for key,p in sorted(self.plans.items(),key=lambda item:(re.search(r'\d{4}-\d{2}-\d{2}T[0-9.]+',item[1]['name']).group(0) if re.search(r'\d{4}-\d{2}-\d{2}T[0-9.]+',item[1]['name']) else item[1]['name']),reverse=True):
            items.append({'id':key,'name':p['name'],'events':len(p['events']),'captures':sum(e['kind']=='capture' for e in p['events']),'duration_ms':max(e['delay_ms'] for e in p['events']),'editable':False})
        for item in reversed(self.workbench.list('experiment')):
            p=self.workbench.get(item['id'])['body']
            items.insert(0,{**item,'events':len(p['events']),'captures':sum(e['kind']=='capture' for e in p['events']),'duration_ms':max(e['delay_ms'] for e in p['events']),'editable':True})
        return items

    def plan(self,key):
        if key in self.plans:return copy.deepcopy(self.plans[key])
        doc=self.workbench.get(key)
        if doc['kind']!='experiment':raise ValueError('Not an experiment')
        return doc['body']

    def preview_light(self,command,value):
        if command not in self.preview or isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not 0<=value<=1000:raise ValueError('Preview intensity must be between 0 and 1000')
        with self.lock:self.preview[command]=value
        return {'preview':dict(self.preview),'physical_output_sent':False}

    def start(self,plan,mode,request_id):
        if self.live.status()['error'] and self.live.status()['error'].startswith('Camera restore failed:'):raise ValueError('Camera restoration needs maintenance')
        if mode != 'hardware':raise ValueError('Only real chamber execution is supported')
        if not isinstance(request_id,str) or not request_id or len(request_id)>128:raise ValueError('A request ID is required')
        if mode=='hardware':
            if plan.get('recovery',{}).get('initial_state_review_required'):raise ValueError('Review and specify the initial light/camera state before running a recovery plan')
            from .chamber_adapter import ChamberAdapter
            adapter=ChamberAdapter(self.profile(),self.data/'captures');adapter.validate(plan)
            if plan.get('execution'):
                check=validate_plan(plan,self.profile());cam=self.profile()['camera']
                if check['frames']*cam['width']*cam['height']*2*1.2>shutil.disk_usage(self.data).free:raise ValueError('Insufficient image storage for this experiment')
        if self.live.status()['error'] and self.live.status()['error'].startswith('Camera restore failed:'):raise ValueError('Camera restoration needs maintenance')
        if not self.run_lock.acquire(blocking=False):raise ValueError('Another run is active')
        j=Journal(self.database)
        try:
            fresh=j.enqueue(request_id,plan,mode=mode)
            result=j.status(request_id)
        except Exception:
            self.run_lock.release();raise
        finally:j.close()
        if not fresh:
            self.run_lock.release();return result
        with self.lock:
            self.active={'id':request_id,'name':plan['name'],'mode':mode};self.last_error=None;self.stop.clear()
        result_start=min(a['intended'] for a in result['attempts'])
        def worker():
            journal=Journal(self.database)
            desk=self
            class EventOwner:
                mode='hardware'
                def validate(owner,p):return adapter.validate(p)
                def lead_seconds(owner,event):return adapter.lead_seconds(event)
                def recoverable_capture_error(owner,exc):return adapter.recoverable_capture_error(exc)
                def capture_timing(owner):return getattr(adapter,'last_capture_timing',{})
                def execute(owner,event,job,seq):
                    desk.event_pending=True
                    try:
                        adapter.last_capture_timing={'intended_trigger':owner.target_time,'actual_trigger':None,'trigger_sent':False}
                        was_live=event['kind']=='capture' and desk.live.status()['running']
                        if was_live:desk.live.stop()
                        if desk.live.status()['error'] and 'restore' in desk.live.status()['error'].lower():raise RuntimeError(desk.live.status()['error'])
                        with (desk.job_lock if event['kind']=='capture' else nullcontext()):
                            if was_live and event['kind']=='capture':
                                if desk.stop.wait(6):raise CaptureCancelled('Acquisition cancelled during camera release')
                            adapter.target_time=owner.target_time;adapter.cancel=owner.cancel
                            result=adapter.execute(event,job,seq)
                            if event['kind']=='set':desk.workbench.set_setting('last_commanded_light',{'command':event['command'],'value':event['value'],'time':time.time(),'physical_output_verified':False})
                        if event['kind']=='capture' and plan.get('execution'):
                            def analyze():
                                try:
                                    from .fluorescence import analyze_run
                                    with desk.analysis_lock:analyze_run(desk.data/'captures'/hashlib.sha256(job.encode()).hexdigest(),plan,run_start=result_start)
                                except Exception as exc:
                                    with desk.lock:desk.last_error='Analysis: '+str(exc)
                            threading.Thread(target=analyze,daemon=True).start()
                        return result
                    finally:desk.event_pending=False
            try:journal.run(request_id,EventOwner(),accelerate=False,stop=self.stop.is_set)
            except Exception as exc:
                with self.lock:self.last_error=str(exc)
            finally:
                try:
                    outcome=journal.status(request_id)['state']
                    if plan.get('execution'):
                        termination={'id':request_id,'name':plan['name'],'state':outcome,'time':time.time()}
                        if outcome not in ('completed','completed_with_errors'):
                            termination['light']=adapter.stop_lighting(plan['execution'].get('on_stop_light',0))
                            if termination['light']['state']=='completed':self.workbench.set_setting('last_commanded_light',{'command':'intensity','value':termination['light']['requested'],'time':time.time(),'physical_output_verified':False})
                        else:termination['light']={'state':'plan_completed','requested':adapter.settings.get('intensity'),'physical_output_verified':False}
                        self.workbench.set_setting('run_end:'+request_id,termination);self.workbench.set_setting('last_run_end',termination)
                    if hasattr(adapter,'close'):adapter.close()
                    capture_root=self.data/'captures'/hashlib.sha256(request_id.encode()).hexdigest()
                    if plan.get('execution'):
                        try:
                            from .fluorescence import analyze_run
                            with self.analysis_lock:analyze_run(capture_root,plan,run_start=result_start)
                        except Exception as exc:self.last_error='Analysis: '+str(exc)
                    for metadata_file in sorted(capture_root.glob('capture-*/metadata.json')):
                        metadata=json.loads(metadata_file.read_text())
                        if metadata.get('state')=='completed' and metadata.get('frames'):
                            frame=metadata_file.parent/metadata['frames'][-1]['file']
                            if frame.is_file():
                                import tifffile
                                pixels=tifffile.imread(frame)
                                # Keep every raw frame; only the overview preview is held on a nearly black snapshot.
                                if plan['name']=='Camera snapshot' and float(pixels.mean())<128:
                                    self.last_error='The new snapshot is nearly black. The previous image remains displayed; the new raw TIFF is saved for review.'
                                else:
                                    self.latest_frame={'path':str(frame.relative_to(self.data/'captures')),'created':frame.stat().st_mtime}
                                    temp=self.data/'display-frame.tmp';temp.write_text(json.dumps(self.latest_frame));temp.replace(self.data/'display-frame.json')
                finally:
                    journal.close()
                    with self.lock:self.active=None
                    self.run_lock.release()
        threading.Thread(target=worker,daemon=True).start()
        return result

    def action(self,path,data):
        actor=data.get('_actor','Local operator')
        with self.operations.lock:
            detail={key:data[key] for key in ('command','value','experiment','mode','view','action','operation','id') if key in data}
            record=self.operations.record(actor,path,detail,data.get('request_id'),'received')
            try:result=self._action(path,data)
            except Exception as exc:
                self.operations.finish(record,'rejected: '+str(exc))
                raise
            self.operations.finish(record,'accepted')
            return result

    def _action(self,path,data):
        if path=='/api/refresh':return self.refresh()
        if path=='/api/preview-light':raise ValueError('Preview-only lighting is unavailable; use verified chamber control')
        if path=='/api/run':
            if data.get('operation'):return self.workspace_action(data)
            if data.get('version') is not None and self.workbench.get(data['experiment'])['version']!=data['version']:raise ValueError('Experiment changed in another window; save again')
            plan=self.plan(data.get('experiment'))
            checked=validate_plan(plan,self.profile())
            if not checked['hardware_ready']:raise ValueError('; '.join(checked['hardware_reasons']))
            frames=checked['frames'];cam=self.profile()['camera']
            if frames*cam['width']*cam['height']*2*1.2>shutil.disk_usage(self.data).free:raise ValueError('Insufficient image storage for this experiment')
            return self.start(checked['plan'],data.get('mode'),data.get('request_id'))
        if path=='/api/capture':
            profile=self.profile()
            op=data.get('operation')
            if op=='measuring_burst':
                if profile.get('verified_controls',{}).get('measuring_burst') is not True:raise ValueError('Measuring burst is not verified on this chamber')
                fields=profile.get('camera',{}).get('measuring_burst',{}).get('fields')
                if not fields:raise ValueError('Missing verified measuring protocol')
                e=Experiment('Measuring burst · 10-frame average');e.protocol('measuring-burst',fields,analysis='Unclassified measuring fluorescence');e.capture('measuring-burst')
                return self.start(e.compile(),'hardware',data.get('request_id'))
            if op=='preview_settings':
                settings={key:data[key] for key in ('exposure_us','gain')}
                for key,lo,hi in [('exposure_us',10,1000000),('gain',0,33)]:
                    value=settings[key]
                    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not lo<=value<=hi:raise ValueError(f'{key} must be between {lo} and {hi}')
                if self.active:raise ValueError('Wait for the active run before changing preview settings')
                restart=self.live.status()['running']
                if restart:self.live.stop()
                if self.live.status()['error'] and self.live.status()['error'].startswith('Camera restore failed:'):raise ValueError('Camera restoration needs maintenance')
                self.workbench.set_setting('live_preview',settings)
                if restart:self.live.start(self.profile(),data['request_id'])
                return {'requested':settings,'applied':False,'readback':'Available with the next live frame'}
            if op in ('protocol_save','protocol_validate','protocol_capture'):
                proto=data['protocol'];fields=proto['fields']
                e=Experiment('Capture '+proto['name']);e.protocol('capture',fields,analysis=proto.get('analysis'),group=proto.get('group','*'),sensors=proto.get('sensors',['*']));e.capture('capture')
                result=validate_plan(e.compile(),profile)
                from .chamber_adapter import ChamberAdapter
                try:
                    ChamberAdapter(profile,self.data/'captures').validate(result['plan'])
                    result['hardware_ready']=True;result['hardware_reasons']=[]
                except (ValueError,KeyError,TypeError) as exc:
                    result['hardware_ready']=False;result['hardware_reasons']=[str(exc)]
                if op=='protocol_save':result.update(self.workbench.save('protocol',proto,data.get('_actor','Local operator'),data.get('id'),data.get('version')))
                if op=='protocol_capture':
                    if not result['hardware_ready']:raise ValueError('; '.join(result['hardware_reasons']))
                    return self.start(result['plan'],'hardware',data['request_id'])
                return result
            if op:raise ValueError('Unknown camera operation')
            if data.get('view')=='live':
                if data.get('action')=='stop':return self.live.stop()
                if data.get('action')!='start':raise ValueError('Unknown live action')
                if profile.get('verified_controls',{}).get('live_view') is not True:raise ValueError('Live camera mode has not been verified')
                next_capture=self.progress().get('next_measurement') if self.active and self.progress() else None
                if self.event_pending or (next_capture and next_capture['due']-time.time()<=40):raise ValueError('Measurement preparation reserved; live view resumes afterwards')
                return self.live.start(profile,data.get('request_id'))
            if not self.status()['camera_capture_ready']:raise ValueError('Camera preview has not been commissioned')
            e=Experiment('Camera snapshot');e.protocol('snapshot',profile['camera']['preview_protocol']);e.capture('snapshot')
            return self.start(e.compile(),'hardware',data.get('request_id'))
        if path=='/api/light':
            e=Experiment('Manual lighting');e.set(data.get('command'),data.get('value'))
            return self.start(e.compile(),'hardware',data.get('request_id'))
        if path=='/api/stop':
            self.stop.set();return {'stop_requested':True,'takes_effect':'At next event boundary; in-flight acquisition can finish'}
        raise ValueError('Unknown action')

class Handler(BaseHTTPRequestHandler):
    server_version='DepiBeans'
    def allowed(self):
        authorities={f'{host}:{port}' for host in ('127.0.0.1','localhost') for port in (self.server.server_port,18951)}
        if self.headers.get('Host') not in authorities:return False
        origin=self.headers.get('Origin')
        return origin is None or origin in {'http://'+authority for authority in authorities}
    def respond(self,code,data,kind='application/json',extra_headers=None):
        if kind=='application/json':data=json.dumps(data,allow_nan=False).encode()
        self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; font-src 'self' data:; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        for key,value in (extra_headers or {}).items():self.send_header(key,str(value))
        self.end_headers();self.wfile.write(data)
    def do_GET(self):
        if not self.allowed():return self.respond(403,{'error':'Local access only'})
        path=urlsplit(self.path).path
        try:
            if path=='/api/frame' and parse_qs(urlsplit(self.path).query).get('view')==['live']:
                payload,created,sequence=self.server.desk.live.frame()
                return self.respond(200,payload,'image/png',{'X-Frame-Created':created,'X-Frame-Sequence':sequence})
            if path=='/api/frame.tif' and parse_qs(urlsplit(self.path).query).get('view')==['bundle']:
                q=parse_qs(urlsplit(self.path).query);key=q.get('id',[''])[0];report=self.server.desk.job_report(key)
                if report['state'] in ('pending','running'):raise ValueError('Wait for the run to stop before exporting its files')
                return self.respond(200,self.server.desk.exports.archive(report,int(q.get('part',['0'])[0])),'application/zip')
            if path in ('/api/frame','/api/frame.tif'):
                key=parse_qs(urlsplit(self.path).query).get('id',[None])[0]
                record=self.server.desk.saved_frame(key) if key else self.server.desk.latest_frame
                if not record:return self.respond(404,{'error':'No completed capture on this controller'})
                if path=='/api/frame.tif':return self.respond(200,(self.server.desk.data/'captures'/record['path']).read_bytes(),'image/tiff')
                from .frame_preview import mono12_png
                return self.respond(200,mono12_png(self.server.desk.data/'captures'/record['path'],display_max=record.get('display_max',4095),display_min=record.get('display_min',0),masked=record.get('masked',False),color=record.get('color',False)),'image/png')
            if path=='/api/status':
                query=parse_qs(urlsplit(self.path).query)
                if query.get('view')==['fluorescence']:
                    from .fluorescence import datasets
                    items=datasets(self.server.desk.data/'captures')
                    latest=next((r for r in self.server.desk.gallery() if r.get('kind')=='mean'),None)
                    return self.respond(200,{'datasets':items,'last_completed':{k:v for k,v in latest.items() if k!='path'} if latest else None})
                if query.get('view')==['bundle']:
                    key=query.get('id',[''])[0];self.server.desk.job_report(key)
                    return self.respond(200,self.server.desk.exports.index(key))
                if query.get('view')==['revisions']:return self.respond(200,self.server.desk.workbench.revisions(query.get('id',[''])[0]))
                if query.get('view')==['revision']:return self.respond(200,self.server.desk.workbench.revision(query.get('id',[''])[0],int(query.get('version',['0'])[0])))
                if query.get('view')==['workspace']:return self.respond(200,self.server.desk.workspace())
                if query.get('view')==['runs']:return self.respond(200,self.server.desk.run_records(max(0,int(query.get('offset',['0'])[0]))))
                if query.get('view')==['job']:return self.respond(200,self.server.desk.job_report(query.get('id',[''])[0]))
                if query.get('view')==['document']:return self.respond(200,self.server.desk.workbench.get(query.get('id',[''])[0]))
                if query.get('view')==['calibration']:return self.respond(200,self.server.desk.workbench.setting('calibration_document',{'calibration_data':[]}))
                if query.get('view')==['gallery']:
                    offset=max(0,int(query.get('offset',['0'])[0]));items=self.server.desk.gallery()
                    day=query.get('day',[''])[0];search=query.get('q',[''])[0].lower()
                    if query.get('kind')==['mean']:items=[r for r in items if r.get('kind')=='mean']
                    if day:items=[r for r in items if time.strftime('%Y-%m-%d',time.localtime(r['created']))==day]
                    if search:items=[r for r in items if search in r['experiment'].lower()]
                    return self.respond(200,{'items':[{k:v for k,v in r.items() if k!='path'} for r in items[offset:offset+24]],'total':len(items),'next_offset':offset+24 if offset+24<len(items) else None})
                if query.get('view')==['history']:return self.respond(200,self.server.desk.history(int(query['before'][0]) if query.get('before') else None))
                return self.respond(200,self.server.desk.status())
            if path=='/api/account':return self.respond(200,{'username':'Local operator','role':'operator'})
            if path=='/api/experiments':return self.respond(200,self.server.desk.catalog())
            if path=='/api/plan':return self.respond(200,self.server.desk.plan(parse_qs(urlsplit(self.path).query).get('id',[''])[0]))
            assets={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
            if path not in assets:return self.respond(404,{'error':'Not found'})
            file,kind=assets[path];return self.respond(200,(Path(__file__).parent/'ui/dist'/file).read_bytes(),kind)
        except (ValueError,KeyError) as exc:self.respond(400,{'error':str(exc)})
        except Exception:self.respond(500,{'error':'Could not read controller state; check the service log'})
    def do_POST(self):
        if not self.allowed() or self.headers.get('X-DepiBeans')!='1':return self.respond(403,{'error':'Local application requests only'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=16384:raise ValueError('Invalid request size')
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict):raise ValueError('Expected a JSON object')
            self.respond(200,self.server.desk.action(urlsplit(self.path).path,data))
        except (ValueError,KeyError,TypeError) as exc:self.respond(400,{'error':str(exc)})
        except Exception:self.respond(500,{'error':'Action failed; inspect controller status before retrying'})


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path.home()/'DepiBeans');p.add_argument('--profile',type=Path);p.add_argument('--port',type=int,default=8765);a=p.parse_args()
    profile=a.profile or Path(__file__).resolve().parent.parent/'profiles/enterprise-linux.uncommissioned.json'
    desk=ControlDesk(a.root,profile)
    server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler);server.desk=desk
    threading.Thread(target=desk.refresh,daemon=True).start()
    threading.Thread(target=desk.scheduler_loop,daemon=True).start()
    print(f'DepiBeans Control: http://127.0.0.1:{a.port}',flush=True)
    server.serve_forever()

if __name__=='__main__':main()
