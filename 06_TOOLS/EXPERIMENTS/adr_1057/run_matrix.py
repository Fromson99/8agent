"""Guard the frozen 37 x 3 MVP matrix, one fresh case process at a time."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time

from common import ROOT, ART, read, sha
from run_case import (STOP, MATRIX, MEMORY_LIMIT, MIN_AVAILABLE, WALL_SECONDS,
    IntegrityFailure, available_memory, cell_directory, durable, load_frozen,
    process_lock, require, stop)


def finished(cell, freeze_hash):
    directory = cell_directory(cell)
    if not directory.exists():
        return False
    reservation, result = directory / 'reservation.json', directory / 'result.json'
    require(reservation.is_file() and result.is_file(), 'existing cell is incomplete; refusing replay')
    require(read(reservation)['design_freeze_sha256'] == freeze_hash, 'existing cell belongs to another freeze')
    outcome = read(result)
    require(outcome.get('cell') == cell and outcome.get('completed') is True
        and outcome.get('outcome') in {'SERVICE_COMPLETED', 'NATIVE_BOUNDED_FAILURE'},
        'existing cell did not complete; refusing replay')
    return True


def process_rss(pid):
    try:
        return next((int(line.split()[1]) * 1024 for line in
            Path(f'/proc/{pid}/status').read_text().splitlines() if line.startswith('VmRSS:')), 0)
    except FileNotFoundError:
        return 0


def terminate(process):
    if process.poll() is not None:
        return
    # The child is the only process in its new session. A child cannot survive
    # a resource stop and overlap the next cell.
    for sig, timeout in ((signal.SIGINT, 10), (signal.SIGTERM, 10), (signal.SIGKILL, 5)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=timeout)
            return
        except subprocess.TimeoutExpired:
            continue
    raise IntegrityFailure('child process did not terminate')


def execute(cell):
    require(available_memory() >= MIN_AVAILABLE, 'available RAM below 4 GiB before process')
    require(not STOP.exists(), 'matrix has a sticky stop')
    log = MATRIX / f"{cell['ordinal']:03d}-{cell['case_id']}-{cell['arm']}.log"
    resource_path = log.with_suffix('.resources.json')
    MATRIX.mkdir(parents=True, exist_ok=True)
    require(not resource_path.exists(), 'existing process receipt; refusing replay')
    start = time.monotonic()
    peak = 0
    cause = None
    process = None
    try:
        with log.open('x', encoding='utf-8') as stream:
            process = subprocess.Popen([str(ROOT / '.venv/bin/python'), '-B',
                str(Path(__file__).with_name('run_case.py')), '--ordinal', str(cell['ordinal'])],
                cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True,
                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'MALLOC_ARENA_MAX': '1'})
            while process.poll() is None:
                rss = process_rss(process.pid)
                peak = max(peak, rss)
                if shutil.disk_usage(ROOT).free < 20*1024**3:
                    cause = 'DISK_FREE_LIMIT'
                elif rss > MEMORY_LIMIT:
                    cause = 'PROCESS_MEMORY_LIMIT'
                elif available_memory() < MIN_AVAILABLE:
                    cause = 'SYSTEM_AVAILABLE_MEMORY_LIMIT'
                elif time.monotonic() - start > WALL_SECONDS + 60:
                    cause = 'PROCESS_DEADLINE'
                if cause:
                    stop('RESOURCE_FAILURE', cell=cell, cause=cause, pid=process.pid)
                    terminate(process)
                    break
                time.sleep(.5)
    except BaseException as exc:
        cause = 'GUARD_INTERRUPTED' if isinstance(exc, KeyboardInterrupt) else 'GUARD_FAILURE'
        stop(cause, cell=cell, error_type=type(exc).__name__)
        if process is not None:
            terminate(process)
    finally:
        receipt = {'cell': cell, 'exit_code': process.returncode if process else None,
            'peak_rss_bytes': peak, 'seconds': time.monotonic() - start, 'interruption': cause,
            'pid': process.pid if process else None, 'process_reaped': process is not None and process.poll() is not None}
        durable(resource_path, receipt, exclusive=True)
    result_path = cell_directory(cell) / 'result.json'
    result = read(result_path) if result_path.exists() else None
    if receipt['exit_code'] != 0 or not result or result.get('completed') is not True:
        stop('CASE_PROCESS_FAILURE', cell=cell, exit_code=receipt['exit_code'],
             recorded_result=result_path.exists())
    print(json.dumps(receipt, ensure_ascii=False), flush=True)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect-only', '--dry-run', action='store_true')
    parser.add_argument('--max-cases', type=int, help='Run at most this many new cells in frozen order.')
    args = parser.parse_args()
    require(args.max_cases is None or args.max_cases > 0, 'max-cases must be positive')
    frozen, *_ = load_frozen()
    freeze_hash = sha(ART / 'design-freeze.json')
    if args.inspect_only:
        print(json.dumps({'frozen_inputs_verified': True, 'cells': len(frozen['execution_order']),
            'existing_cells': sum(cell_directory(c).exists() for c in frozen['execution_order']),
            'sticky_stop': read(STOP) if STOP.exists() else None,
            'available_memory_bytes': available_memory(), 'live_model_calls': 0,
            'runtime_loaded': False}, ensure_ascii=False))
        return 0
    with process_lock('.matrix-runner.lock'):
        require(not STOP.exists(), 'matrix has a sticky stop')
        outcomes = []
        for cell in frozen['execution_order']:
            if finished(cell, freeze_hash):
                continue
            if args.max_cases is not None and len(outcomes) >= args.max_cases:
                break
            outcomes.append(execute(cell))
            durable(ART / 'matrix-progress.json', {'design_freeze_sha256': freeze_hash,
                'last_ordinal': cell['ordinal'], 'invocation_outcomes': outcomes,
                'stop': read(STOP) if STOP.exists() else None})
            if STOP.exists():
                return 2
        completed = sum((cell_directory(c) / 'result.json').is_file()
            and read(cell_directory(c) / 'result.json').get('completed') is True for c in frozen['execution_order'])
        durable(ART / 'matrix-progress.json', {'design_freeze_sha256': freeze_hash,
            'completed_cells': completed, 'total_cells': 1, 'matrix_complete': completed == 1,
            'invocation_outcomes': outcomes, 'stop': None})
        return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except IntegrityFailure as exc:
        if '--inspect-only' not in sys.argv and '--dry-run' not in sys.argv:
            stop('RUNNER_OR_INTEGRITY_FAILURE', error=str(exc))
        print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        raise SystemExit(2)
