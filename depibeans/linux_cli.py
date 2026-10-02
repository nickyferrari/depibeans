"""Linux commissioning tools. Hardware execution requires an explicitly commissioned profile."""
import argparse
import importlib.util
import json
from pathlib import Path
import platform
import sys
from .legacy_timeline import load_timeline, summary
from .camera_protocol import compile_camera


def doctor():
    result={'python':platform.python_version(),'platform':platform.platform(),'mode':'commissioning',
            'physical_control_enabled':False,'camera_sdk_python_available':importlib.util.find_spec('vmbpy') is not None,
            'migration_complete':False,'blockers':[]}
    try:
        from .linux_adept import LinuxNative
        native=LinuxNative();result['adept_version']=native.version() or None;result['fpga_devices']=native.devices()
        if not result['fpga_devices']:result['blockers'].append('No Adept FPGA enumerated')
    except Exception as exc:
        result['adept_error']=str(exc);result['blockers'].append('Adept is unavailable')
    if not result['camera_sdk_python_available']:result['blockers'].append('Vimba Python SDK is not installed')
    result['blockers']+=['Camera/FPGA physical parity not commissioned','Complete experiment and recovery acceptance pending']
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor')
    camera=sub.add_parser('camera-status');camera.add_argument('--transport',required=True)
    run=sub.add_parser('run-plan');run.add_argument('plan');run.add_argument('--profile',required=True);run.add_argument('--database',required=True);run.add_argument('--data',required=True);run.add_argument('--request-id',required=True)
    imp=sub.add_parser('inspect-timeline');imp.add_argument('path');imp.add_argument('--output')
    audit=sub.add_parser('audit-references');audit.add_argument('directory');audit.add_argument('--output')
    sim=sub.add_parser('simulate');sim.add_argument('plan');sim.add_argument('--database',required=True);sim.add_argument('--request-id',required=True)
    args=p.parse_args()
    if args.command=='doctor':result=doctor()
    elif args.command=='camera-status':
        from .avt_camera import discover
        result=discover(args.transport)
    elif args.command=='run-plan':
        from .execution import Journal
        from .chamber_adapter import ChamberAdapter
        import signal
        stopped=[False]
        signal.signal(signal.SIGINT,lambda *unused:stopped.__setitem__(0,True))
        signal.signal(signal.SIGTERM,lambda *unused:stopped.__setitem__(0,True))
        plan=json.loads(Path(args.plan).read_text())
        if plan.get('schema')!='depibeans.experiment-plan/1':raise ValueError('Only a newly compiled Python plan can run; historical timelines are read-only')
        adapter=ChamberAdapter(json.loads(Path(args.profile).read_text()),args.data)
        adapter.validate(plan)
        journal=Journal(args.database)
        try:
            if journal.enqueue(args.request_id,plan,mode='hardware'):journal.run(args.request_id,adapter,stop=lambda:stopped[0])
            result=journal.status(args.request_id)
        finally:
            adapter.close();journal.close()
    elif args.command=='simulate':
        from .execution import Journal, Simulator
        plan=json.loads(Path(args.plan).read_text());journal=Journal(args.database)
        try:
            if journal.enqueue(args.request_id,plan):journal.run(args.request_id,Simulator(),accelerate=True)
            result=journal.status(args.request_id)
        finally:journal.close()
    elif args.command=='inspect-timeline':
        plan=load_timeline(args.path);result=summary(plan)
        if args.output:Path(args.output).write_text(json.dumps(plan,indent=2)+'\n')
    else:
        reports=[];failures=[];waveforms=0
        for f in sorted(Path(args.directory).rglob('Timeline.xml')):
            try:
                plan=load_timeline(f);r=summary(plan);r['protocol_compile_errors']=[]
                for proto in plan['protocols']:
                    try:compile_camera(proto['fields'],terminal_mask=0x20);waveforms+=1
                    except Exception as exc:r['protocol_compile_errors'].append({'protocol':proto['id'],'error':str(exc)})
                reports.append(r)
            except Exception as exc:failures.append({'path':str(f),'error':str(exc)})
        result={'timelines':len(reports),'events':sum(r['events'] for r in reports),'camera_protocols_compiled':waveforms,
                'parse_failures':failures,'reports':reports,'physical_execution':False}
        if args.output:Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
        else:pass
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
