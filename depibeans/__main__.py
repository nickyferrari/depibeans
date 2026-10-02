import argparse
import json
import tempfile
from pathlib import Path
from .core import Engine
from .native import library_version


def main():
    parser=argparse.ArgumentParser(description='DepiBeans development tools; no live hardware controls are enabled.')
    sub=parser.add_subparsers(dest='action',required=True)
    demo=sub.add_parser('demo',help='Run a temporary simulator and print its status')
    demo.add_argument('--chambers',type=int,default=1)
    probe=sub.add_parser('driver-version',help='Read DLL version without opening hardware')
    probe.add_argument('dll')
    args=parser.parse_args()
    if args.action=='driver-version':
        print(json.dumps(library_version(args.dll),indent=2));return
    if not 1<=args.chambers<=24:
        parser.error('Choose between 1 and 24 simulated chambers')
    with tempfile.TemporaryDirectory(prefix='depibeans-demo-') as folder:
        engine=Engine(str(Path(folder)/'simulation.sqlite'))
        for i in range(1,args.chambers+1):
            chamber=f'sim-{i:02}'
            engine.add_simulator(chamber,f'Simulated DEPI {i:02}',{'light_intensity':[0,1000]})
            engine.grant('local-demo',chamber,'operator',granted_by='local-bootstrap')
        print(json.dumps(engine.status('local-demo'),indent=2))
        engine.close()

if __name__=='__main__':main()
