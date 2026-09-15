#!/usr/bin/env python3
"""data/corpus → canonical data root/RAW. Preview by default; stop old runs first."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '02_BACKEND'))

def main(argv=None):
    from lawrag.pipeline.genos_raw_move import move
    from lawrag.pipeline.genos_stages import plain_path, offline_data_root
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', default=str(ROOT / 'data/corpus'))
    p.add_argument('--apply', action='store_true')
    args = p.parse_args(argv)
    os.umask(0o077)
    data = offline_data_root(ROOT)
    try:
        if args.apply:
            data.mkdir(parents=True, exist_ok=True)
            with plain_path(data / '.raw-migration.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = move(args.source, data, apply=True)
        else:
            result = move(args.source, data)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print('이동 중단 (덮어쓰기 없음):', str(exc), file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
