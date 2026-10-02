"""Reconnectable outbound portal transport. Never sends hardware commands."""
import json
import os
from pathlib import Path
import re
import signal
import socket
import ipaddress
import subprocess
import threading
import time
import urllib.request
import urllib.parse

ROOT=Path.home()/'DepiBeans'
ORIGIN=(ROOT/'data/portal/origin.txt').read_text().strip()
stop=threading.Event()
def tunnel_ipv4(origin):
    host=urllib.parse.urlsplit(origin).hostname
    try:return socket.gethostbyname(host)
    except OSError:pass
    # Newly created quick-tunnel names can hit a cached NXDOMAIN. Ask the
    # provider's current authoritative nameservers instead of that cache.
    try:
        ns=subprocess.run(['/usr/bin/dig','+short','+time=2','+tries=1','trycloudflare.com','NS'],capture_output=True,text=True,timeout=4,check=True)
        for server in ns.stdout.splitlines()[:2]:
            if not re.fullmatch(r'[a-z0-9.-]+\.ns\.cloudflare\.com\.?',server):continue
            result=subprocess.run(['/usr/bin/dig','+short','+time=2','+tries=1','@'+server,host,'A'],capture_output=True,text=True,timeout=4,check=True)
            for line in result.stdout.splitlines():
                try:address=ipaddress.IPv4Address(line.strip())
                except ValueError:continue
                if address.is_global:return str(address)
    except (OSError,subprocess.SubprocessError):pass
    return ''
def main():
    signal.signal(signal.SIGTERM,lambda *_:stop.set())
    signal.signal(signal.SIGINT,lambda *_:stop.set())
    key=(ROOT/'data/portal/bridge.key').read_text().strip()
    while not stop.is_set():
        proc=subprocess.Popen([str(ROOT/'vendor/cloudflared'),'tunnel','--url','http://127.0.0.1:8766',
            '--protocol','http2','--http-host-header',urllib.parse.urlsplit(ORIGIN).netloc,'--no-autoupdate'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        state={'origin':None}
        def read_log():
            for line in proc.stdout:
                match=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',line)
                if match:
                    state['origin']=match.group()
                    (ROOT/'data/portal/connection-candidate.json').write_text(json.dumps({'origin':state['origin']}))
        reader=threading.Thread(target=read_log,daemon=True);reader.start()
        try:
            while proc.poll() is None and not stop.is_set():
                if state['origin']:
                    node=os.environ.get('DEPI_NODE_ID','')
                    req=urllib.request.Request(ORIGIN+('/_nodes/register' if node else '/_connection/register'),
                        data=json.dumps({'origin':state['origin'], 'ipv4':tunnel_ipv4(state['origin']), 'id':node}).encode(),
                        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json',
                                 'User-Agent':'DepiBeans/0.3 (Linux portal connector)'})
                    try:
                        with urllib.request.urlopen(req,timeout=20) as response:
                            result=json.load(response)
                            if result.get('registered') is not True:raise RuntimeError('Connection not registered')
                        receipt={'origin':state['origin'],'public_origin':ORIGIN,'heartbeat':time.time()}
                        tmp=ROOT/'data/portal/connection.tmp';tmp.write_text(json.dumps(receipt));tmp.replace(ROOT/'data/portal/connection.json')
                        print('Portal connection registered.',flush=True)
                    except Exception as exc:
                        # Never include request headers, secrets, cookies, or invitation links.
                        status=getattr(exc,'code',None)
                        print('Portal registration pending: '+type(exc).__name__+(f' HTTP {status}' if status else ''),flush=True)
                    stop.wait(20)
                else:stop.wait(1)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
            reader.join(timeout=2)
        stop.wait(5)
if __name__=='__main__':main()
