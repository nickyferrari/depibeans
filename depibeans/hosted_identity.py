"""Verify short-lived hosting assertions bound to one HTTP request and chamber.
The bridge key is never sent to the browser. Existing controller checks still apply.
"""
from contextlib import closing
import base64,hashlib,hmac,json,re,sqlite3,time
from pathlib import Path

def verify_assertion(root,key,header,signature,method,target,body,chamber):
    if not isinstance(header,str) or len(header)>2048:raise ValueError('Invalid assertion')
    material='\n'.join(('depi-hosted-v1',method,target,hashlib.sha256(body).hexdigest(),header)).encode()
    expected=hmac.new(key.encode(),material,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature,expected):raise ValueError('Invalid signature')
    try:claim=json.loads(base64.b64decode(header,validate=True))
    except Exception:raise ValueError('Invalid assertion')
    now=int(time.time())
    if type(claim.get('time')) is not int or abs(now-claim['time'])>30:raise ValueError('Expired assertion')
    if claim.get('chamber')!=chamber:raise ValueError('Wrong chamber')
    if claim.get('role') not in ('viewer','operator','admin'):raise ValueError('Invalid role')
    if not isinstance(claim.get('user'),str) or not re.fullmatch(r'[a-zA-Z0-9_.@+\-]{1,128}',claim['user']):raise ValueError('Invalid user')
    if not isinstance(claim.get('nonce'),str) or not re.fullmatch(r'[a-f0-9]{32}',claim['nonce']):raise ValueError('Invalid nonce')
    if method=='POST' and claim['role']=='viewer':raise ValueError('Read-only user')
    with closing(sqlite3.connect(Path(root)/'hosted-nonces.sqlite3',timeout=3)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS nonces(id TEXT PRIMARY KEY,created INTEGER NOT NULL)')
        db.execute('DELETE FROM nonces WHERE created<?',(now-90,))
        try:db.execute('INSERT INTO nonces VALUES(?,?)',(claim['nonce'],now))
        except sqlite3.IntegrityError:raise ValueError('Repeated assertion')
    return claim['user'],claim['role']
