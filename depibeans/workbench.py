"""Versioned experiment/protocol workspace. Never executes uploaded code."""
from contextlib import contextmanager
from pathlib import Path
import copy,hashlib,json,math,re,sqlite3,time,uuid
from .camera_protocol import compile_camera,ChamberPins
from .scripting import Experiment

class Workbench:
    def __init__(self,path):
        self.path=Path(path)
        with self.db() as db:db.executescript('''
        CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,kind TEXT,name TEXT,body TEXT,version INTEGER,updated REAL,actor TEXT,archived INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS versions(id TEXT,version INTEGER,body TEXT,created REAL,actor TEXT,PRIMARY KEY(id,version));
        CREATE TABLE IF NOT EXISTS settings(name TEXT PRIMARY KEY,body TEXT);
        CREATE TABLE IF NOT EXISTS uploads(id TEXT,seq INTEGER,body TEXT,created REAL,actor TEXT,PRIMARY KEY(id,seq,actor));
        CREATE TABLE IF NOT EXISTS schedules(id TEXT PRIMARY KEY,plan TEXT,mode TEXT,due REAL,state TEXT,actor TEXT,error TEXT);
        ''')
        with self.db() as db:db.execute("UPDATE schedules SET state='missed',error='Controller restarted after the scheduled start. Review and schedule again.' WHERE state IN ('dispatching','queued') AND due<?",(time.time(),))
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    def setting(self,name,default):
        with self.db() as db:row=db.execute('SELECT body FROM settings WHERE name=?',(name,)).fetchone()
        return json.loads(row['body']) if row else copy.deepcopy(default)
    def set_setting(self,name,body):
        with self.db() as db:db.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(name) DO UPDATE SET body=excluded.body',(name,json.dumps(body,allow_nan=False)))
    def list(self,kind):
        with self.db() as db:rows=db.execute('SELECT id,name,version,updated,actor FROM documents WHERE kind=? AND archived=0 ORDER BY updated DESC',(kind,)).fetchall()
        return [dict(r) for r in rows]
    def get(self,key):
        with self.db() as db:row=db.execute('SELECT * FROM documents WHERE id=? AND archived=0',(key,)).fetchone()
        if not row:raise ValueError('Saved item not found')
        return {**dict(row),'body':json.loads(row['body'])}
    def revisions(self,key):
        self.get(key)
        with self.db() as db:rows=db.execute('SELECT version,created,actor FROM versions WHERE id=? ORDER BY version DESC',(key,)).fetchall()
        return [dict(r) for r in rows]
    def revision(self,key,version):
        head=self.get(key)
        with self.db() as db:row=db.execute('SELECT body,version,created,actor FROM versions WHERE id=? AND version=?',(key,version)).fetchone()
        if not row:raise ValueError('Version not found')
        return {**head,'head_version':head['version'],'version':row['version'],'body':json.loads(row['body']),'actor':row['actor'],'updated':row['created']}

    def save(self,kind,body,actor,key=None,version=None):
        name=body.get('name')
        if not isinstance(name,str) or not 1<=len(name.strip())<=180:raise ValueError('Use a name of 1–180 characters')
        encoded=json.dumps(body,allow_nan=False)
        if len(encoded.encode())>2_000_000:raise ValueError('Plan is too large')
        key=key or 'user-'+uuid.uuid4().hex
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT version,kind FROM documents WHERE id=?',(key,)).fetchone()
            if old and (version!=old['version'] or old['kind']!=kind):raise ValueError('This item changed in another window. Reload before saving.')
            v=(old['version']+1) if old else 1
            db.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?,0) ON CONFLICT(id) DO UPDATE SET name=excluded.name,body=excluded.body,version=excluded.version,updated=excluded.updated,actor=excluded.actor,archived=0',(key,kind,name,encoded,v,time.time(),actor))
            db.execute('INSERT INTO versions VALUES(?,?,?,?,?)',(key,v,encoded,time.time(),actor))
        return {'id':key,'version':v,'name':name}
    def archive(self,key,version):
        with self.db() as db:
            if not db.execute('UPDATE documents SET archived=1 WHERE id=? AND version=?',(key,version)).rowcount:raise ValueError('Item changed; reload before archiving')
        return {'archived':True}
    def chunk(self,data,actor):
        key=data.get('upload');seq=data.get('sequence');body=data.get('chunk')
        if not isinstance(key,str) or not re.fullmatch('[a-zA-Z0-9-]{1,80}',key) or type(seq) is not int or not 0<=seq<1000 or not isinstance(body,str) or len(body.encode())>12000:raise ValueError('Invalid upload chunk')
        with self.db() as db:
            db.execute('DELETE FROM uploads WHERE created<?',(time.time()-3600,))
            db.execute('INSERT INTO uploads VALUES(?,?,?,?,?) ON CONFLICT(id,seq,actor) DO UPDATE SET body=excluded.body,created=excluded.created',(key,seq,body,time.time(),actor))
        return {'received':seq}
    def assembled(self,key,actor):
        with self.db() as db:rows=db.execute('SELECT seq,body FROM uploads WHERE id=? AND actor=? ORDER BY seq',(key,actor)).fetchall()
        if not rows or [r['seq'] for r in rows]!=list(range(len(rows))):raise ValueError('Upload is incomplete')
        text=''.join(r['body'] for r in rows)
        if len(text.encode())>2_000_000:raise ValueError('Plan is too large')
        return json.loads(text)

def validate_plan(plan,profile):
    if not isinstance(plan,dict):raise ValueError('Expected an experiment plan')
    if not isinstance(plan.get('name'),str) or not 1<=len(plan['name'].strip())<=180:raise ValueError('Experiment name is required')
    events=plan.get('events');protocols=plan.get('protocols',[])
    if not isinstance(events,list) or not 1<=len(events)<=10000:raise ValueError('Use 1–10,000 events')
    if not isinstance(protocols,list) or len(protocols)>256:raise ValueError('Too many camera protocols')
    names=set();waveforms={};pins=ChamberPins(**{k:tuple(v) if isinstance(v,list) else v for k,v in profile['pins'].items()})
    for proto in protocols:
        if not isinstance(proto,dict) or not isinstance(proto.get('fields'),dict):raise ValueError('Each camera protocol needs fields')
        name=proto.get('id')
        if not isinstance(name,str) or not name or name in names:raise ValueError('Camera protocol names must be unique')
        names.add(name);waveforms[name]=compile_camera(proto['fields'],pins=pins,clock_hz=profile['expected_clock_hz'])
        if waveforms[name]['frame_count']>10000 or waveforms[name]['duration_s']>3600:raise ValueError('Capture exceeds supported frame count or one-hour acquisition limit')
    for event in events:
        if not isinstance(event,dict):raise ValueError('Each event must be an object')
        if type(event.get('delay_ms')) is not int or not 0<=event['delay_ms']<=366*86400000 or type(event.get('relative')) is not bool:raise ValueError('Each event needs valid timing and a relative/absolute flag')
        if event.get('kind')=='set':
            if event.get('command') not in ('intensity','FR','UVA','UVB'):raise ValueError('Unknown lighting channel')
            value=float(event.get('value'))
            if isinstance(event.get('value'),bool) or not math.isfinite(value) or not 0<=value<=65535:raise ValueError('Invalid light setting')
        elif event.get('kind')=='capture':
            if event.get('protocol') not in names:raise ValueError('Capture references an unknown protocol')
        else:raise ValueError('Unknown event type')
    p=copy.deepcopy(plan);p['schema']='depibeans.experiment-plan/1';p['hardware_execution_authorized']=False
    from .chamber_adapter import ChamberAdapter
    reasons=[]
    try:
        ChamberAdapter(profile,Path('/unused')).validate(p)
    except (ValueError,KeyError,TypeError) as exc:reasons.append(str(exc))
    if p.get('recovery',{}).get('initial_state_review_required'):reasons.append('Review and specify the initial light/camera state before running this recovery plan')
    return {'plan':p,'valid':True,'events':len(events),'frames':sum(waveforms[e['protocol']]['frame_count'] for e in events if e['kind']=='capture'),'hardware_ready':not reasons,'hardware_reasons':reasons,'waveforms':waveforms}

def recipe_plan(data):
    e=Experiment(data['name'])
    for proto in data.get('protocols',[]):e.protocol(proto['id'],proto['fields'],analysis=proto.get('analysis'),group=proto.get('group','*'),sensors=proto.get('sensors',['*']))
    repeats=data.get('repeat',1)
    if type(repeats) is not int or not 1<=repeats<=1000:raise ValueError('Repeat count must be 1–1000')
    steps=data.get('steps',[])
    if not isinstance(steps,list) or not steps or len(steps)*repeats>10000:raise ValueError('Use 1–10,000 total steps')
    for _ in range(repeats):
        for step in steps:
            kind=step.get('kind')
            if kind=='wait':e.wait(step['duration'])
            elif kind=='at':e.wait_until(step['time'])
            elif kind=='set':e.set(step['command'],float(step['value']))
            elif kind=='capture':e.capture(step['protocol'])
            else:raise ValueError('Unknown recipe step')
    return e.compile()
