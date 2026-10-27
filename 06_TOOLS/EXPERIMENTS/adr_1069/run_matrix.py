"""Run the single frozen offline B0 service reconstruction under resource guards."""
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
from run_case import (STOP, MATRIX, WALL_SECONDS, IntegrityFailure,
    available_memory, cell_directory, checked, digest, durable, load_frozen,
    process_lock, require, resource_baseline,
    resource_reading, resource_cause, stop)

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


def in_flight(cell, *, replay_arm=None):
    return False  # This runner has no external transport; recorded responses are local.


def execute(cell, baseline_swap, *, replay_arm=None):
    require(replay_arm == 'B0' and cell == {'ordinal':1,'case_id':'fsc-hard-005','arm':'A0'},
            'only the offline recorded A0 flow is authorized')
    initial = resource_reading(baseline_swap=baseline_swap)
    cause = resource_cause(initial)
    if cause:
        stop('RESOURCE_FAILURE', cell=cell, cause=cause, phase='BEFORE_WORKER', resources=initial)
        raise IntegrityFailure(cause)
    require(not STOP.exists(), 'matrix has a sticky stop')
    parent = ART/'replay'/replay_arm if replay_arm else MATRIX
    log = parent / f"{cell['ordinal']:03d}-{cell['case_id']}-{cell['arm']}.log"
    resource_path = log.with_suffix('.resources.json')
    parent.mkdir(parents=True, exist_ok=True)
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
            command = [str(ROOT / '.venv/bin/python'), '-B',
                str(Path(__file__).with_name('run_case.py')), '--ordinal', str(cell['ordinal'])]
            if replay_arm:command.extend(['--replay-arm', replay_arm])
            process = subprocess.Popen(command,
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
                    outstanding = in_flight(cell,replay_arm=replay_arm)
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
            outstanding_at_termination = in_flight(cell,replay_arm=replay_arm)
            terminate(process)
    finally:
        receipt = {'cell': cell, 'exit_code': process.returncode if process else None,
            'peak_rss_bytes': peak, 'seconds': time.monotonic() - start, 'interruption': cause,
            'pid': process.pid if process else None, 'process_reaped': process is not None and process.poll() is not None,
            'initial_resources': initial, 'last_resources': last,
            'forced_termination': forced, 'physical_call_outstanding_at_termination': outstanding_at_termination,
            'outstanding_call_acceptance': 'UNKNOWN' if outstanding_at_termination else 'NOT_APPLICABLE'}
        durable(resource_path, receipt, exclusive=True)
    result_path = parent/cell_directory(cell).name/'result.json'
    result = read(result_path) if result_path.exists() else None
    if receipt['exit_code'] != 0 or not result or result.get('completed') is not True:
        stop('CASE_PROCESS_FAILURE', cell=cell, exit_code=receipt['exit_code'],
             recorded_result=result_path.exists())
    print(json.dumps(receipt, ensure_ascii=False), flush=True)
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay-arm',choices=('B0',),required=True)
    parser.add_argument('--ordinal',type=int,choices=(1,),default=1)
    parser.add_argument('--inspect-only','--dry-run',action='store_true')
    args=parser.parse_args()
    frozen,*_=load_frozen(replay_arm=args.replay_arm)
    cell=frozen['execution_order'][0]
    if args.inspect_only:
        print(json.dumps({'frozen_inputs_verified':True,'arm':args.replay_arm,'cell':cell,
            'sticky_stop':read(STOP) if STOP.exists() else None,'offline_only':True,
            'live_model_calls':0,'runtime_loaded':False},ensure_ascii=False))
        return 0
    with process_lock('.matrix-runner.lock'):
        baseline_swap=resource_baseline(frozen)
        receipt=execute(cell,baseline_swap,replay_arm=args.replay_arm)
        return 0 if receipt['exit_code']==0 and not STOP.exists() else 2


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except IntegrityFailure as exc:
        if '--inspect-only' not in sys.argv and '--dry-run' not in sys.argv:
            stop('RUNNER_OR_INTEGRITY_FAILURE',error=str(exc))
        print(type(exc).__name__+': '+str(exc),file=sys.stderr)
        raise SystemExit(2)
