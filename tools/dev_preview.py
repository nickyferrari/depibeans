"""Run the real web workspace on loopback with physical execution disabled."""
import argparse
import json
from pathlib import Path
import sys
import threading
import time
from http.server import ThreadingHTTPServer

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from depibeans.control_app import ControlDesk, Handler


class DevelopmentDesk(ControlDesk):
    def refresh(self):
        self.devices = {'fpga_devices': [], 'cameras': [], 'checked_at': time.time(),
                        'errors': ['Local development: hardware disabled']}
        return self.status()

    def start(self, plan, mode, request_id):
        if mode != 'simulation':
            raise ValueError('Local development only supports simulation')
        return super().start(plan, mode, request_id)

    def profile(self):
        profile = super().profile()
        profile['commissioned'] = False
        profile['verified_controls'] = {}
        return profile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    root = SOURCE / '.development'
    root.mkdir(exist_ok=True)
    profile = json.loads((SOURCE / 'profiles/enterprise-linux.uncommissioned.json').read_text())
    profile.update(commissioned=False, verified_controls={})
    path = root / 'development-profile.json'
    path.write_text(json.dumps(profile, indent=2))
    desk = DevelopmentDesk(root, path)
    desk.refresh()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.desk = desk
    threading.Thread(target=desk.scheduler_loop, daemon=True).start()
    print(f'Local development: http://127.0.0.1:{args.port}; hardware disabled', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
