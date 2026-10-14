"""Download starter Piper voices for AcePressure.

Fetches 4 ONNX voices (Hindi male/female + English male/female) and their JSON
metadata into data/piper-voices/. Idempotent — skips voices already present.

The voices live under the public rhasspy/piper-voices repository on HuggingFace;
no login required, direct HTTPS GET.

Rerun this script any time to refresh or add new voices. Edit VOICES below to
add any voice from https://huggingface.co/rhasspy/piper-voices/tree/main .
"""
from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOICES_DIR = ROOT / 'data' / 'piper-voices'


# (local_name, remote_folder_relative_to_rhasspy/piper-voices/main/)
VOICES = [
    ('hi_IN-pratham-medium',    'hi/hi_IN/pratham/medium/'),
    ('hi_IN-priyamvada-medium', 'hi/hi_IN/priyamvada/medium/'),
    ('en_US-amy-medium',        'en/en_US/amy/medium/'),
    ('en_US-ryan-medium',       'en/en_US/ryan/medium/'),
]

BASE = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/'


def download(url: str, dest: Path):
    """Streaming download with a basic progress print."""
    req = urllib.request.Request(url, headers={'User-Agent': 'AcePressure-Piper-Downloader/1.0'})
    with urllib.request.urlopen(req, timeout=120) as r:
        total = int(r.headers.get('Content-Length', 0))
        chunk = 65536
        done = 0
        tmp = dest.with_suffix(dest.suffix + '.part')
        with open(tmp, 'wb') as f:
            while True:
                buf = r.read(chunk)
                if not buf:
                    break
                f.write(buf)
                done += len(buf)
                if total:
                    pct = (done * 100) // total
                    sys.stdout.write(f'\r      {pct:>3}% ({done >> 20} MB / {total >> 20} MB)')
                    sys.stdout.flush()
        tmp.replace(dest)
    sys.stdout.write('\n')


def main():
    global VOICES_DIR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data',
                        help='Active data folder; use data-demo for demo testing.')
    args = parser.parse_args()
    VOICES_DIR = args.data_dir.resolve() / 'piper-voices'
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    print(f'Downloading Piper voices into {VOICES_DIR}')
    errors = 0
    for name, remote in VOICES:
        onnx_dest = VOICES_DIR / f'{name}.onnx'
        json_dest = VOICES_DIR / f'{name}.onnx.json'
        if onnx_dest.exists() and json_dest.exists():
            print(f'  ✓ {name} already present')
            continue
        print(f'  → {name}')
        try:
            if not onnx_dest.exists():
                download(f'{BASE}{remote}{name}.onnx', onnx_dest)
            if not json_dest.exists():
                download(f'{BASE}{remote}{name}.onnx.json', json_dest)
            print(f'  ✓ {name}')
        except (urllib.error.URLError, OSError) as e:
            print(f'  ✗ {name}: {e}')
            errors += 1
            onnx_dest.unlink(missing_ok=True)
            json_dest.unlink(missing_ok=True)
    print()
    if errors:
        print(f'Finished with {errors} error(s). Re-run this script to retry.')
        sys.exit(1)
    print('All voices downloaded.')  # Install_Piper.bat says next how to use them: main voice or backup (1.6.5)


if __name__ == '__main__':
    main()
