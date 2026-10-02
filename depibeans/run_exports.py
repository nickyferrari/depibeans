"""Bounded, on-demand exports of existing run records and original capture files."""
import csv,hashlib,io,json,threading,zipfile
from pathlib import Path

PART_BYTES=16*1024*1024
MAX_MANIFEST=4*1024*1024
class RunExports:
    def __init__(self,captures):
        self.root=Path(captures).resolve();self.lock=threading.Lock()
    def files(self,job):
        root=self.root/hashlib.sha256(job.encode()).hexdigest()
        result=[]
        for path in sorted([*root.glob('capture-*/*'),*root.glob('analysis/*.tif'),*root.glob('fluorescence.json')]):
            resolved=path.resolve()
            if not path.is_file() or path.suffix not in ('.tif','.json') or not resolved.is_relative_to(root) or not resolved.is_relative_to(self.root):continue
            result.append({'name':str(path.relative_to(root)),'bytes':path.stat().st_size,'path':path})
        return result
    def groups(self,job):
        groups=[[]];size=0
        for item in self.files(job):
            if item['bytes']>PART_BYTES:raise ValueError('An original file exceeds the bundle limit; use its individual download')
            if size+item['bytes']>PART_BYTES:groups.append([]);size=0
            groups[-1].append(item);size+=item['bytes']
        return groups
    def index(self,job):
        groups=self.groups(job)
        return {'parts':[{'part':i,'bytes':sum(f['bytes'] for f in group),'files':len(group)} for i,group in enumerate(groups)],'contains':'Original TIFFs, acquisition metadata, run report, event CSV and SHA-256 checksums','temporary_files_created':False}
    def archive(self,report,part):
        if not self.lock.acquire(blocking=False):raise ValueError('Another export is being prepared. Try again shortly.')
        try:
            groups=self.groups(report['id'])
            if not 0<=part<len(groups):raise ValueError('Unknown export part')
            manifest=json.dumps(report,indent=2,allow_nan=False).encode()
            if len(manifest)>MAX_MANIFEST:raise ValueError('Run report exceeds the bundle limit; download the report separately')
            buf=io.BytesIO();checksums={}
            with zipfile.ZipFile(buf,'w',compression=zipfile.ZIP_STORED) as archive:
                archive.writestr('run-report.json',manifest)
                csvfile=io.StringIO();writer=csv.writer(csvfile)
                writer.writerow(['step','action','setting','state','intended_unix','started_unix','ended_unix','error'])
                def cell(value):
                    value='' if value is None else str(value)
                    return "'"+value if value.startswith(('=','+','-','@','\t','\r')) else value
                for attempt in report['attempts']:
                    event=report['plan']['events'][attempt['seq']]
                    writer.writerow([attempt['seq']+1,cell(event.get('command',event.get('protocol'))),cell(event.get('value')),attempt['state'],attempt['intended'],attempt['started'],attempt['ended'],cell((attempt.get('result') or {}).get('error'))])
                archive.writestr('events.csv',csvfile.getvalue())
                for item in groups[part]:
                    path=item['path']
                    if path.stat().st_size!=item['bytes']:raise ValueError('Capture files changed while preparing the export')
                    payload=path.read_bytes()
                    if len(payload)!=item['bytes']:raise ValueError('Capture files changed while preparing the export')
                    archive.writestr(item['name'],payload);checksums[item['name']]=hashlib.sha256(payload).hexdigest()
                archive.writestr('bundle.json',json.dumps({'job':report['id'],'part':part+1,'total_parts':len(groups),'sha256':checksums,'originals_unchanged':True},indent=2))
            if buf.tell()>24*1024*1024:raise ValueError('Bundle exceeds the portal download limit')
            return buf.getvalue()
        finally:self.lock.release()
