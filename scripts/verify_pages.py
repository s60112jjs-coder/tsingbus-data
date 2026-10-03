"""Read-only verification of public Pages files; never connects to TDX."""
import json
import os
import time
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'docs/v1'
manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
names = ['manifest.json'] + [entry['path'] for entry in manifest['files'].values()]
for name in names:
    if Path(name).name != name:
        raise SystemExit('Rejected unsafe manifest path')
expected = {name: (root / name).read_bytes() for name in names}
base = os.environ['PAGES_URL'].rstrip('/') + '/v1/'
for attempt in range(10):
    try:
        for name, content in expected.items():
            request = urllib.request.Request(base + name, headers={'Cache-Control': 'no-cache'})
            with urllib.request.urlopen(request, timeout=20) as response:
                if response.read() != content:
                    raise ValueError('Published data is not current')
        print('Pages manifest and every registered data file match the publication.')
        break
    except Exception:
        if attempt == 9:
            raise SystemExit('Pages verification failed; inspect the deployment before retrying.')
        time.sleep(15)
