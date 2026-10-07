"""Durable append-only build events and bounded live heartbeats; no core edits."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from collections import deque
import csv
import functools
import json
import os
from pathlib import Path
import threading
import time


def atomic(path, value):
    path = Path(path)
    temporary = path.with_name('.' + path.name + '-' + str(os.getpid()))
    with temporary.open('w', encoding='utf-8') as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write('\n'); out.flush(); os.fsync(out.fileno())
    os.replace(temporary, path)


class BuildLog:
    def __init__(self, directory, *, interval=5, terminal=None):
        import sys
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.terminal = terminal or sys.stdout
        self.events = (self.directory / 'events.jsonl').open('a', encoding='utf-8', buffering=1)
        self.timings = (self.directory / 'phases.csv').open('a', encoding='utf-8', newline='', buffering=1)
        self.csv = csv.writer(self.timings)
        if self.timings.tell() == 0:
            self.csv.writerow(['time_utc', 'phase', 'status', 'elapsed_seconds'])
        self.lock = threading.RLock()
        previous = self.directory / 'current.json'
        sequence = json.loads(previous.read_text()).get('seq', 0) if previous.is_file() else 0
        self.stacks, self.seq, self.last, self.total_started = {}, sequence, None, time.monotonic()
        self.last_current_write = 0.0
        self.progress_states = {}
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._heartbeat, args=(interval,), daemon=True)
        self.thread.start()

    def emit(self, phase, status, **details):
        from semantic_runtime.genos_backend import safe
        with self.lock:
            self.seq += 1
            row = safe({'seq': self.seq, 'time_utc': datetime.now(timezone.utc).isoformat(),
                        'phase': phase, 'status': status,
                        'total_elapsed_seconds': round(time.monotonic() - self.total_started, 3), **details})
            self.last = row
            line = json.dumps(row, ensure_ascii=False)
            self.events.write(line + '\n')
            self.terminal.write('REBUILD ' + line + '\n'); self.terminal.flush()
            if status in ('RUNNING', 'PROGRESS') and details.get('task'):
                count = f"{details.get('completed')}/{details.get('total')} {details.get('unit')}"
                eta = details.get('remaining_seconds')
                estimate = f"현재 처리 예상 잔여 {eta:.0f}초" if eta is not None else '현재 처리 예상 잔여: 측정 중/계수 없는 구간'
                self.terminal.write(f"진행 {details['task']}: {count} | {details.get('percent')}% | "
                                    f"최근 {details.get('recent_units_per_second')}건/초 | {estimate} | 전체 잔여: 후속 단계 미측정\n")
                self.terminal.flush()
            now = time.monotonic()
            if status in ('FAILED', 'INTERRUPTED', 'FINISHED') or now - self.last_current_write >= 1:
                atomic(self.directory / 'current.json', row)
                self.last_current_write = now
            if status in ('DONE', 'FAILED', 'INTERRUPTED'):
                self.csv.writerow([row['time_utc'], phase, status, details.get('elapsed_seconds', '')])
            return row

    @contextmanager
    def phase(self, name, **details):
        thread = threading.get_ident()
        started = time.monotonic()
        with self.lock:
            self.stacks.setdefault(thread, []).append((name, started, details))
        self.emit(name, 'START', **details)
        try:
            yield
        except BaseException as error:
            self.emit(name, 'INTERRUPTED' if isinstance(error, KeyboardInterrupt) else 'FAILED',
                      elapsed_seconds=round(time.monotonic() - started, 3),
                      exception=type(error).__name__, error=str(error), **details)
            raise
        else:
            self.emit(name, 'DONE', elapsed_seconds=round(time.monotonic() - started, 3), **details)
        finally:
            with self.lock:
                self.stacks[thread].pop()
                if not self.stacks[thread]: self.progress_states.pop(thread, None)

    def progress(self, *, task, completed, total, unit):
        """Called by the processing thread after actual work; never query locked output DBs."""
        thread, now = threading.get_ident(), time.monotonic()
        changed = False
        with self.lock:
            state = self.progress_states.get(thread)
            if state is None or state['task'] != task:
                state = dict(task=task, completed=0, total=total, unit=unit,
                             phase=self.stacks.get(thread, [('processing', now, {})])[-1][0],
                             started=now, last_advance=now, samples=deque([(now, 0)], maxlen=120))
                self.progress_states[thread] = state
                changed = True
            finished = total is not None and completed == total and state['completed'] < completed
            if completed > state['completed']: state['last_advance'] = now
            state.update(completed=completed, total=total)
            # Sample once per second; preserve accurate counters on every call.
            if now-state['samples'][-1][0] >= 1: state['samples'].append((now, completed))
            phase = self.stacks.get(thread, [('processing', now, {})])[-1][0]
        if changed or finished: self.emit(phase, 'PROGRESS', **self.progress_snapshot(thread, now))

    def progress_snapshot(self, thread, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            state = self.progress_states.get(thread)
            stack = self.stacks.get(thread, [])
            if not state or not stack or state['phase'] != stack[-1][0]:
                return {'remaining': 'not_measured', 'overall_eta': 'unmeasured_later_stages'}
            done, total = state['completed'], state['total']
            elapsed = now-state['started']
            samples = list(state['samples'])
            recent = next((s for s in reversed(samples) if s[0] <= now-60), samples[0])
            span = now-recent[0]
            speed = (done-recent[1])/span if span > 0 else 0
            average = done/elapsed if elapsed > 0 else 0
            stale = now-state['last_advance']
            # Counts are exact; ETA is an estimate, and never covers unmeasured finalization.
            eta = (total-done)/speed if total is not None and done < total and done >= 2 and elapsed >= 10 and speed > 0 and stale < 30 else None
            estimates = [(total-done)/r for r in (speed, average) if total is not None and r > 0]
            result = dict(task=state['task'], completed=done, total=total, unit=state['unit'],
                          percent=round(100*done/total,2) if total else None,
                          recent_units_per_second=round(speed,3), average_units_per_second=round(average,3),
                          seconds_since_last_completion=round(stale,1),
                          remaining_seconds=round(eta,1) if eta is not None else None,
                          estimated_task_finish_utc=(datetime.now(timezone.utc)+timedelta(seconds=eta)).isoformat() if eta is not None else None,
                          remaining='estimated_current_task_only' if eta is not None else 'warming_up_or_uncounted_or_stalled',
                          overall_eta='unmeasured_later_stages')
            if eta is not None: result['estimate_comparison_seconds'] = [round(min(estimates),1), round(max(estimates),1)]
            return result

    def _heartbeat(self, interval):
        while not self.stop.wait(interval):
            with self.lock:
                active = [(thread, stack[-1], [x[0] for x in stack]) for thread,stack in self.stacks.items() if stack]
            for thread, (name, started, details), chain in active:
                self.emit(name, 'RUNNING', elapsed_seconds=round(time.monotonic() - started, 3),
                          active_phases=chain, **self.progress_snapshot(thread), **details)

    def close(self, status):
        self.stop.set(); self.thread.join(timeout=2)
        self.emit('run', 'FINISHED', exit_status=status)
        (self.directory / 'summary.txt').write_text(
            '종료 코드: ' + str(status) + '\n전체 경과(초): ' + str(round(time.monotonic() - self.total_started, 3))
            + '\n전체 출력: run.log\n단계 이벤트: events.jsonl\n단계 시간: phases.csv\n현재/최종 상태: current.json\n'
            + 'GENOS 현장 서빙·질의 검증: 미확인\n', encoding='utf-8')
        self.events.flush(); os.fsync(self.events.fileno())
        self.events.close(); self.timings.close()


@contextmanager
def observe(log):
    """Wrap installed callables only during this process, retaining native file pins."""
    import shutil
    from lawrag.pipeline import glossary_linking, glossary_knowledge, term_generation, term_serving_bundle
    from lawrag.pipeline import reference_resolution, document_release
    from semantic_runtime import full_glossary, navigation_storage, term_index, fulltext
    targets = [
        (glossary_linking, 'project', 'document-term-links'),
        (term_generation, 'publish', 'source-generation'),
        (term_serving_bundle, 'prepare_assets', 'glossary-serving-assets'),
        (glossary_knowledge, 'verify', 'glossary-knowledge-verification'),
        (full_glossary.Glossary, '__init__', 'glossary-search-cache'),
        (term_generation, 'compile_index', 'navigation-index'),
        (term_generation.fulltext, 'build', 'fulltext-index'),
        (navigation_storage, 'finalize', 'navigation-audit'),
        (reference_resolution, 'advance', 'explicit-reference-model'),
        (reference_resolution, 'apply', 'explicit-reference-apply'),
        (document_release, '_copy_reference_audit', 'copy-reference-audit'),
        (document_release, '_verify_navigation_audit', 'verify-navigation-audit'),
        (document_release, 'verify_assets', 'verify-generation-assets'),
        (term_serving_bundle, 'verify_assets', 'verify-generation-assets'),
        (shutil, 'copyfile', 'copy-file'),
        (term_serving_bundle, 'sha', 'asset-file-hash'),
        (glossary_knowledge, 'sha', 'knowledge-file-hash'),
        (full_glossary, 'sha', 'glossary-file-hash'),
    ]
    saved = []
    hooks = []
    try:
        for module in (glossary_linking, term_index, fulltext):
            hooks.append((module, hasattr(module, '_BUILD_PROGRESS'), getattr(module, '_BUILD_PROGRESS', None)))
            module._BUILD_PROGRESS = log.progress
        for module, attribute, label in targets:
            original = getattr(module, attribute, None)
            if not callable(original):
                continue
            @functools.wraps(original)
            def wrapper(*args, _fn=original, _label=label, **kwargs):
                paths = [str(x) for x in args[:2] if isinstance(x, (str, Path))]
                with log.phase(_label, paths=paths):
                    return _fn(*args, **kwargs)
            wrapper.__code__ = wrapper.__code__.replace(co_filename=original.__code__.co_filename)
            saved.append((module, attribute, original))
            setattr(module, attribute, wrapper)
        yield
    finally:
        for module, existed, original in hooks:
            if existed: module._BUILD_PROGRESS = original
            else: delattr(module, '_BUILD_PROGRESS')
        for module, attribute, original in reversed(saved):
            setattr(module, attribute, original)
