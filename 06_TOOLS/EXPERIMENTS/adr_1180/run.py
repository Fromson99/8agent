"""Prospectively frozen, bounded PeCab comparison. Never selects MAIN code."""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import os
import resource
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-1180-pipeline02-bounded-index-speed'
ART = ADR / 'artifacts'
sys.path.insert(0, str(ROOT / '06_TOOLS/maintenance'))
from experiment_json import write_summary, write_raw_json


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def token_row(item):
    # Spawned workers inherit the explicit, verified sealed runtime on sys.path.
    from semantic_runtime import fulltext
    key, text = item
    value = fulltext._search_forms(text)
    return key, value, os.getpid(), resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def dataset():
    with gzip.open(ART / 'dataset.json.gz', 'rt') as f:
        return json.load(f)


def prepare():
    plan = json.loads((ART / 'design.json').read_text())
    archive = ROOT / plan['baseline_archive']
    assert sha(archive) == plan['baseline_archive_sha256']
    base = ART / 'runtimes/baseline'
    base.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            rel = Path(name.split('/', 1)[1])
            assert not rel.is_absolute() and '..' not in rel.parts
            target = base / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(name))
    pins = json.loads((base / 'CODE_PINS.json').read_text())['files']
    assert all(sha(base / name) == expected for name, expected in pins.items())
    for arm in plan['order'][1:]:
        candidate = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1180' / arm / 'candidate.json'
        meta = json.loads(candidate.read_text())
        assert meta['arm_id'] == arm and meta['production_loadable'] is False
        runtime = ART / 'runtimes' / arm
        shutil.copytree(base, runtime)
        for row in meta['revisions'][-1]['files']:
            source = ROOT / row['frozen_path']
            assert sha(source) == row['snapshot_sha256']
            rel = str(source).split('/snapshot/', 1)[1]
            shutil.copyfile(source, runtime / rel)
        verified = {name: sha(runtime / name) for name in pins}
        write_summary(runtime / 'RESEARCH_PINS.json', verified)


def child(arm):
    plan = json.loads((ART / 'design.json').read_text())
    runtime = ART / 'runtimes' / arm
    pins = (json.loads((runtime / 'CODE_PINS.json').read_text())['files'] if arm == 'baseline'
            else json.loads((runtime / 'RESEARCH_PINS.json').read_text()))
    assert all(sha(runtime / name) == expected for name, expected in pins.items())
    sys.path.insert(0, str(runtime / '02_BACKEND'))
    os.environ['LAWRAG_WORKSPACE_ROOT'] = str(runtime)
    # No sockets are permitted in the measured parent or spawned workers.
    import socket
    socket.socket.connect = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('NETWORK_FORBIDDEN'))
    selected = dataset()
    source = ROOT / selected['source']
    assert sha(source) == selected['sha256']
    db = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
    results, worker_rss = [], {}
    workers = plan['arms'][arm]['workers']
    t0 = time.monotonic()
    pool = ProcessPoolExecutor(max_workers=workers, mp_context=get_context('spawn')) if workers > 1 else None
    try:
        keys = selected['keys']
        for start in range(0, len(keys), 128):
            part = []
            for key in keys[start:start+128]:
                value = db.execute('SELECT json FROM unit WHERE key=?', (key,)).fetchone()
                assert value is not None
                part.append((key, json.loads(value[0])['text']))
            mapped = pool.map(token_row, part, chunksize=16) if pool else map(token_row, part)
            for key, text, pid, rss in mapped:
                results.append([key, text])
                worker_rss[str(pid)] = max(worker_rss.get(str(pid), 0), rss)
            if start % 2048 == 0:
                print(arm, len(results), round(time.monotonic()-t0, 3), flush=True)
    finally:
        if pool:
            pool.shutdown(wait=True, cancel_futures=True)
        db.close()
    elapsed = time.monotonic() - t0
    from semantic_runtime import fulltext
    output = ART / 'run-001' / arm
    output.mkdir(parents=True, exist_ok=False)
    raw = write_raw_json(output / 'tokens.json.gz', results)
    result = {'arm': arm, 'seconds': elapsed, 'units': len(results), 'workers': workers,
              'worker_peak_rss_kib': worker_rss, 'output': raw,
              'cache_stats_parent_only': getattr(fulltext, '_CHUNK_FORM_STATS', None),
              'cache_bytes_parent_only': getattr(fulltext, '_CHUNK_FORM_BYTES', None),
              'source_unchanged': sha(source) == selected['sha256']}
    assert result['source_unchanged']
    write_summary(output / 'result.json', result)


def rss_group(group):
    pages = 0
    for p in Path('/proc').iterdir():
        if p.name.isdigit():
            try:
                fields = (p / 'stat').read_text().rsplit(')', 1)[1].split()
                if int(fields[2]) == group:
                    pages += int(fields[21])
            except (OSError, ValueError, IndexError):
                pass
    return pages * os.sysconf('SC_PAGE_SIZE')


def run():
    plan = json.loads((ART / 'design.json').read_text())
    out = ART / 'run-001'
    out.mkdir(exist_ok=False)
    runs = []
    for arm in plan['order']:
        with (out / (arm + '.log')).open('x') as log:
            started = time.monotonic()
            env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1'}
            child_proc = subprocess.Popen([sys.executable, '-B', __file__, 'child', '--arm', arm],
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True, env=env)
            peak = 0
            while child_proc.poll() is None:
                peak = max(peak, rss_group(child_proc.pid))
                if time.monotonic()-started > 300 or peak > 8*1024**3:
                    os.killpg(child_proc.pid, signal.SIGTERM)
                    break
                time.sleep(0.2)
            code = child_proc.wait()
        row = {'arm': arm, 'exit_code': code, 'total_process_seconds': time.monotonic()-started,
               'peak_process_group_bytes': peak}
        p = out / arm / 'result.json'
        if p.exists():
            row['measurement'] = json.loads(p.read_text())
        runs.append(row)
        print('FINISHED', arm, row['total_process_seconds'], code, flush=True)
        if code:
            break
    baseline = None
    for row in runs:
        p = out / row['arm'] / 'tokens.json.gz'
        if not p.exists():
            continue
        with gzip.open(p, 'rt') as f:
            tokens = json.load(f)
        if baseline is None:
            baseline = tokens
        row['mismatches'] = sum(a != b for a, b in zip(baseline, tokens)) + abs(len(tokens)-len(baseline))
    write_summary(out / 'result.json', {'runs': runs, 'full_pipeline_measured': False,
        'onsite_measured': False, 'model_calls': 0, 'local_logical_cpus': os.cpu_count()})


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['prepare', 'run', 'child'])
    p.add_argument('--arm')
    a = p.parse_args()
    {'prepare': prepare, 'run': run, 'child': lambda: child(a.arm)}[a.action]()
