#!/usr/bin/env python3
"""문서별 구조화·LLM·임베딩 마지막 저장 상태 조회 (모델/문서 처리 없음)."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '02_BACKEND'))


def main(argv=None):
    from lawrag.pipeline.genos_stages import offline_data_root
    from lawrag.pipeline.genos_status import validate_run_id, read_report, render_console, export_report
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id', required=True)
    p.add_argument('--failed', action='store_true', help='실패·보류·중단 문서만 표시')
    p.add_argument('--limit', type=int, default=30, help='표 최대 행 수 (0: 전체)')
    p.add_argument('--export', action='store_true', help='같은 로그 폴더에 검색 가능한 HTML 및 CSV 저장')
    args = p.parse_args(argv)
    try:
        validate_run_id(args.run_id)
        if args.limit < 0:
            p.error('--limit는 0 이상이어야 합니다')
        logs = offline_data_root(ROOT) / 'LOGS' / args.run_id
        report = read_report(logs)
        print(render_console(report, failures_only=args.failed, limit=args.limit), end='')
        if not report['recorded']:
            return 2
        if args.export:
            for kind, path in export_report(logs, report).items():
                print(kind.upper() + ': ' + path)
        return 0
    except (ValueError, OSError) as exc:
        p.error(str(exc))


if __name__ == '__main__':
    raise SystemExit(main())
