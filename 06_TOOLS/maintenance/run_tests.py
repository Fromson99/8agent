#!/usr/bin/env python3
"""Run pytest files in parallel worker processes and merge the results.

Each worker is an ordinary ``python -m pytest`` process over a batch of whole
files, with its own --basetemp, so tests run exactly as they do serially; only
different files run at the same time.  Batches are balanced with the per-file
times recorded by earlier runs (``90_RUNTIME/PYTEST_CACHE/file-durations.json``)
and a new batch starts only while enough memory is available.

Tests that depend on what ran earlier in the same process can pass or fail
depending on the batch they land in.  For before/after comparisons pass
--compare (or --batches-from) so both runs use the same batches.

Examples (from the workspace root):
  .venv/bin/python 06_TOOLS/maintenance/run_tests.py 05_TESTS/CONTRACTS/test_a.py 05_TESTS/CONTRACTS/test_b.py
  .venv/bin/python 06_TOOLS/maintenance/run_tests.py --files-from list.txt --output 90_RUNTIME/OUT/run1
  .venv/bin/python 06_TOOLS/maintenance/run_tests.py --files-from list.txt --compare 90_RUNTIME/OUT/run0/result.json

The result JSON lists every test outcome; --compare prints tests whose outcome
differs from an earlier result.  Exit status is 0 only when no test failed or
errored and every batch finished.

--code-root DIR runs the tests against an exact code tree (a release's code/ or
a staged candidate) instead of the working tree: each worker is
pytest_code_root.py, which imports the product packages from DIR.  The tree is
hashed before and after, its engine pins are checked first, and any product
module imported from outside DIR fails the batch.  Results of completely
finished files are also stored per file as that tree's baseline
(baseline_results.py), so main_release.py does not have to rerun the current
MAIN when the next candidate is compared with it.
  .venv/bin/python 06_TOOLS/maintenance/run_tests.py --code-root 08_DEPLOYMENT/RELEASES/<id>/code --files-from list.txt
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ElementTree

import baseline_results

ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).resolve().parent / 'pytest_code_root.py'
DURATIONS = ROOT / '90_RUNTIME' / 'PYTEST_CACHE' / 'file-durations.json'
EATMYDATA_LIBRARY = '/usr/lib/x86_64-linux-gnu/libeatmydata.so'
WORKER_MEMORY_MB = 700       # measured ~490 MB per worker over the full suite, plus margin
RESERVE_MEMORY_MB = 2500     # left for the OS, other sessions and growth
DEFAULT_FILE_SECONDS = 8.0   # for files without a recorded time


def available_memory_mb():
    with open('/proc/meminfo') as meminfo:
        for line in meminfo:
            if line.startswith('MemAvailable:'):
                return int(line.split()[1]) // 1024
    return 0


def default_workers():
    by_memory = (available_memory_mb() - RESERVE_MEMORY_MB) // WORKER_MEMORY_MB
    return max(1, min(8, (os.cpu_count() or 2) - 2, by_memory))


def load_durations():
    try:
        return json.loads(DURATIONS.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def make_batches(files, durations, workers, batch_seconds):
    """Longest files first; each batch about batch_seconds so startup cost stays small."""
    timed = sorted(((durations.get(name, DEFAULT_FILE_SECONDS), name) for name in files), reverse=True)
    total = sum(seconds for seconds, _ in timed)
    target = min(batch_seconds, max(total / (workers * 3), 1.0))
    batches, current, current_seconds = [], [], 0.0
    for seconds, name in timed:
        if current and current_seconds + seconds > target:
            batches.append((current_seconds, current))
            current, current_seconds = [], 0.0
        current.append(name)
        current_seconds += seconds
    if current:
        batches.append((current_seconds, current))
    return sorted(batches, key=lambda batch: batch[0], reverse=True)


def engine_preflight(code_root):
    """Engine pin check of a code tree in a clean interpreter: (engines, files, errors)."""
    probe = subprocess.run(
        [sys.executable, '-I', '-c', 'import json,sys\n'
         'sys.dont_write_bytecode=True\n'
         'sys.path[:0]=[sys.argv[1],sys.argv[2]]\n'
         'from genos_codespace_engine_preflight import check\n'
         'engines,count,errors=check(__import__("pathlib").Path(sys.argv[3]))\n'
         'print(json.dumps([engines,count,errors],default=str))',
         str(ROOT / '06_TOOLS' / 'COMMANDS'), str(code_root / '02_BACKEND'), str(code_root)],
        cwd=ROOT, capture_output=True, text=True, timeout=300)
    if probe.returncode:
        return None, None, [probe.stderr.strip()[-2000:] or f'exit {probe.returncode}']
    engines, count, errors = json.loads(probe.stdout.strip().splitlines()[-1])
    return engines, count, errors


def earlier_layout(earlier, files):
    """Batches of an earlier result in their original order, if it ran the same files.

    Same files grouped the same way, so order-dependent tests see the same neighbours.
    """
    if sorted(earlier['files']) != sorted(files):
        return None
    return [(0.0, batch['files']) for batch in sorted(earlier['batches'], key=lambda item: item['batch'])]


def read_junit(path, batch_files):
    """Return [(nodeid, file, outcome, seconds, message)] from one worker's junit file.

    junit stores the node id as a dotted classname; the batch's file list tells
    where the module path ends and a test class begins.
    """
    modules = sorted(((name[:-3].replace('/', '.'), name) for name in batch_files), key=lambda item: -len(item[0]))
    rows = []
    for case in ElementTree.parse(path).getroot().iter('testcase'):
        classname, name = case.get('classname', ''), case.get('name', '')
        file, rest = next(((file, classname[len(module):].lstrip('.')) for module, file in modules
                           if classname == module or classname.startswith(module + '.')), (classname, ''))
        nodeid = '::'.join(part for part in (file, *rest.split('.'), name) if part) if rest else file + '::' + name
        outcome, message = 'passed', None
        for child in case:
            if child.tag in ('failure', 'error'):
                outcome = 'failed' if child.tag == 'failure' else 'error'
                message = (child.get('message') or '').splitlines()[0][:300] if child.get('message') else None
                break
            if child.tag == 'skipped':
                outcome = 'skipped'
        rows.append((nodeid, file, outcome, float(case.get('time') or 0), message))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('files', nargs='*', help='test files relative to the workspace root')
    parser.add_argument('--files-from', type=Path, help='file with one test file per line')
    parser.add_argument('-j', '--workers', type=int, default=0, help='parallel processes (default: from CPU and free memory)')
    parser.add_argument('--batch-seconds', type=float, default=25.0, help='target recorded seconds per batch')
    parser.add_argument('--output', type=Path, help='new directory for junit files, logs and result.json')
    parser.add_argument('--compare', type=Path, help='earlier result.json; print tests whose outcome changed '
                        '(its batch layout is reused when the file list is the same)')
    parser.add_argument('--batches-from', type=Path, help='earlier result.json whose batch layout to reuse')
    parser.add_argument('--batch-timeout', type=float, default=1800.0, help='seconds before a batch is stopped')
    parser.add_argument('--pytest-arg', action='append', default=[], help='extra pytest argument (repeatable)')
    parser.add_argument('--code-root', type=Path, help='run against this exact code tree instead of the working tree')
    parser.add_argument('--no-baseline-save', action='store_true', help='with --code-root: do not store the results '
                        'as this tree\'s per-file baseline')
    args = parser.parse_args()

    files = list(args.files)
    if args.files_from:
        files += [line.strip() for line in args.files_from.read_text().splitlines() if line.strip() and not line.startswith('#')]
    files = list(dict.fromkeys(files))
    missing = [name for name in files if not (ROOT / name.split('::')[0]).exists()]
    if not files or missing:
        parser.error('no test files given' if not files else 'missing: ' + ', '.join(missing))
    if any('::' in name for name in files):
        parser.error('give whole files; node ids would split one file across workers')

    code_root = code_before = None
    preflight = None
    if args.code_root:
        code_root = args.code_root.resolve()
        if not (code_root / '02_BACKEND').is_dir():
            parser.error(f'--code-root has no 02_BACKEND: {code_root}')
        code_before = baseline_results.inventory(code_root)
        if (code_root / '02_BACKEND' / 'ENGINES').is_dir():
            engines, engine_files, errors = engine_preflight(code_root)
            preflight = {'engines': engines, 'files': engine_files, 'errors': errors}
            if errors:
                raise SystemExit(f'engine preflight failed for {code_root}: {errors}')

    workers = args.workers or default_workers()
    output = (args.output or Path(tempfile.mkdtemp(prefix='run-tests-', dir=ROOT / '90_RUNTIME' / 'OUT'))).resolve()
    output.mkdir(parents=True, exist_ok=bool(args.output is None))
    durations = load_durations()
    batches = make_batches(files, durations, workers, args.batch_seconds)
    layout_source = args.batches_from or args.compare
    if layout_source:
        earlier_batches = earlier_layout(json.loads(layout_source.read_text()), files)
        if earlier_batches is not None:
            batches = earlier_batches
        elif args.batches_from:
            parser.error('--batches-from has a different file list')

    env = dict(os.environ)
    if os.environ.get('LAWRAG_TEST_KEEP_FSYNC') != '1' and os.path.exists(EATMYDATA_LIBRARY) \
            and 'libeatmydata' not in env.get('LD_PRELOAD', ''):
        env['LD_PRELOAD'] = (EATMYDATA_LIBRARY + ' ' + env.get('LD_PRELOAD', '')).strip()
    print(f'{len(files)} files in {len(batches)} batches, {workers} workers, output {output}'
          + (f', code root {code_root}' if code_root else ''), flush=True)

    started = time.monotonic()
    pending = list(enumerate(batches))
    running = {}
    finished = []
    while pending or running:
        while pending and len(running) < workers and (not running or available_memory_mb() > RESERVE_MEMORY_MB):
            index, (_, batch_files) = pending.pop(0)
            log = (output / f'batch-{index:03d}.log').open('w')
            # A file that fails to import is reported as an error; the other files in the batch still run.
            pytest_args = ['-q', '-p', 'no:cacheprovider', '--tb=short', '-rN', '--continue-on-collection-errors',
                           '--basetemp', str(output / f'tmp-{index:03d}'), '--junitxml', str(output / f'batch-{index:03d}.xml'),
                           *args.pytest_arg, *batch_files]
            if code_root:
                command = [sys.executable, str(WORKER), '--code-root', str(code_root),
                           '--report', str(output / f'batch-{index:03d}.isolation.json'), '--', *pytest_args]
            else:
                command = [sys.executable, '-m', 'pytest', *pytest_args]
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            running[index] = (process, log, time.monotonic(), batch_files)
        time.sleep(0.2)
        for index, (process, log, begun, batch_files) in list(running.items()):
            timed_out = time.monotonic() - begun > args.batch_timeout
            if process.poll() is None and not timed_out:
                continue
            if process.poll() is None:
                process.kill()
                process.wait()
            log.close()
            finished.append({'batch': index, 'files': batch_files, 'exit_code': process.returncode,
                             'seconds': round(time.monotonic() - begun, 2), 'timed_out': timed_out})
            del running[index]
            done = len(finished)
            print(f'  batch {index:3d} exit={process.returncode} {time.monotonic() - begun:6.1f}s '
                  f'({done}/{len(batches)}, {time.monotonic() - started:6.1f}s elapsed)', flush=True)

    rows, incomplete = [], []
    for batch in sorted(finished, key=lambda item: item['batch']):
        junit = output / f"batch-{batch['batch']:03d}.xml"
        if batch['timed_out'] or not junit.exists() or batch['exit_code'] not in (0, 1, 5):  # 5: nothing collected
            incomplete.append(batch)
        if junit.exists():
            rows += read_junit(junit, batch['files'])
    file_seconds = {}
    for _, file, _, seconds, _ in rows:
        file_seconds[file] = file_seconds.get(file, 0.0) + seconds
    unfinished = {name for batch in incomplete for name in batch['files']}
    measured = {name: round(seconds, 2) for name, seconds in file_seconds.items() if name not in unfinished}
    if measured:
        DURATIONS.parent.mkdir(parents=True, exist_ok=True)
        DURATIONS.write_text(json.dumps({**durations, **measured}, ensure_ascii=False, indent=0, sort_keys=True) + '\n')

    counts = {}
    for _, _, outcome, _, _ in rows:
        counts[outcome] = counts.get(outcome, 0) + 1
    wall = round(time.monotonic() - started, 2)
    result = {'files': files, 'workers': workers, 'wall_seconds': wall, 'counts': counts,
              'fsync': 'eatmydata' if 'libeatmydata' in env.get('LD_PRELOAD', '') else 'real',
              'incomplete_batches': incomplete, 'batches': sorted(finished, key=lambda item: item['batch']),
              'tests': [{'nodeid': nodeid, 'outcome': outcome, 'seconds': seconds, 'message': message}
                        for nodeid, _, outcome, seconds, message in sorted(rows)]}
    code_changed = []
    if code_root:
        code_after = baseline_results.inventory(code_root)
        code_changed = sorted(name for name in code_before.keys() | code_after.keys()
                              if code_before.get(name) != code_after.get(name))
        violations, violation_files, fallbacks, same_bytes = {}, [], set(), set()
        for batch in finished:
            report_path = output / f"batch-{batch['batch']:03d}.isolation.json"
            report = json.loads(report_path.read_text()) if report_path.exists() else None
            if report is None:
                continue
            fallbacks.update(report['workspace_fallback_modules'])
            same_bytes.update(report.get('same_bytes_outside_code_root', []))
            if report['loaded_outside_code_root']:
                violations[batch['batch']] = report['loaded_outside_code_root']
                violation_files += batch['files']
        result.update(code_root=str(code_root), code_inventory_sha256=baseline_results.inventory_sha(code_before),
                      code_files=len(code_before), code_unchanged=not code_changed, code_changed_files=code_changed,
                      engine_preflight=preflight, isolation_violations=violations,
                      isolation_violation_files=sorted(violation_files), workspace_fallback_modules=sorted(fallbacks),
                      same_bytes_outside_code_root=sorted(same_bytes))
        if not args.no_baseline_save and not code_changed:
            result['baseline_files_saved'] = baseline_results.save_result(result)
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')

    print(f"{wall}s wall, " + ', '.join(f'{count} {outcome}' for outcome, count in sorted(counts.items())))
    if code_root:
        print(f"code root {code_root}: {result['code_files']} files, inventory {result['code_inventory_sha256'][:16]}, "
              f"unchanged={result['code_unchanged']}, isolation violations={len(result['isolation_violations'])}, "
              f"baseline files saved={result.get('baseline_files_saved', 0)}")
        for name in code_changed:
            print(f'CODE CHANGED DURING RUN {name}')
        for batch, modules in result['isolation_violations'].items():
            print(f'ISOLATION batch {batch}: ' + ', '.join(f'{name}={path}' for name, path in list(modules.items())[:5]))
    for batch in incomplete:
        print(f"INCOMPLETE batch {batch['batch']} exit={batch['exit_code']} timed_out={batch['timed_out']}: "
              f"see {output / ('batch-%03d.log' % batch['batch'])}")
    for test in result['tests']:
        if test['outcome'] in ('failed', 'error'):
            print(f"{test['outcome'].upper()} {test['nodeid']}" + (f" - {test['message']}" if test['message'] else ''))
    if args.compare:
        before = {test['nodeid']: test['outcome'] for test in json.loads(args.compare.read_text())['tests']}
        after = {test['nodeid']: test['outcome'] for test in result['tests']}
        changed = sorted(nodeid for nodeid in before.keys() | after.keys() if before.get(nodeid) != after.get(nodeid))
        print(f'{len(changed)} outcome changes against {args.compare}')
        for nodeid in changed:
            print(f'  {before.get(nodeid, "absent")} -> {after.get(nodeid, "absent")}  {nodeid}')
    print(f'result: {output / "result.json"}')
    failed = counts.get('failed', 0) + counts.get('error', 0)
    raise SystemExit(0 if not failed and not incomplete and not code_changed else 1)


if __name__ == '__main__':
    main()
