#!/usr/bin/env python3
"""One-document GENOS structure diagnostics. No model calls; no cache overwrite.

Run from DEV: python3 TRANSFER/genos_structure_timing.py.txt --from-run external-nfs-001
Add --rebuild to time the installed parser into a fresh diagnostic directory.
Python 3.11+, standard-library launcher; uses the installed GENOS pipeline.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
import functools
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import threading
import time


def plain(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Symlink not allowed: ' + str(path))
    return path


class Timing:
    def __init__(self, directory):
        self.started = time.perf_counter()
        self.stream = (directory / 'timing.jsonl').open('x', encoding='utf-8', buffering=1)
        self.console = (directory / 'timing.log').open('x', encoding='utf-8', buffering=1)
        self.stack, self.rows, self.patches = [], defaultdict(lambda: {
            'calls': 0, 'seconds_inclusive': 0., 'seconds_self': 0., 'cpu_seconds': 0., 'failures': 0}), []
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.heartbeat, daemon=True)
        self.thread.start()

    def emit(self, event, stage, **values):
        with self.lock:
            row = dict(at=datetime.now(timezone.utc).isoformat(), event=event,
                       stage=stage, elapsed=round(time.perf_counter()-self.started, 3), **values)
            self.stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            message = f'[{event}] {stage} ' + ' '.join(f'{k}={v}' for k, v in values.items())
            print(message, flush=True)
            self.console.write(message + '\n')

    def heartbeat(self):
        while not self.stop.wait(10):
            with self.lock:
                if self.stack:
                    name, started, _ = self.stack[-1]
                    self.emit('WAIT', name, seconds=round(time.perf_counter()-started, 1))

    @contextmanager
    def stage(self, name, quiet=False):
        started = time.perf_counter()
        cpu_started = time.process_time()
        frame = [name, started, 0.]
        with self.lock:
            self.stack.append(frame)
        if not quiet:
            self.emit('START', name)
        failed = False
        try:
            yield
        except BaseException:
            failed = True
            raise
        finally:
            elapsed = time.perf_counter()-started
            with self.lock:
                self.stack.pop()
                if self.stack:
                    self.stack[-1][2] += elapsed
                row = self.rows[name]
                row['calls'] += 1
                row['seconds_inclusive'] += elapsed
                row['seconds_self'] += max(0., elapsed-frame[2])
                row['cpu_seconds'] += time.process_time()-cpu_started
                row['failures'] += int(failed)
            if not quiet:
                self.emit('FAIL' if failed else 'END', name, seconds=round(elapsed, 3),
                          cpu_seconds=round(time.process_time()-cpu_started, 3))

    def wrap(self, module, attr, label, quiet=False):
        original = getattr(module, attr, None)
        if not callable(original):
            self.emit('UNAVAILABLE', label, symbol=attr)
            return
        @functools.wraps(original)
        def timed(*args, **kwargs):
            with self.stage(label, quiet=quiet):
                return original(*args, **kwargs)
        self.patches.append((module, attr, original))
        setattr(module, attr, timed)

    def close(self):
        for module, attr, original in reversed(self.patches):
            setattr(module, attr, original)
        self.stop.set()
        self.thread.join(timeout=2)
        self.stream.close()
        self.console.close()


def select_cache(data, args, timing):
    if args.cache:
        folder = plain(args.cache)
        folder.relative_to(plain(data / 'STRUCTURE'))
        return folder, json.loads((folder / 'structure-receipt.json').read_text())
    document = args.document
    if not document:
        run = plain(data / 'LLM' / args.from_run)
        plans = list(run.glob('*/plan.json'))
        if len(plans) != 1:
            raise ValueError(f'LLM 문서 폴더 {len(plans)}개: --document에 RAW 기준 정확한 상대 경로를 지정하세요')
        work = json.loads(plain(plans[0]).read_text())
        files = work.get('files', [])
        if len(files) != 1:
            raise ValueError('한 문서 계획이 아닙니다. --document를 지정하세요')
        document = files[0]['relative']
    matches, unreadable = [], 0
    for number, folder in enumerate((data / 'STRUCTURE').iterdir(), 1):
        if folder.name.startswith('.'):
            continue
        path = plain(folder) / 'structure-receipt.json'
        if not path.is_file():
            continue
        try:
            receipt = json.loads(path.read_text())
        except (OSError, ValueError):
            unreadable += 1
            continue
        if receipt.get('input_row', {}).get('relative') == document:
            matches.append((folder, receipt))
        if number % 100 == 0:
            timing.emit('SCAN', '캐시 영수증 탐색', examined=number, matched=len(matches))
    if unreadable:
        timing.emit('WARNING', '캐시 영수증 탐색', unreadable_receipts=unreadable)
    if len(matches) != 1:
        for folder, _ in matches:
            timing.emit('MATCH', '캐시 후보', path=str(folder))
        raise ValueError(f'정확히 일치하는 캐시 {len(matches)}개: --cache로 한 경로를 지정하세요')
    return matches[0]


def summarize_source(folder, timing):
    path = plain(folder / 'authoring-source.sqlite')
    # After verification/rebuild, source stores are closed and immutable.
    with timing.stage('SQLite 작업 수·반복 저장량 조회'):
        with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as db:
            db.execute('PRAGMA query_only=ON')
            counts = {t: db.execute('SELECT count(*) FROM '+t).fetchone()[0]
                      for t in ('document', 'source_block', 'source_unit', 'authoring_job')}
            counts['job_json_characters'] = db.execute(
                'SELECT coalesce(sum(length(input_json)),0) FROM authoring_job').fetchone()[0]
            counts['sqlite_bytes'] = path.stat().st_size
            timing.emit('COUNTS', '구조화 산출물', **counts)
            return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.', help='GENOS DEV 코드 루트')
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--from-run', help='LLM 문서가 하나인 기존 run-id에서 선택')
    selection.add_argument('--document', help='RAW 기준 정확한 상대 경로')
    selection.add_argument('--cache', help='기존 STRUCTURE/<지문> 절대 경로')
    parser.add_argument('--rebuild', action='store_true', help='별도 진단 폴더에 신규 구조화; 기본은 캐시 검증')
    parser.add_argument('--timeout', type=int, default=300, help='DOC 변환 제한 초')
    args = parser.parse_args(argv)
    if args.timeout < 1 or (args.from_run and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', args.from_run)):
        parser.error('timeout/run-id 값 오류')
    root = plain(args.root)
    if not (root / '02_BACKEND/lawrag/pipeline/genos_stages.py').is_file():
        parser.error('DEV 루트에서 실행하세요. 설치된 genos_stages.py가 필요합니다')
    data = plain(root / '01_DATA')
    # Fixed GENOS four-stage layout; do not guess a different active dataset.
    if not (data / 'STRUCTURE').is_dir():
        parser.error('01_DATA/STRUCTURE가 없습니다')
    logs = plain(data / 'LOGS')
    logs.mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='structure-timing-', dir=logs))
    timing = Timing(out)
    summary = dict(format='genos-structure-timing-v1', status='RUNNING', mode='rebuild' if args.rebuild else 'cache',
                   llm_calls=0, note='Inclusive times overlap; self times exclude instrumented children. Not a quality evaluation.',
                   output=str(out), python=sys.version, experiment_id='ADR-0343-experiment-v1', arm_id='instrumentation')
    code = 1
    try:
        timing.emit('OUTPUT', '진단 저장 위치', path=str(out))
        with timing.stage('설치 코드 import'):
            sys.path.insert(0, str(root / '02_BACKEND'))
            from lawrag.pipeline import genos_stages as stages, genos_build as build, genos_doc as doc
            from semantic_runtime import contracts
        if Path(build.ROOT).resolve() != root.resolve():
            raise ValueError('Imported code root differs from --root')
        with timing.stage('한 문서 캐시 선택'):
            folder, receipt = select_cache(data, args, timing)
        row, plan = receipt['input_row'], receipt['plan']
        summary.update(document=row['relative'], document_id=row['document_id'],
                       source_sha256=row['sha256'], source_cache=str(folder))
        timing.emit('DOCUMENT', '대상 문서', document=row['relative'], mode=summary['mode'])
        with timing.stage('코드 지문 기록'):
            summary['code_sha256'] = {str(Path(m.__file__).relative_to(root)): contracts.sha(m.__file__)
                                     for m in (stages, build, doc, contracts)}
            summary['runner_sha256'] = contracts.sha(__file__)
        # Identify parser dependencies before wrapping functions, preserving inspect.getsource semantics.
        with timing.stage('파서·패키지 지문 계산'):
            dependencies = stages.parser_identity(root)
        summary['parser_identity_matches'] = dependencies == receipt['parser']
        timing.emit('IDENTITY', '캐시 파서 지문', matches=summary['parser_identity_matches'])
        for module in (stages, build, doc):
            timing.wrap(module, 'sha', 'SHA256 파일 읽기', quiet=True)
        for module, attr, label in (
            (stages, 'files_hashes', '캐시 전체 파일 해시 순회'),
            (stages, 'verify_structure', '기존 구조화 무결성 검증'),
            (doc, 'prepare', 'DOC 변환·입력 준비'),
            (build, 'ingest_files', '파싱·구조화·기계적 검사·저장'),
            (build, 'registered_ingest', '등록 양식 파싱'),
            (build, '_build_source_store', '구조 결과 → source SQLite'),
            (build, 'source_jobs', 'source SQLite·LLM 작업 생성'),
            (build, 'atomic', 'JSON 원자 저장'),
        ):
            timing.wrap(module, attr, label, quiet=(attr == 'atomic'))
        # Imports are version-sensitive; report unavailable detail explicitly.
        with timing.stage('파서 세부 계측 준비'):
            from lawrag.core import ingest
            timing.wrap(ingest, 'ingest', '형식별 기본 파서')
            timing.wrap(ingest, 'ingest_rulehtml_bytes', '규정 HTML 파서')
            try:
                from lawrag.pipeline import genos_admission
            except ImportError:
                timing.emit('UNAVAILABLE', '기계적 구조 검사', symbol='genos_admission (구버전)')
            else:
                timing.wrap(genos_admission, 'validate_structure', '기계적 구조 검사')
        source = plain(row['path'])
        source.relative_to(plain(data / 'RAW'))
        with timing.stage('선택 원문 해시 확인'):
            if stages.sha(source) != row['sha256']:
                raise ValueError('Source changed since cached receipt')
        if args.rebuild:
            # Uses the installed implementation with one exact receipt row.
            # Fresh data directory guarantees existing caches/queues remain intact.
            with timing.stage('한 문서 신규 구조화 전체'):
                folder, _ = stages.structure(row, plan, out / 'scratch', dependencies,
                                             args.timeout, lambda message: timing.emit('PIPELINE', str(message)))
        else:
            stages.verify_structure(folder)
        summary['counts'] = summarize_source(folder, timing)
        summary['result_folder'] = str(folder)
        summary['status'], code = 'COMPLETED', 0
    except KeyboardInterrupt:
        summary['status'], code = 'INTERRUPTED', 130
        timing.emit('INTERRUPTED', '진단 중단; 기존 원본·캐시 보존')
    except Exception as exc:
        summary.update(status='FAILED', error_type=type(exc).__name__, error=str(exc))
        timing.emit('ERROR', type(exc).__name__, message=str(exc))
    finally:
        summary['seconds_total'] = time.perf_counter()-timing.started
        summary['timings'] = dict(timing.rows)
        timing.emit('SUMMARY', '측정 구간별 집계 (상위 시간에 하위 포함)')
        for label, values in sorted(timing.rows.items(), key=lambda x: -x[1]['seconds_self']):
            timing.emit('TOTAL', label, calls=values['calls'],
                        inclusive=round(values['seconds_inclusive'], 3), own_seconds=round(values['seconds_self'], 3),
                        cpu_seconds=round(values['cpu_seconds'], 3),
                        failures=values['failures'])
        (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
        timing.emit('RESULT', summary['status'], path=str(out / 'summary.json'))
        timing.close()
    return code


if __name__ == '__main__':
    raise SystemExit(main())
