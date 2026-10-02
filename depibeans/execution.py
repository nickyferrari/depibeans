"""Durable one-chamber execution journal; adapters supply physical operations.

An interrupted attempt becomes uncertain and is never automatically replayed.
A successfully returned adapter call is recorded as completed, not physically
verified. Portal authentication belongs ahead of this local service boundary.
"""
from contextlib import contextmanager
from datetime import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from zoneinfo import ZoneInfo
from .capture_outcomes import CaptureCancelled,CaptureSkipped

class Journal:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.path,isolation_level=None)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, hash TEXT NOT NULL, plan TEXT NOT NULL,
            mode TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts(job TEXT NOT NULL, seq INTEGER NOT NULL, state TEXT NOT NULL,
            intended REAL NOT NULL, started REAL, ended REAL, result TEXT, PRIMARY KEY(job,seq));
        ''')

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:yield;self.db.execute('COMMIT')
        except BaseException:self.db.execute('ROLLBACK');raise

    @contextmanager
    def owner(self):
        with self.path.with_suffix('.controller.lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            try:yield
            finally:fcntl.flock(lock,fcntl.LOCK_UN)

    def enqueue(self,job_id,plan,*,mode='simulation',start=None,timezone='America/Detroit'):
        if mode not in {'simulation','hardware'}:raise ValueError('Invalid execution mode')
        if not job_id or len(job_id)>128:raise ValueError('Invalid request identifier')
        events=plan.get('events')
        if not isinstance(events,list) or not events:raise ValueError('Plan must have events')
        for e in events:
            if e.get('kind') not in {'set','capture'}:raise ValueError('Unsupported event kind')
            if type(e.get('delay_ms')) is not int or e['delay_ms']<0 or type(e.get('relative')) is not bool:raise ValueError('Invalid event timing')
        canonical=json.dumps({'plan':plan,'mode':mode,'timezone':timezone,'requested_start':start},sort_keys=True,allow_nan=False)
        digest=hashlib.sha256(canonical.encode()).hexdigest()
        start=time.time() if start is None else start
        midnight=datetime.fromtimestamp(start,ZoneInfo(timezone)).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        with self.transaction():
            previous=self.db.execute('SELECT hash FROM jobs WHERE id=?',(job_id,)).fetchone()
            if previous:
                if previous['hash']!=digest:raise ValueError('Request identifier reused with a different plan')
                return False
            self.db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)',(job_id,digest,json.dumps(plan),mode,'pending',time.time()))
            for seq,e in enumerate(events):
                due=(start if e['relative'] else midnight)+e['delay_ms']/1000
                self.db.execute('INSERT INTO attempts(job,seq,state,intended) VALUES(?,?,?,?)',(job_id,seq,'pending',due))
        return True

    def recover(self):
        """Call only under owner lock; freezes any interrupted hardware attempt."""
        with self.transaction():
            rows=self.db.execute("SELECT DISTINCT job FROM attempts WHERE state='running'").fetchall()
            for row in rows:
                self.db.execute("UPDATE attempts SET state='uncertain' WHERE job=? AND state='running'",(row['job'],))
                self.db.execute("UPDATE jobs SET state='needs_review' WHERE id=?",(row['job'],))
            self.db.execute("UPDATE jobs SET state='paused' WHERE state='running'")
        return len(rows)

    def run(self,job_id,adapter,*,accelerate=False,late_limit_s=30,stop=lambda:False):
        with self.owner():
            self.recover()
            row=self.db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            if not row:raise ValueError('Unknown job')
            if row['state']!='pending':raise ValueError('Job requires review or is already finished')
            if row['mode']!=adapter.mode:raise ValueError('Adapter mode does not match job')
            if accelerate and row['mode']!='simulation':raise ValueError('Accelerated hardware execution is forbidden')
            plan=json.loads(row['plan']);adapter.validate(plan)
            # Hardware commits must reach durable storage before each command.
            # Simulation has no external effects and may batch OS flushes.
            self.db.execute('PRAGMA synchronous='+('FULL' if row['mode']=='hardware' else 'NORMAL'))
            self.db.execute("UPDATE jobs SET state='running' WHERE id=?",(job_id,))
            for attempt in self.db.execute('SELECT * FROM attempts WHERE job=? ORDER BY intended,seq',(job_id,)).fetchall():
                if attempt['state']!='pending':continue
                due=attempt['intended'];event=plan['events'][attempt['seq']]
                lead=getattr(adapter,'lead_seconds',lambda e:0)(event)
                deadline=time.monotonic()+max(0,due-time.time()-lead)
                while not accelerate and time.monotonic()<deadline:
                    if stop():break
                    time.sleep(min(.1,max(0,deadline-time.monotonic())))
                if stop():
                    self.db.execute("UPDATE jobs SET state='paused' WHERE id=?",(job_id,));return 'paused'
                if not accelerate and time.time()-due>late_limit_s:
                    self.db.execute("UPDATE jobs SET state='needs_review' WHERE id=?",(job_id,));return 'needs_review'
                seq=attempt['seq']
                self.db.execute("UPDATE attempts SET state='running',started=? WHERE job=? AND seq=?",(time.time(),job_id,seq))
                try:
                    adapter.target_time=due;adapter.cancel=stop
                    result=adapter.execute(plan['events'][seq],job_id,seq)
                    encoded=json.dumps(result,allow_nan=False)
                except Exception as exc:
                    timing=getattr(adapter,'capture_timing',lambda:{})()
                    if isinstance(exc,(CaptureCancelled,CaptureSkipped)):
                        attempt_state='cancelled' if isinstance(exc,CaptureCancelled) else 'skipped'
                        self.db.execute("UPDATE attempts SET state=?,ended=?,result=? WHERE job=? AND seq=?",(attempt_state,time.time(),json.dumps({**timing,'error':str(exc),'trigger_sent':False,'retry':False}),job_id,seq))
                        if isinstance(exc,CaptureCancelled):
                            self.db.execute("UPDATE jobs SET state='paused' WHERE id=?",(job_id,));return 'paused'
                        if plan.get('execution',{}).get('capture_failure')=='continue':continue
                        self.db.execute("UPDATE jobs SET state='needs_review' WHERE id=?",(job_id,));return 'needs_review'
                    if event['kind']=='capture' and plan.get('execution',{}).get('capture_failure')=='continue' and getattr(adapter,'recoverable_capture_error',lambda e:False)(exc):
                        self.db.execute("UPDATE attempts SET state='failed',ended=?,result=? WHERE job=? AND seq=?",(time.time(),json.dumps({**timing,'error':str(exc),'retry':False}),job_id,seq))
                        continue
                    with self.transaction():
                        self.db.execute("UPDATE attempts SET state='uncertain',ended=?,result=? WHERE job=? AND seq=?",(time.time(),json.dumps({**timing,'error':str(exc),'physical_state':'unknown'}),job_id,seq))
                        self.db.execute("UPDATE jobs SET state='needs_review' WHERE id=?",(job_id,))
                    raise
                with self.transaction():
                    self.db.execute("UPDATE attempts SET state='completed',ended=?,result=? WHERE job=? AND seq=?",(time.time(),encoded,job_id,seq))
            failed=self.db.execute("SELECT count(*) FROM attempts WHERE job=? AND state IN ('failed','skipped')",(job_id,)).fetchone()[0]
            outcome='completed_with_errors' if failed else 'completed'
            self.db.execute("UPDATE jobs SET state=? WHERE id=?",(outcome,job_id));return outcome

    def status(self,job_id):
        row=self.db.execute('SELECT id,mode,state,created FROM jobs WHERE id=?',(job_id,)).fetchone()
        if not row:raise ValueError('Unknown job')
        result=dict(row);result['attempts']=[dict(r) for r in self.db.execute('SELECT seq,state,intended,started,ended,result FROM attempts WHERE job=? ORDER BY seq',(job_id,))]
        return result

    def close(self):self.db.close()

class Simulator:
    mode='simulation'
    def validate(self,plan):
        names={p['id'] for p in plan.get('protocols',[])}
        for e in plan['events']:
            if e['kind']=='capture' and e['protocol'] not in names:raise ValueError('Missing camera protocol')
    def execute(self,event,job_id,sequence):
        return {'simulated':True,'physical_output_verified':False,'event':event}
