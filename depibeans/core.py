"""Simulator-only engine. No native device adapter or public auth endpoint.

Physical execution requires a separate durable attempt/outbox implementation.
Every database must live on local disk, never a network share.
"""
import json
import sqlite3
import threading
import time
import uuid
from .lighting import finite


class Rejected(ValueError):
    """A client request did not satisfy the engine contract."""


def number(value):
    try:
        return finite(value)
    except (ValueError, TypeError) as exc:
        raise Rejected('Expected a finite numeric value') from exc


def identifier(value):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value.lower():
            raise ValueError()
        return value.lower()
    except (ValueError, AttributeError) as exc:
        raise Rejected('A canonical UUID is required') from exc


def values(settings):
    if not isinstance(settings, dict) or not settings or any(not isinstance(k,str) for k in settings):
        raise Rejected('At least one named setting is required')
    return {key:number(value) for key,value in settings.items()}


class Engine:
    def __init__(self, path, clock=time.time):
        self.clock=clock
        self.lock=threading.RLock()
        self.db=sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        old=self.db.execute('PRAGMA table_info(commands)').fetchall()
        if old and 'source' not in {r['name'] for r in old}:
            self.db.close()
            raise RuntimeError('Prototype v1 database: retain it for history and use a new simulator database for v2')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS chambers(
            id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 0, settings TEXT NOT NULL DEFAULT '{}',
            capabilities TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS grants(actor TEXT, chamber TEXT REFERENCES chambers(id),
            role TEXT CHECK(role IN ('viewer','operator','administrator')) NOT NULL,
            PRIMARY KEY(actor,chamber));
        CREATE TABLE IF NOT EXISTS commands(chamber TEXT NOT NULL REFERENCES chambers(id),
            source TEXT NOT NULL, id TEXT NOT NULL, actor TEXT NOT NULL,
            request TEXT NOT NULL, result TEXT NOT NULL, created REAL NOT NULL,
            expires REAL NOT NULL, PRIMARY KEY(chamber,source,id));
        CREATE TABLE IF NOT EXISTS schedules(chamber TEXT NOT NULL REFERENCES chambers(id),
            id TEXT NOT NULL, actor TEXT NOT NULL, due REAL NOT NULL,
            expires REAL NOT NULL, settings TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('active','paused','deleted','completed','missed','failed')),
            PRIMARY KEY(chamber,id));
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, actor TEXT NOT NULL,
            chamber TEXT NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL, at REAL NOT NULL);
        PRAGMA user_version=2;
        ''')

    def close(self):
        self.db.close()

    def _audit(self, actor, chamber, event, detail, now=None):
        self.db.execute('INSERT INTO audit(actor,chamber,event,detail,at) VALUES(?,?,?,?,?)',
                        (actor,chamber,event,json.dumps(detail,allow_nan=False),self.clock() if now is None else now))

    def _transaction(self, action):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                value=action()
                self.db.execute('COMMIT')
                return value
            except BaseException:
                self.db.execute('ROLLBACK')
                raise

    def add_simulator(self, chamber, name, limits):
        """Trusted local setup only; these are not commissioned physical limits."""
        if not isinstance(limits,dict) or not limits:
            raise Rejected('Simulator limits are required')
        for key,bounds in limits.items():
            if not isinstance(key,str) or not isinstance(bounds,(list,tuple)) or len(bounds)!=2 or number(bounds[0])>number(bounds[1]):
                raise Rejected('Invalid simulator limits')
        with self.lock:
            try:
                self.db.execute('INSERT INTO chambers(id,name,mode,capabilities) VALUES(?,?,?,?)',
                                (chamber,name,'simulation',json.dumps(limits,allow_nan=False)))
            except sqlite3.IntegrityError as exc:
                raise Rejected('Chamber already exists or configuration is invalid') from exc

    def grant(self, actor, chamber, role, *, granted_by):
        """Trusted local provisioning, not a public endpoint. None revokes access.

        granted_by must come from an authenticated provisioning context, never
        browser JSON. Bootstrapping is the caller's explicit local operation.
        """
        if role not in {None,'viewer','operator','administrator'} or not isinstance(granted_by,str) or not granted_by.strip():
            raise Rejected('Valid role and provisioning actor are required')
        def action():
            self._chamber(chamber)
            before=self.db.execute('SELECT role FROM grants WHERE actor=? AND chamber=?',(actor,chamber)).fetchone()
            if role is None:
                self.db.execute('DELETE FROM grants WHERE actor=? AND chamber=?',(actor,chamber))
            else:
                self.db.execute('INSERT OR REPLACE INTO grants VALUES(?,?,?)',(actor,chamber,role))
            self._audit(granted_by,chamber,'membership-changed',{'subject':actor,'previous':before['role'] if before else None,'role':role})
            if role in {None,'viewer'}:
                rows=self.db.execute("SELECT id FROM schedules WHERE chamber=? AND actor=? AND state='active'",(chamber,actor)).fetchall()
                for row in rows:
                    self.db.execute("UPDATE schedules SET state='paused' WHERE chamber=? AND id=?",(chamber,row['id']))
                    self._audit(granted_by,chamber,'schedule-paused',{'id':row['id'],'reason':'permission-change','subject':actor})
        return self._transaction(action)

    def _allow(self, actor, chamber, write=False):
        row=self.db.execute('SELECT role FROM grants WHERE actor=? AND chamber=?',(actor,chamber)).fetchone()
        if not row or (write and row['role']=='viewer'):
            raise Rejected('No permission for this chamber')

    def _chamber(self, chamber):
        row=self.db.execute('SELECT * FROM chambers WHERE id=?',(chamber,)).fetchone()
        if not row:
            raise Rejected('Unknown chamber')
        return row

    def _settings(self, row, settings):
        settings=values(settings)
        limits=json.loads(row['capabilities'])
        for key,value in settings.items():
            if key not in limits:
                raise Rejected('Unsupported capability: '+key)
            if not limits[key][0]<=value<=limits[key][1]:
                raise Rejected('Outside configured limits: '+key)
        return settings

    def status(self, actor):
        with self.lock:
            rows=self.db.execute('SELECT c.* FROM chambers c JOIN grants g ON c.id=g.chamber WHERE g.actor=? ORDER BY c.id',(actor,)).fetchall()
            return [{**dict(r),'settings':json.loads(r['settings']),'capabilities':json.loads(r['capabilities']),
                     'physical_output_verified':False,'hardware_connected':False} for r in rows]

    def command(self, actor, command_id, chamber, revision, settings, ttl_s=60):
        command_id=identifier(command_id)
        ttl_s=number(ttl_s)
        if not 0<ttl_s<=120:
            raise Rejected('TTL must be greater than zero and at most 120 seconds')
        def action():
            now=self.clock()
            return self._command(actor,command_id,chamber,revision,settings,now+ttl_s,'manual',now)
        return self._transaction(action)

    def _command(self, actor, command_id, chamber, revision, settings, expires, source, now):
        # A revoked caller cannot retrieve cached commands through a write endpoint.
        self._allow(actor,chamber,True)
        if type(revision) is not int:
            raise Rejected('Revision must be an integer')
        settings=values(settings)
        request=json.dumps([actor,chamber,revision,settings,source],sort_keys=True,allow_nan=False)
        previous=self.db.execute('SELECT request,result FROM commands WHERE chamber=? AND source=? AND id=?',
                                 (chamber,source,command_id)).fetchone()
        if previous:
            if previous['request']!=request:
                raise Rejected('Command ID already used for another request')
            return json.loads(previous['result'])
        if not now<expires<=now+120:
            raise Rejected('Command expired or expiry exceeds two minutes')
        row=self._chamber(chamber)
        if row['mode']!='simulation':
            raise Rejected('Hardware adapter is not commissioned')
        if row['revision']!=revision:
            raise Rejected('Settings changed; refresh before applying')
        settings=self._settings(row,settings)
        merged={**json.loads(row['settings']),**settings}
        self.db.execute('UPDATE chambers SET settings=?,revision=revision+1 WHERE id=?',
                        (json.dumps(merged,allow_nan=False),chamber))
        paused=[]
        if source=='manual':
            paused=[r['id'] for r in self.db.execute("SELECT id FROM schedules WHERE chamber=? AND state='active'",(chamber,)).fetchall()]
            for schedule_id in paused:
                self.db.execute("UPDATE schedules SET state='paused' WHERE chamber=? AND id=?",(chamber,schedule_id))
                self._audit(actor,chamber,'schedule-paused',{'id':schedule_id,'reason':'manual-command','command_id':command_id},now)
        result={'id':command_id,'state':'simulated','revision':revision+1,'settings':merged,
                'physical_output_verified':False,'expires':expires,'paused_schedule_ids':paused}
        self.db.execute('INSERT INTO commands VALUES(?,?,?,?,?,?,?,?)',
                        (chamber,source,command_id,actor,request,json.dumps(result),now,expires))
        self._audit(actor,chamber,'command',{**result,'source':source},now)
        return result

    def schedule(self, actor, schedule_id, chamber, due, settings):
        schedule_id=identifier(schedule_id)
        due=number(due)
        def action():
            self._allow(actor,chamber,True)
            if due<=self.clock():
                raise Rejected('Choose a future time')
            if self.db.execute('SELECT 1 FROM schedules WHERE chamber=? AND id=?',(chamber,schedule_id)).fetchone():
                raise Rejected('Schedule ID already exists; use a new UUID')
            row=self._chamber(chamber)
            settings_copy=self._settings(row,settings)
            if row['mode']!='simulation':
                raise Rejected('Hardware adapter is not commissioned')
            overlap=self.db.execute("SELECT id FROM schedules WHERE chamber=? AND state='active' AND abs(due-?)<180",(chamber,due)).fetchone()
            if overlap:
                raise Rejected('Allow three minutes between this chamber’s events')
            try:
                self.db.execute('INSERT INTO schedules VALUES(?,?,?,?,?,?,?)',
                                (chamber,schedule_id,actor,due,due+120,json.dumps(settings_copy),'active'))
            except sqlite3.IntegrityError as exc:
                raise Rejected('Schedule already exists or is invalid') from exc
            self._audit(actor,chamber,'schedule-created',{'id':schedule_id,'due':due})
            return {'id':schedule_id,'state':'active'}
        return self._transaction(action)

    def schedules(self, actor):
        with self.lock:
            rows=self.db.execute("SELECT s.* FROM schedules s JOIN grants g ON g.chamber=s.chamber WHERE g.actor=? AND s.state!='deleted' ORDER BY s.due",(actor,)).fetchall()
            return [{**dict(r),'settings':json.loads(r['settings'])} for r in rows]

    def set_schedule_state(self, actor, chamber, schedule_id, state):
        schedule_id=identifier(schedule_id)
        if state not in {'active','paused','deleted'}:
            raise Rejected('Invalid schedule action')
        def action():
            self._allow(actor,chamber,True)
            row=self.db.execute('SELECT * FROM schedules WHERE chamber=? AND id=?',(chamber,schedule_id)).fetchone()
            if not row:
                raise Rejected('Unknown schedule')
            if row['state'] in {'deleted','completed','missed','failed'} and state!='deleted':
                raise Rejected('Create a new future event for a finished schedule')
            if state=='active':
                if row['due']<=self.clock():
                    raise Rejected('Choose a new future time')
                self._allow(row['actor'],chamber,True)
                overlap=self.db.execute("SELECT id FROM schedules WHERE chamber=? AND id!=? AND state='active' AND abs(due-?)<180",(chamber,schedule_id,row['due'])).fetchone()
                if overlap:
                    raise Rejected('This schedule conflicts with another active event')
            self.db.execute('UPDATE schedules SET state=? WHERE chamber=? AND id=?',(state,chamber,schedule_id))
            self._audit(actor,chamber,'schedule-'+state,{'id':schedule_id})
        return self._transaction(action)

    def tick(self):
        """Per-occurrence simulator transactions; never a physical I/O executor."""
        now=self.clock()
        with self.lock:
            keys=self.db.execute("SELECT chamber,id FROM schedules WHERE state='active' AND due<=? ORDER BY due,chamber,id",(now,)).fetchall()
        count=0
        for key in keys:
            def action():
                row=self.db.execute("SELECT * FROM schedules WHERE chamber=? AND id=? AND state='active' AND due<=?",(key['chamber'],key['id'],now)).fetchone()
                if not row:
                    return 0
                state='completed';error=None
                if row['expires']<=now:
                    state='missed'
                else:
                    self.db.execute('SAVEPOINT occurrence')
                    try:
                        current=self._chamber(row['chamber'])
                        self._command(row['actor'],row['id'],row['chamber'],current['revision'],
                                      json.loads(row['settings']),row['expires'],'schedule',now)
                    except sqlite3.Error:
                        raise  # A broken journal must not be treated as a successful receipt.
                    except Exception as exc:
                        self.db.execute('ROLLBACK TO occurrence')
                        state='failed';error=type(exc).__name__
                    finally:
                        self.db.execute('RELEASE occurrence')
                self.db.execute('UPDATE schedules SET state=? WHERE chamber=? AND id=?',(state,row['chamber'],row['id']))
                self._audit(row['actor'],row['chamber'],'schedule-'+state,{'id':row['id'],'error':error},now)
                return 1
            count+=self._transaction(action)
        return count
