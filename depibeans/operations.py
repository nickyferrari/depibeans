"""Operator reservation and bounded, durable command records for one chamber."""
from contextlib import contextmanager
import json
import sqlite3
import threading
import time

class Operations:
    def __init__(self, path):
        self.path=path;self.lock=threading.RLock()
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS commands(id INTEGER PRIMARY KEY, created REAL, actor TEXT, action TEXT, detail TEXT, request_id TEXT, outcome TEXT)')
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    def record(self,actor,action,detail,request_id,outcome):
        with self.connect() as db:
            cursor=db.execute('INSERT INTO commands(created,actor,action,detail,request_id,outcome) VALUES(?,?,?,?,?,?)',(time.time(),actor,action,json.dumps(detail),request_id,outcome))
            return cursor.lastrowid
    def finish(self,record,outcome):
        with self.connect() as db:db.execute('UPDATE commands SET outcome=? WHERE id=?',(outcome,record))
    def recent(self,limit=100,before=None):
        with self.connect() as db:
            rows=db.execute('SELECT * FROM commands WHERE id<? ORDER BY id DESC LIMIT ?', (before or 9223372036854775807,limit)).fetchall()
        return [{**dict(r),'detail':json.loads(r['detail'])} for r in rows]
    def last_light(self):
        with self.connect() as db:
            row=db.execute("SELECT created,actor,detail,request_id FROM commands WHERE action='/api/light' AND outcome='accepted' ORDER BY id DESC LIMIT 1").fetchone()
        return {**dict(row),'detail':json.loads(row['detail'])} if row else None
