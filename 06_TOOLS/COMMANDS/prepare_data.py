#!/usr/bin/env python3
"""Local/GENOS shared RAW preparation. Preview first; --apply to migrate/import."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '02_BACKEND'))


def main(argv=None):
    from lawrag.pipeline.genos_stages import offline_data_root, plain_path
    from lawrag.pipeline.genos_raw_move import move, scan
    from lawrag.pipeline.raw_prepare import import_packages, STAGES
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group()
    group.add_argument('--source', help='기존 원문 corpus 폴더만 이동; 패키지를 지정하지 마세요')
    group.add_argument('--from-packages', help='명시적 공개 외규 패키지 선택 JSON')
    p.add_argument('--apply', action='store_true')
    args = p.parse_args(argv)
    os.umask(0o077)
    data = offline_data_root(ROOT)

    def legacy_source(value):
        source = plain_path(value).resolve()
        for name in ('PACKAGES', 'ACTIVE', 'SOURCE_SETS', 'CATALOG', 'INDEXES',
                     'SEMANTIC', 'wiki', 'BACKUPS', 'RETIREMENT'):
            protected = (data / name).resolve()
            if source == protected or protected in source.parents or source in protected.parents:
                raise ValueError('불변/보호 데이터는 이동 대상이 아닙니다: ' + str(source))
        return source

    def prepare():
        target = plain_path(data / 'RAW')
        legacy = plain_path(ROOT / 'data/corpus')
        if args.source:
            result = move(legacy_source(args.source), data, apply=args.apply)
        elif args.from_packages:
            result = import_packages(ROOT, data, args.from_packages, apply=args.apply)
        elif (data / 'LOGS/raw-package-import/receipt.json').exists():
            if legacy.exists():
                raise ValueError('RAW와 data/corpus가 동시에 있습니다. 원문 선택을 명시하세요.')
            result = import_packages(ROOT, data, ROOT / '08_DEPLOYMENT/CONFIG/raw-source-packages.json', apply=args.apply)
        elif (data / 'LOGS/raw-migration/receipt.json').exists() or legacy.exists():
            result = move(legacy, data, apply=args.apply)
        elif target.is_dir():
            result = {'status': 'RAW_EXISTS', 'target': str(target), 'files': len(scan(target)),
                      'note': '기존 RAW 보존; 내용/manifest 입력 검사는 build-data-stages --check-only로 실행'}
        else:
            selection = ROOT / '08_DEPLOYMENT/CONFIG/raw-source-packages.json'
            if not selection.is_file():
                raise ValueError('원문 없음. --source로 기존 corpus 폴더를 지정하세요.')
            result = import_packages(ROOT, data, selection, apply=args.apply)
        if args.apply:
            for name in STAGES:
                plain_path(data / name).mkdir(parents=True, exist_ok=True)
        return result

    try:
        if args.apply:
            data.mkdir(parents=True, exist_ok=True)
            with plain_path(data / '.raw-migration.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = prepare()
        else:
            result = prepare()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print('원문 준비 중단 (기존 자료 보존): ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
