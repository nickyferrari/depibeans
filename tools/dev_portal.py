"""Local TLS portal, isolated from production accounts and connection secrets."""
import argparse
import json
from pathlib import Path
import sys

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from depibeans.portal import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cert', type=Path, required=True)
    parser.add_argument('--key', type=Path, required=True)
    args = parser.parse_args()
    if not args.cert.is_file() or not args.key.is_file():
        parser.error('Supply a locally trusted TLS certificate and private key')
    root = SOURCE / '.development/portal'
    root.mkdir(parents=True, exist_ok=True)
    approved = root / 'approved-emails.json'
    if not approved.exists():
        approved.write_text(json.dumps(['user@example.edu']))
    (root / 'origin.txt').write_text('https://localhost:8766\n')
    app = create_app(root, 'https://localhost:8766')
    app.run(host='127.0.0.1', port=8766, debug=False,
            ssl_context=(str(args.cert), str(args.key)))


if __name__ == '__main__':
    main()
