"""List recent request reports in one explicit date folder; never auto-selects one."""
import argparse
import gzip
import json
import math
import shlex
import sys
from datetime import datetime
from pathlib import Path

ROW_LIMIT = 8*1024*1024
SCAN_LIMIT = 256*1024*1024
MARKER = b'"timing.probe.summary"'


def has_probe(path):
    opener = gzip.open if path.suffix.lower() == '.gz' else open
    seen = 0; tail = b''
    with opener(path, 'rb') as source:
        while True:
            chunk = source.read(1024*1024)
            if not chunk:return '없음'
            seen += len(chunk)
            if MARKER in tail+chunk:return '있음'
            tail = chunk[-len(MARKER):]
            if seen > SCAN_LIMIT:return '확인 불가(크기 초과)'


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('date_folder')
    parser.add_argument('--limit', type=int, default=10)
    args = parser.parse_args(argv)
    root = Path(args.date_folder).expanduser().resolve()
    if not root.is_dir():
        print('FIND_FAILED: 요청 보고서 날짜 폴더를 찾지 못했습니다: '+str(root), file=sys.stderr)
        return 1
    rows, skipped, seen = [], 0, 0
    for path in root.glob('*/legal_agent/_qa/*.row'):
        seen += 1
        try:
            with path.open('rb') as source:
                raw = source.read(ROW_LIMIT+1)
            if len(raw) > ROW_LIMIT:raise ValueError()
            row = json.loads(raw)
            duration = row.get('seconds')
            if type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0:raise ValueError()
            when = datetime.fromisoformat(row['requested_at'])
            report = (path.parent.parent/row['report']).resolve()
            report.relative_to(root)
            if not report.is_file():raise ValueError()
            rows.append((when, duration, report))
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            skipped += 1
    rows.sort(key=lambda r: r[0], reverse=True)
    print(f'요약 기록 {seen}건 / 읽기·값·대상 파일 미확인 {skipped}건. 최근 {min(args.limit, len(rows))}건 — 자동 선택하지 않습니다.')
    for index, (when, duration, report) in enumerate(rows[:max(1, args.limit)], 1):
        try:probe = has_probe(report)
        except OSError:probe = '확인 불가(읽기 실패)'
        print(f'\n[{index}] 요청 {when.isoformat(timespec="seconds")} | 서버 전체 {duration:.3f}초 | 함수·구간 계측 {probe}')
        print(report)
        print('bash ./GENOS_FUNCTION_TIMING_20261024_R2/GENOS_FUNCTION_TIMING_20261024_R2.txt extract '+shlex.quote(str(report))+' --code-root ~/DEV')
    if not rows:
        print('후보 없음: 날짜 폴더와 요약 엑셀의 JSON 보고서 경로를 확인하세요.')
    print('\n화면의 질문 시각·처리 시간과 대조해 같은 요청을 고르세요.')
    print('FIND_COMPLETE')
    return 0


if __name__ == '__main__':
    sys.exit(main())
