"""Read-only live counters, or runtime-only logging around the existing release CLI.

No compiler files, input bindings, model settings or active pointers are rewritten.
"""
import argparse
from contextlib import closing
from datetime import datetime
import functools
import json
import os
from pathlib import Path
import re
import runpy
import sqlite3
import sys
import threading
import time
import traceback
from zoneinfo import ZoneInfo


def load(path):
    if not path.is_file(): return None
    return json.loads(path.read_text())


def counts(path, table, field):
    if not path.is_file(): return None
    # Fixed identifiers, not user-controlled SQL. Read snapshots, never create a DB.
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.2)) as db:
        db.execute('PRAGMA query_only=ON')
        return dict(db.execute(f'SELECT {field},count(*) FROM {table} GROUP BY {field}'))


def snapshot(data, run):
    folder = data / 'TERM_RELEASES' / run
    selection = load(data / 'LOGS' / run / 'structure-selection.json')
    source = load(folder / 'sources/selection.json')
    origin = load(data / 'LOGS' / run / 'selection-origin.json')
    result = {'선택': f"완료 {len(selection['documents'])}건" if selection else '기록 없음',
        '원문 통합': f"완료 {len(source['document_ids'])}건" if source else '완료 기록 없음',
        '용어 후보·검토 계획': '저장됨' if (folder / 'review/plan.json').is_file() else '완료 기록 없음'}
    if origin: result['보류 문서'] = str(origin['omitted_count']) + '건'
    jobs = counts(folder / 'review/review.sqlite', 'job', 'status')
    if jobs is None:
        result['용어·정의 LLM 검토'] = '대기 또는 계획 생성 중 (전체 수 미확정)'
    else:
        total = sum(jobs.values())
        done, running, failed = (jobs.get(s, 0) for s in ('complete', 'running', 'failed'))
        remaining = jobs.get('pending', 0) + running
        ended = (folder / 'review/completion.json').is_file()
        result['용어·정의 LLM 검토'] = f'완료 {done}/{total} | 남은 처리 {remaining} | 진행 상태 {running} | 실패 {failed} | 검토 종료 기록 {ended}'
    refs = counts(folder / 'reference-review/review.sqlite', 'case_record', 'state')
    if refs is None:
        result['명시 참조 LLM 보정'] = '대기 또는 기준 색인 생성 중 (전체 수 미확정)'
    else:
        total = sum(refs.values())
        done = sum(refs.get(s, 0) for s in ('APPROVED', 'REJECTED', 'UNKNOWN', 'DETERMINISTIC', 'DATA_GAP', 'NO_CANDIDATES'))
        remaining = sum(refs.get(s, 0) for s in ('CANDIDATES_READY', 'MODEL_PENDING', 'MODEL_FAILED', 'MODEL_UNKNOWN', 'VALIDATED'))
        retry = sum(refs.get(s, 0) for s in ('MODEL_FAILED', 'MODEL_UNKNOWN'))
        result['명시 참조 LLM 보정'] = f'종료 판정 {done}/{total} | 남은 판정 {remaining} | 실패·미확인 {retry} (자료부족·후보없음은 해결 성공이 아님)'
    result['문서–용어 연결·기준 색인'] = '세대 결과 저장됨' if (folder / 'serving-baseline/result.json').is_file() else '완료 기록 없음 (실행 모드에서 내부 기능 로그 표시)'
    result['최종 색인·서빙 자산 검증'] = 'release 영수증 저장됨; 무결성 인증은 별도 verify 필요' if (folder / 'release.json').is_file() else '완료 기록 없음'
    return result


def processes(root, run):
    result = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid(): continue
        try:
            args = proc.joinpath('cmdline').read_bytes().decode().split('\0')
            if '--run-id' in args and args[args.index('--run-id')+1] == run and proc.joinpath('cwd').resolve() == root:
                if any('pipeline.py' in a or 'genos_release_progress' in a for a in args):
                    result.append(int(proc.name))
        except (OSError, ValueError, IndexError, UnicodeError): pass
    return sorted(result)


class Display:
    def __init__(self):
        self.lock = threading.RLock()
        self.stack = []
        self.started = time.monotonic()
        self.last_values = {}
        self.last_scope = None
        self.last_processes = None
    def emit(self, message):
        with self.lock:
            stamp = datetime.now(ZoneInfo('Asia/Seoul')).strftime('%H:%M:%S KST')
            print(f'[{stamp}] {message}', flush=True)
    def wrap(self, module, name, label):
        if not callable(getattr(module, name, None)):
            self.emit(f'로그 호환: {label} / {name} 함수가 현장 코드에 없음; 해당 로그만 생략 (기능 추가·검사 우회 없음)')
            return None
        original = getattr(module, name)
        @functools.wraps(original)
        def call(*args, **kwargs):
            started = time.monotonic()
            with self.lock: self.stack.append((label, started))
            self.emit('기능 시작: ' + label)
            try:
                value = original(*args, **kwargs)
                self.emit(f'기능 반환: {label} | 경과 {time.monotonic()-started:.1f}초 (전체 완료 여부는 결과 상태 확인)')
                return value
            except BaseException as exc:
                self.emit(f'기능 중단: {label} | {type(exc).__name__}: {exc}')
                traceback.print_exc()
                raise
            finally:
                with self.lock: self.stack.pop()
        setattr(module, name, call)
        return original
    def show(self, data, run):
        try:
            values = snapshot(data, run)
            with self.lock:
                scope = (str(data), run)
                if self.last_scope != scope:
                    self.last_values = {}
                    self.last_scope = scope
                changed = {label: value for label, value in values.items()
                           if self.last_values.get(label) != value}
                for label, value in changed.items(): self.emit(label + ': ' + value)
                self.last_values = dict(values)
                if self.stack:
                    label, started = self.stack[-1]
                    self.emit(f'현재 기능: {label} | 기능 경과 {time.monotonic()-started:.1f}초 (경과 시간은 처리 성공의 증거가 아님)')
                elif not changed:
                    self.emit(f'저장된 상태 변화 없음 | 관측 경과 {time.monotonic()-self.started:.1f}초 (실행·정상 여부는 미확인)')
        except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
            self.emit(f'진행 스냅샷 오류: {type(exc).__name__}: {exc}')
            traceback.print_exc()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id', default='financial-risk-success-20261001-r1')
    p.add_argument('--build', action='store_true', help='Resume existing build with function logging; do not run alongside existing build')
    p.add_argument('--selected-only', action='store_true', help='Build only the verified structure selection, with no legacy base generation')
    p.add_argument('--glossary-corpus-policy', choices=['append', 'replace'], default='append')
    p.add_argument('--once', action='store_true')
    p.add_argument('--interval', type=float, default=10)
    a = p.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', a.run_id) or not 1 <= a.interval <= 60:
        p.error('Invalid run ID or interval')
    root = Path.cwd().resolve()
    data = Path(os.environ.get('GENOS_DATA_ROOT', '/workspace/01_DATA')).resolve(strict=True)
    d = Display()
    d.emit('후속 BUILD 재개' if a.build else '읽기 전용 진행 감시')
    d.emit('시간 ETA·전체 완료율은 계산하지 않음; 저장된 작업 수와 기능별 경과 표시. 서빙 활성화 없음.')
    if not a.build:
        try:
            while True:
                pids = processes(root, a.run_id)
                if pids != d.last_processes:
                    d.emit('관측된 동일 run 실행 PID=' + str(pids) + ' (없으면 다른 checkout·종료 여부 확인)')
                    d.last_processes = pids
                d.show(data, a.run_id)
                if a.once: return 0
                time.sleep(a.interval)
        except KeyboardInterrupt:
            d.emit('감시만 종료; 구축 프로세스는 중단하지 않음')
            return 0
    if processes(root, a.run_id):
        raise ValueError('Existing build active; use watch mode in another terminal')
    sys.path.insert(0, str(root / '02_BACKEND'))
    from lawrag.pipeline import document_release as release, glossary_review, term_generation
    from lawrag.pipeline import glossary_document_update, reference_resolution
    bindings = [(release, 'selected_sources', '선택 원문·영수증 검증'),
        (release, 'merge_sources', '원문 통합'), (glossary_document_update, 'augment', '문서 정의·용어 후보 준비'),
        (glossary_document_update.definitions, 'add', '준비: 본문 정의·조문 위치·명시 참조 단서 추출'),
        (glossary_document_update, 'replace_corpus', '준비: 새 용어집 사본의 과거 문서 근거 분리'),
        (glossary_document_update, 'refresh_occurrences', '준비: 용어 출현 위치 재탐색'),
        (glossary_review, 'prepare', '용어 검토 계획'), (glossary_review, 'complete', '용어 검토·완료본 생성'),
        (glossary_review, 'run', '용어·정의 LLM 검토'),
        (release, 'build_generation', '문서 연결·색인 세대 생성'),
        (term_generation.glossary_linking, 'project', '문서–용어 연결'),
        (term_generation, 'publish', '원문 세대 저장'),
        (term_generation, 'compile_index', '용어·정의·참조 navigation 색인'),
        (term_generation.fulltext, 'build', '원문 fulltext 색인'),
        (reference_resolution, 'advance', '명시 참조 후보·LLM 보정'),
        (reference_resolution, 'run', '명시 참조 LLM 호출'),
        (reference_resolution, 'apply', '검증된 참조 보정 반영'),
        (release, 'verify_assets', '최종 서빙 자산 검증')]
    installed = []
    finished = False
    original_argv = sys.argv
    stop = threading.Event()
    def heartbeat():
        while not stop.wait(a.interval): d.show(data, a.run_id)
    monitor = threading.Thread(target=heartbeat, daemon=True)
    try:
        for module, name, label in bindings:
            original = d.wrap(module, name, label)
            if original is not None: installed.append((module, name, original))
        profile = data / 'LOGS/financial-risk-full-e2e-20260930-r3/reference-model-profile.json'
        base = '/nfs-root/diamo/8-agent/term-releases/fulltext-repair-20260924T071754Z-31987d27/generation'
        sys.argv = ['06_TOOLS/pipeline.py', 'document-release', 'build', '--run-id', a.run_id]
        if not a.selected_only:
            sys.argv.extend(['--base-generation', base])
        sys.argv.extend(['--reference-model-profile', str(profile), '--max-review-jobs', '100',
                        '--max-reference-cases', '10000', '--reference-batch-size', '8'])
        if a.glossary_corpus_policy != 'append':
            sys.argv.extend(['--glossary-corpus-policy', a.glossary_corpus_policy])
        d.emit('원문 입력: ' + ('이번 구조화 선택본만; 예전 NFS 세대 제외' if a.selected_only else '선택본 + 명시된 기존 세대'))
        d.emit('용어집 문서 근거 정책: ' + a.glossary_corpus_policy)
        monitor.start()
        d.show(data, a.run_id)
        runpy.run_path(str(root / '06_TOOLS/pipeline.py'), run_name='__main__')
        finished = True
    except SystemExit as exc:
        if exc.code in (None, 0, 3):
            d.emit('BUILD 종료 코드=' + str(exc.code) + (' (남은 작업은 같은 명령으로 재개)' if exc.code == 3 else ''))
            finished = True
        else:
            d.emit('BUILD 실패 코드=' + str(exc.code) + ' | 실행 명령=' + repr(sys.argv))
            traceback.print_exc()
        raise
    except BaseException as exc:
        d.emit(f'BUILD 실패: {type(exc).__name__}: {exc} | 실행 명령={sys.argv!r}')
        traceback.print_exc()
        raise
    finally:
        stop.set()
        if monitor.is_alive(): monitor.join(timeout=1)
        for module, name, original in reversed(installed): setattr(module, name, original)
        sys.argv = original_argv
        if finished: d.show(data, a.run_id)


if __name__ == '__main__':
    main()
