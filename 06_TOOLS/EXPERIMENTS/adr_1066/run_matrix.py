"""Guard the frozen 3 x 3 MVP matrix, one fresh case process at a time."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from common import ROOT, ART, read, sha
from run_case import (STOP, MATRIX, GATE, WALL_SECONDS, IntegrityFailure,
    available_memory, cell_directory, checked, digest, durable, load_frozen,
    process_lock, require, require_continuation_gate, resource_baseline,
    resource_reading, resource_cause, stop)

METRIC_FILES = ('metrics.json', 'evidence-audit.json', 'judge-source-packets.json',
                'ontology-audit.json', 'retrieval-ledger-case.json')


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


def in_flight(cell):
    path = cell_directory(cell) / 'call-state.json'
    return path.is_file() and read(path).get('last_call', {}).get('status') == 'STARTED'


def execute(cell, baseline_swap):
    initial = resource_reading(baseline_swap=baseline_swap)
    cause = resource_cause(initial)
    if cause:
        stop('RESOURCE_FAILURE', cell=cell, cause=cause, phase='BEFORE_WORKER', resources=initial)
        raise IntegrityFailure(cause)
    require(not STOP.exists(), 'matrix has a sticky stop')
    log = MATRIX / f"{cell['ordinal']:03d}-{cell['case_id']}-{cell['arm']}.log"
    resource_path = log.with_suffix('.resources.json')
    MATRIX.mkdir(parents=True, exist_ok=True)
    require(not resource_path.exists(), 'existing process receipt; refusing replay')
    start = time.monotonic()
    peak = 0
    cause = None
    pressure_since = None
    forced = False
    outstanding_at_termination = False
    last = initial
    process = None
    try:
        with log.open('x', encoding='utf-8') as stream:
            process = subprocess.Popen([str(ROOT / '.venv/bin/python'), '-B',
                str(Path(__file__).with_name('run_case.py')), '--ordinal', str(cell['ordinal'])],
                cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True,
                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'MALLOC_ARENA_MAX': '1'})
            while process.poll() is None:
                last = resource_reading(baseline_swap=baseline_swap, pid=process.pid)
                peak = max(peak, last['rss_bytes'])
                deadline = time.monotonic() - start > WALL_SECONDS + 60
                cause = cause or resource_cause(last) or ('PROCESS_DEADLINE' if deadline else None)
                if cause:
                    stop('RESOURCE_FAILURE', cell=cell, cause=cause, pid=process.pid,
                         phase='WORKER_MONITOR', resources=last)
                    # STOP prevents new native model/tool reservations. Permit
                    # an accepted call to finish and preserve its receipt before
                    # shutting down; the unchanged deadline remains a backstop.
                    outstanding = in_flight(cell)
                    if outstanding:
                        pressure_since = None
                    elif pressure_since is None:
                        pressure_since = time.monotonic()
                    if deadline or (pressure_since is not None and time.monotonic()-pressure_since >= 15):
                        forced = True
                        outstanding_at_termination = outstanding
                        terminate(process)
                        break
                time.sleep(.5)
    except BaseException as exc:
        cause = 'GUARD_INTERRUPTED' if isinstance(exc, KeyboardInterrupt) else 'GUARD_FAILURE'
        stop(cause, cell=cell, error_type=type(exc).__name__)
        if process is not None:
            forced = True
            outstanding_at_termination = in_flight(cell)
            terminate(process)
    finally:
        receipt = {'cell': cell, 'exit_code': process.returncode if process else None,
            'peak_rss_bytes': peak, 'seconds': time.monotonic() - start, 'interruption': cause,
            'pid': process.pid if process else None, 'process_reaped': process is not None and process.poll() is not None,
            'initial_resources': initial, 'last_resources': last,
            'forced_termination': forced, 'physical_call_outstanding_at_termination': outstanding_at_termination,
            'outstanding_call_acceptance': 'UNKNOWN' if outstanding_at_termination else 'NOT_APPLICABLE'}
        durable(resource_path, receipt, exclusive=True)
    result_path = cell_directory(cell) / 'result.json'
    result = read(result_path) if result_path.exists() else None
    if receipt['exit_code'] != 0 or not result or result.get('completed') is not True:
        stop('CASE_PROCESS_FAILURE', cell=cell, exit_code=receipt['exit_code'],
             recorded_result=result_path.exists())
    print(json.dumps(receipt, ensure_ascii=False), flush=True)
    return receipt


def collect_cell_metrics(frozen, cell):
    """One read-only collector after the product worker is reaped; no replay."""
    directory = cell_directory(cell)
    failure = directory / 'metric-collection-failure.json'
    if not directory.is_dir():
        return False
    try:
        require(not failure.exists(), 'previous metric collection failed; no automatic rerun')
        freeze_hash = sha(ART / 'design-freeze.json')
        receipt_path = ART / 'evaluation-case-receipts.json'
        receipts = read(receipt_path) if receipt_path.exists() else {
            'design_freeze_sha256': freeze_hash, 'metrics': {}, 'judge': {}}
        require(receipts.get('design_freeze_sha256') == freeze_hash, 'metric receipts use another freeze')
        expected = receipts['metrics'].get(str(cell['ordinal']))
        outputs = [directory / name for name in METRIC_FILES]
        if expected is not None:
            require(set(expected) == {str(p.relative_to(ROOT)) for p in outputs}, 'metric receipt file set changed')
            for relative, value in expected.items():
                checked(ROOT / relative, value)
            execution_receipt = receipts.get('execution_audit', {}).get(str(cell['ordinal']))
            require(execution_receipt is not None, 'execution audit lacks a completion receipt')
            require(set(execution_receipt) == {str((directory/'execution-audit.json').relative_to(ROOT))},
                    'execution audit receipt file set changed')
            for relative, value in execution_receipt.items():
                checked(ROOT / relative, value)
            return True
        require(not any(p.exists() for p in [*outputs, directory/'execution-audit.json']),
                'partial metric output lacks completion receipt; inspect without replay')
        script = Path(__file__).with_name('collect_metrics.py')
        checked(script, frozen['evaluation_scripts'][str(script.relative_to(ROOT))])
        result = read(directory / 'result.json')
        arguments = ['--case', cell['case_id'], '--arm', cell['arm'], '--out', str(directory)]
        if result.get('completed') is not True:
            arguments.append('--diagnostic-incomplete')
        with process_lock('.matrix-case.lock'):
            with (directory/'metrics.log').open('x', encoding='utf-8') as stream:
                process = subprocess.run([str(ROOT/'.venv/bin/python'), '-B', str(script), *arguments],
                    cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                    env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'MALLOC_ARENA_MAX': '1'})
        require(process.returncode == 0, 'read-only metric collection failed')
        require(all(p.is_file() for p in [*outputs, directory/'execution-audit.json']), 'metric outputs are incomplete')
        receipts['metrics'][str(cell['ordinal'])] = {str(p.relative_to(ROOT)): sha(p) for p in outputs}
        receipts.setdefault('execution_audit', {})[str(cell['ordinal'])] = {
            str((directory/'execution-audit.json').relative_to(ROOT)): sha(directory/'execution-audit.json')}
        durable(receipt_path, receipts)
        return True
    except (IntegrityFailure, OSError, KeyError, ValueError) as exc:
        if not failure.exists():
            durable(failure, {'cell':cell,'design_freeze_sha256':sha(ART/'design-freeze.json'),
                'error_type':type(exc).__name__,'error':str(exc),'product_replayed':False}, exclusive=True)
        stop('METRIC_COLLECTION_FAILURE', cell=cell, error_type=type(exc).__name__)
        return False


def persist_gate(frozen):
    """Persist the first decision once, including a concrete stopped-cell audit."""
    if GATE.exists():
        value = read(GATE)
        require(value.get('report_sha256') == digest({k:v for k,v in value.items() if k != 'report_sha256'}),
                'existing gate receipt changed')
        require(value.get('design_freeze_sha256') == sha(ART/'design-freeze.json'), 'existing gate uses another freeze')
        if value.get('passed') is True:
            require_continuation_gate(frozen)
        return value
    script = Path(__file__).with_name('gate.py')
    checked(script, frozen['runner_hashes'][str(script.relative_to(ROOT))])
    from gate import check
    with process_lock('.matrix-case.lock'):
        value = check(frozen)
    value.update(design_freeze_sha256=sha(ART/'design-freeze.json'), gate_script_sha256=sha(script),
                 checked_at=time.time())
    if STOP.exists():
        value['passed'] = False
        value.setdefault('reasons', []).append({'code':'MATRIX_STOP_PRESENT', 'stop_sha256':sha(STOP)})
    value['report_sha256'] = digest(value)
    durable(GATE, value, exclusive=True)
    return value


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
        baseline_swap = resource_baseline(frozen)
        outcomes = []
        cell = None
        try:
            if STOP.exists():
                # A previous process may have failed after recording its result.
                # Preserve diagnostic evidence without resuming product work.
                for previous in frozen['execution_order']:
                    if (cell_directory(previous)/'result.json').is_file():
                        collect_cell_metrics(frozen, previous)
                persist_gate(frozen)
                return 2
            for cell in frozen['execution_order']:
                if cell['ordinal'] >= 10:
                    require_continuation_gate(frozen)
                if not finished(cell, freeze_hash):
                    if args.max_cases is not None and len(outcomes) >= args.max_cases:
                        break
                    outcomes.append(execute(cell, baseline_swap))
                # The worker has exited before the collector starts. Completed
                # receipts are hash-checked on resume instead of regenerated.
                collect_cell_metrics(frozen, cell)
                durable(ART / 'matrix-progress.json', {'design_freeze_sha256': freeze_hash,
                    'last_ordinal': cell['ordinal'], 'invocation_outcomes': outcomes,
                    'stop': read(STOP) if STOP.exists() else None})
                if STOP.exists():
                    persist_gate(frozen)
                    return 2
                if cell['ordinal'] == 9:
                    gate = persist_gate(frozen)
                    if gate.get('passed') is not True:
                        stop('FIRST_NINE_GATE_FAILED', gate_sha256=sha(GATE),
                             design_freeze_sha256=freeze_hash)
                        return 2
        except (IntegrityFailure, OSError, KeyError, ValueError) as exc:
            stop('RUNNER_OR_INTEGRITY_FAILURE', cell=cell, error_type=type(exc).__name__, error=str(exc))
            if cell and (cell_directory(cell)/'result.json').is_file():
                collect_cell_metrics(frozen, cell)
            persist_gate(frozen)
            raise
        completed = sum((cell_directory(c) / 'result.json').is_file()
            and read(cell_directory(c) / 'result.json').get('completed') is True for c in frozen['execution_order'])
        durable(ART / 'matrix-progress.json', {'design_freeze_sha256': freeze_hash,
            'completed_cells': completed, 'total_cells': 9, 'matrix_complete': completed == 9,
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
