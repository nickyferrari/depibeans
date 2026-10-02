"""Report staging computer availability; never sends chamber commands."""
import json
from pathlib import Path
import time
import urllib.request


def main():
    root = Path.home() / 'DepiBeans/data/node'
    key = (root / 'heartbeat.key').read_text().strip()
    while True:
        healthy = False
        state = {}
        try:
            with urllib.request.urlopen('http://127.0.0.1:8765/api/status', timeout=5) as response:
                state = json.load(response)
            healthy = state.get('chamber_id') == 'depi-five'
        except Exception:
            pass
        request = urllib.request.Request(
            'https://portal.example.org/_nodes/heartbeat',
            data=json.dumps({'id': 'depi-five', 'controller_online': healthy,
                             'manual_light_ready': healthy and state.get('manual_light_ready') is True,
                             'experiment_ready': healthy and state.get('experiment_ready') is True,
                             'has_fault': healthy and bool(state.get('last_error')),
                             'running': healthy and bool(state.get('active'))}).encode(),
            headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if json.load(response).get('registered') is not True:
                    raise ValueError('Registration not acknowledged')
            print('DEPI 5 heartbeat acknowledged', flush=True)
        except Exception as exc:
            print('Heartbeat pending: ' + type(exc).__name__, flush=True)
        time.sleep(15)


if __name__ == '__main__':
    main()
