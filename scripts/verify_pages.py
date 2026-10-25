"""Read-only verification of public Pages files; never connects to TDX.

Run right after a deploy (default) or with --initial-delay 300 as the delayed
re-check: every manifest-registered file must match the git copy byte for byte.
"""
import argparse
import json
import os
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'docs/v1'
DEFAULT_URL = 'https://s60112jjs-coder.github.io/tsingbus-data'


def expected_files(root):
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    names = ['manifest.json'] + [entry['path'] for entry in manifest['files'].values()]
    for name in names:
        if Path(name).name != name:
            raise SystemExit('Rejected unsafe manifest path')
    return {name: (root / name).read_bytes() for name in names}


def fetch_public(url):
    # Cache-busting query: the Pages CDN may otherwise serve the previous object for minutes.
    request = urllib.request.Request(url + '?verify=' + str(int(time.time())), headers={'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def verify(base, expected, fetch=fetch_public, sleep=time.sleep, attempts=10, interval=15):
    """Return None when everything matches, else the last mismatch description."""
    problem = None
    for attempt in range(attempts):
        problem = None
        for name, content in expected.items():
            try:
                if fetch(base + name) != content:
                    problem = f'{name} is not current'
                    break
            except Exception as error:
                problem = f'{name} unreadable ({type(error).__name__})'
                break
        if problem is None:
            return None
        if attempt < attempts - 1:
            sleep(interval)
    return problem


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--initial-delay', type=int, default=0, help='Seconds to wait before the first check')
    parser.add_argument('--attempts', type=int, default=10)
    args = parser.parse_args()
    if args.initial_delay:
        time.sleep(args.initial_delay)
    base = os.environ.get('PAGES_URL', DEFAULT_URL).rstrip('/') + '/v1/'
    problem = verify(base, expected_files(ROOT), attempts=args.attempts)
    if problem:
        raise SystemExit(f'Pages verification failed: {problem}; inspect the deployment before retrying.')
    print('Pages manifest and every registered data file match the publication.')


if __name__ == '__main__':
    main()
