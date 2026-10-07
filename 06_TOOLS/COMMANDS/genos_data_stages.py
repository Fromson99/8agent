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
    p.add_argument('--only-internal', action='store_true', help='Select every supported format under RAW/internal, independently of the external document scope')
    p.add_argument('--only-internal-pdf', action='store_true', help='Select RAW/internal PDFs without reading external source files')
    p.add_argument('--limit', type=int, help='Positive document limit; requires --only-internal-pdf')
    p.add_argument('--document-scope', type=Path, help='Hash-pinned selection; defaults to CATALOG/BUILD_SCOPE.json when configured')
    p.add_argument('--team', action='append', help='Select a team in the registered RAW team layout; repeatable')
    p.add_argument('--unzip', choices=['on', 'off'], default='on')
    p.add_argument('--xml-markdown', choices=['on', 'off'], default='on')
    p.add_argument('--pdf-conversion', choices=['on', 'off'], default=os.environ.get('GENOS_PDF_CONVERSION', 'on'))
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--execute', action='store_true')
    mode.add_argument('--check-only', action='store_true')
    args, rest = p.parse_known_args(argv)
    if (args.only_internal_pdf or args.only_internal) and args.exclude_internal:
        p.error('--only-internal-pdf and --exclude-internal conflict')
    if args.limit is not None and (not args.only_internal_pdf or args.limit < 1):
        p.error('--limit requires --only-internal-pdf and a positive value')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', args.run_id):
        p.error('run-id는 영문/숫자/._- 1~80자')
    forbidden = {'--input-root', '--external-root', '--build-dir', '--data-root', '--source', '--resume'}
    if any(a.split('=')[0] in forbidden for a in rest):
        p.error('경로는 논리 data root로 고정합니다. 같은 run-id는 자동 재개합니다.')
    data = genos_stages.offline_data_root(ROOT)
    if (data / 'LOGS' / args.run_id / 'selection-origin.json').exists():
        p.error('성공 문서 선택으로 고정된 run-id입니다. document-release의 merge/prepare/review/index/build를 사용하세요. 새 구조화에는 새 run-id가 필요합니다.')
    from lawrag.pipeline import document_scope, team_raw, raw_preprocess
    if args.only_internal and (args.document_scope or args.only_internal_pdf):
        p.error('--only-internal conflicts with --document-scope/--only-internal-pdf')
    team_layout = bool(team_raw.config(data)) and not args.document_scope
    if args.team and not team_layout:
        p.error('--team requires prepare-data --team-layout --apply and no explicit document scope')
    if args.team and any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*_team', t) for t in args.team):
        p.error('team must be a directory name ending in _team')
    scope_path = None if args.only_internal or team_layout else (args.document_scope or document_scope.configured(data))
    if scope_path and args.only_internal_pdf:
        p.error('--only-internal-pdf conflicts with the configured document scope')
    raw = genos_stages.plain_path(data / 'RAW')
    if (raw / '.migration-in-progress').exists():
        p.error('원문 이동 미완료. migration receipt를 확인하세요.')
    options = genos_build.parser().parse_args(['build', '--input-root', str(raw),
        '--build-dir', str(data / 'TERM' / args.run_id), *rest])
    if options.timeout < 1:p.error('timeout must be positive')
    if args.stage in {'index', 'all'} and args.execute and not options.glossary_dir:
        from lawrag.pipeline import glossary_linking
        options.glossary_dir=glossary_linking.configured(ROOT,data)
    if args.stage in {'index', 'all'} and args.execute and options.glossary_dir:
        from lawrag.pipeline import glossary_linking
        glossary_linking.binding(options.glossary_dir)
    logs = genos_stages.plain_path(data / 'LOGS' / args.run_id)
    logs.mkdir(parents=True, exist_ok=True)
    for file in logs.iterdir():
        genos_stages.plain_path(file)
    with (logs / 'run.lock').open('a') as lock, genos_stages.plain_path(data / '.raw-migration.lock').open('a') as raw_lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(raw_lock, (fcntl.LOCK_EX if team_layout and args.execute else fcntl.LOCK_SH) | fcntl.LOCK_NB)
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
                preparation = None
                if team_layout:
                    if args.stage != 'index':
                        preparation = raw_preprocess.run(ROOT, data, logs / 'preparation', execute=args.execute,
                            unzip=args.unzip == 'on', xml_md=args.xml_markdown == 'on', pdf=args.pdf_conversion == 'on',
                            only_internal=args.only_internal or args.only_internal_pdf, exclude_internal=args.exclude_internal, teams=args.team,
                            emit=lambda message: (terminal.write(message + '\n'), terminal.flush(), progress.emit(message)))
                    plan, inventory = team_raw.collect(data, options.bindings, emit=progress.emit,
                        only_internal=args.only_internal, only_internal_pdf=args.only_internal_pdf, limit=args.limit,
                        exclude_internal=args.exclude_internal, teams=args.team)
                elif scope_path:
                    plan, inventory = document_scope.collect(data, scope_path, options.bindings,
                        exclude_internal=args.exclude_internal, emit=progress.emit)
                else:
                    plan, inventory = genos_corpus.collect(raw, options.bindings,
                        exclude_internal=args.exclude_internal, skip_invalid=True, emit=progress.emit,
                        only_internal_pdf=args.only_internal_pdf, limit=args.limit, only_internal=args.only_internal)
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
                    if preparation and args.execute:
                        result.update(status='RAW_PREPARED', note='ZIP/XML/PDF 준비 설정 적용 및 입력 검사 완료. 구조화·색인은 별도 단계입니다.')
                else:
                    result = genos_stages.execute(plan, options, data, args.run_id, args.stage, progress=progress, status=status)
                    result['selected_total'] = result['total']
                    result['total'] += input_failed
                    result['skipped'] += input_failed
                    result['passed_percent'] = round(100 * result['passed'] / result['total'], 2) if result['total'] else 0
                    result['skipped_percent'] = round(100 * result['skipped'] / result['total'], 2) if result['total'] else 0
                    result['ok'] = result['ok'] and not input_failed and not source_errors
                if args.execute and args.stage in {'structure', 'all'}:
                    selected_path = logs / 'structure-selection.json'
                    selected = json.loads(selected_path.read_text())
                    selected['input_inventory_valid'] = not input_failed and not source_errors
                    genos_build.atomic(selected_path, selected)
                result.update(input_failed=input_failed, source_errors=source_errors, preparation=preparation)
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
                # A cancelled report must not be rebuilt during cancellation.
            progress.finish('중단됨: 저장된 구조화/청크 결과 보존. 같은 명령으로 재개', status='INTERRUPTED') if progress.state else None
            return 130
        except Exception as exc:
            if status is not None and status.attempt is not None:
                status.finish('FAILED', error=reason(exc))
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
