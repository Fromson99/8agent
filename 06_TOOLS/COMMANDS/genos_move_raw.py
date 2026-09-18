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
    p.add_argument('--replace-internal-pdf', action='store_true', help='Replace RAW/internal with PDF folders; retain recovery backup')
    p.add_argument('--rollback-internal', type=Path)
    args = p.parse_args(argv)
    os.umask(0o077)
    data = offline_data_root(ROOT)
    try:
        if args.replace_internal_pdf or args.rollback_internal:
            from lawrag.pipeline import genos_internal_replace
            with plain_path(data / '.raw-migration.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if args.rollback_internal:
                    receipt = json.loads((args.rollback_internal / 'receipt.json').read_text())
                    if receipt['data'] != str(data):
                        raise ValueError('Backup belongs to another data root')
                    result = genos_internal_replace.rollback(args.rollback_internal)
                else:
                    result = genos_internal_replace.replace(data, apply=args.apply)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
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
