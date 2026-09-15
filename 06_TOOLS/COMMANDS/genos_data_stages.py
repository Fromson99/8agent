#!/usr/bin/env python3
"""GENOS: 원문 → 전체 구조 추출(재사용) → 용어·정의·참조 → DRAFT."""
from __future__ import annotations
import argparse
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime
import fcntl
import json
import logging
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '02_BACKEND'))


def main(argv=None):
    from lawrag.pipeline import genos_build, genos_corpus, genos_stages
    from lawrag.pipeline.genos_progress import Progress, DetailStream, reason
    from lawrag.pipeline.genos_status import Ledger, export_report
    from semantic_runtime.genos_backend import safe
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id', default='stages-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    p.add_argument('--stage', choices=['raw', 'structure', 'index', 'all'], default='all')
    p.add_argument('--exclude-internal', action='store_true')
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--execute', action='store_true')
    mode.add_argument('--check-only', action='store_true')
    args, rest = p.parse_known_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', args.run_id):
        p.error('run-id는 영문/숫자/._- 1~80자')
    forbidden = {'--input-root', '--external-root', '--build-dir', '--data-root', '--source', '--resume'}
    if any(a.split('=')[0] in forbidden for a in rest):
        p.error('경로는 논리 data root로 고정합니다. 같은 run-id는 자동 재개합니다.')
    data = genos_stages.offline_data_root(ROOT)
    raw = genos_stages.plain_path(data / 'RAW')
    if (raw / '.migration-in-progress').exists():
        p.error('원문 이동 미완료. migration receipt를 확인하세요.')
    options = genos_build.parser().parse_args(['build', '--input-root', str(raw),
        '--build-dir', str(data / 'TERM' / args.run_id), *rest])
    if options.timeout < 1:p.error('timeout must be positive')
    if args.stage!='raw' and args.execute and not options.glossary_dir:
        from lawrag.pipeline import glossary_linking
        options.glossary_dir=glossary_linking.configured(ROOT,data)
    if options.glossary_dir:
        from lawrag.pipeline import glossary_linking
        glossary_linking.binding(options.glossary_dir)
    logs = genos_stages.plain_path(data / 'LOGS' / args.run_id)
    logs.mkdir(parents=True, exist_ok=True)
    for file in logs.iterdir():
        genos_stages.plain_path(file)
    with (logs / 'run.lock').open('a') as lock, genos_stages.plain_path(data / '.raw-migration.lock').open('a') as raw_lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(raw_lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        migration = data / 'LOGS/raw-migration/receipt.json'
        if migration.exists() and json.loads(migration.read_text())['status'] != 'COMPLETED':
            p.error('원문 이동 미완료. genos_move_raw.py --apply를 재실행하세요.')
        terminal = sys.stdout
        progress = Progress(logs, terminal)
        stream = DetailStream(progress)
        handler = logging.StreamHandler(stream)
        logging.getLogger().addHandler(handler)
        # GENOS has its own non-propagating handler, often initialized before
        # redirect_stderr. Route it into detail.log instead of breaking the board.
        from semantic_runtime import observability
        observability.configure()
        owned_handlers = [(h, h.stream) for h in logging.getLogger('genos').handlers
                          if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)]
        for h, _ in owned_handlers:
            h.setStream(stream)
        status = None
        try:
            with redirect_stdout(stream), redirect_stderr(stream):
                # Inventory has no document context; details are saved without flooding the screen.
                plan, inventory = genos_corpus.collect(raw, options.bindings,
                    exclude_internal=args.exclude_internal, skip_invalid=True, emit=progress.emit,
                    internal_pdf_root=data / 'PDF/internal')
                genos_build.atomic(logs / ('inventory-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json'), inventory)
                input_failed = sum(x.get('scope') == 'document' for x in inventory['errors'])
                source_errors = [x for x in inventory['errors'] if x.get('scope') != 'document']
                terminal.write(f'입력: 처리 대상 {len(plan["files"])}문서 | 입력 제외 {input_failed}문서 | 저장소 오류 {len(source_errors)}건\n')
                terminal.flush()
                status = Ledger(logs)
                status.start([{**row, 'route': genos_build.route_summary(row)} for row in plan['files']],
                             args.stage if args.execute else 'raw',
                             excluded=[x for x in inventory['errors'] if x.get('scope') == 'document'],
                             ignored=inventory['excluded'])
                if not args.execute or args.stage == 'raw':
                    result = {'stage': 'raw', 'status': 'INPUT_CHECK_ONLY', 'selected': len(plan['files']),
                              'ok': inventory['ok'],
                              'note': '입력 목록/해시 확인이며 파싱·LLM·임베딩 성공이 아닙니다.'}
                else:
                    result = genos_stages.execute(plan, options, data, args.run_id, args.stage, progress=progress, status=status)
                    result['selected_total'] = result['total']
                    result['total'] += input_failed
                    result['skipped'] += input_failed
                    result['passed_percent'] = round(100 * result['passed'] / result['total'], 2) if result['total'] else 0
                    result['skipped_percent'] = round(100 * result['skipped'] / result['total'], 2) if result['total'] else 0
                    result['ok'] = result['ok'] and not input_failed and not source_errors
                result.update(input_failed=input_failed, source_errors=source_errors)
                receipt = logs / ('result-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json')
                genos_build.atomic(receipt, safe(result))
                status.finish('COMPLETED' if result.get('ok', True) and not source_errors else 'FAILED',
                              error=' / '.join(str(x['source']) + ': ' + x['error'] for x in source_errors))
                export_report(logs)
            progress._newline()
            terminal.write('결과: ' + json.dumps({k: v for k, v in result.items() if k != 'documents'}, ensure_ascii=False) + '\n')
            terminal.write('진행 로그: ' + str(logs / 'progress.log') + '\n')
            terminal.write('문서별 결과: ' + str(receipt) + '\n')
            terminal.write('한눈에 보는 문서 상태표: ' + str(logs / 'doc-status.html') + '\n')
            terminal.write('엑셀용 문서 상태표: ' + str(logs / 'doc-status.csv') + '\n')
            return 0 if result.get('ok', True) else 2
        except KeyboardInterrupt:
            if status is not None and status.attempt is not None:
                status.finish('INTERRUPTED')
                export_report(logs)
            progress.finish('중단됨: 저장된 구조화/청크 결과 보존. 같은 명령으로 재개', status='INTERRUPTED') if progress.state else None
            return 130
        except Exception as exc:
            if status is not None and status.attempt is not None:
                status.finish('FAILED', error=str(exc))
                export_report(logs)
            progress.emit(__import__('traceback').format_exc())
            progress._newline()
            terminal.write('중단: ' + reason(exc) + '\n상세: ' + str(logs / 'detail.log') + '\n')
            return 1
        finally:
            if status is not None:
                status.close()
            logging.getLogger().removeHandler(handler)
            for h, original_stream in owned_handlers:
                h.setStream(original_stream)
            stream.flush()
            progress.close()


if __name__ == '__main__':
    raise SystemExit(main())
