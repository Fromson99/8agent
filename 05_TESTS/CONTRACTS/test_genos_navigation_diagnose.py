"""Diagnostic reads must never mutate or signal a running build."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import os
import zipfile
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'06_TOOLS/OFFLINE'))
import genos_navigation_diagnose as diag

@pytest.fixture
def database(tmp_path):
    path=tmp_path/'navigation.sqlite'
    schema,_=diag.sql_statements(ROOT/'02_BACKEND/semantic_runtime/term_links.py')
    with sqlite3.connect(path) as db:
        db.executescript(schema)
        db.execute('CREATE TABLE occurrence(term_id TEXT,source_id TEXT,PRIMARY KEY(term_id,source_id))')
        db.execute("INSERT INTO link_occurrence(id,key,status) VALUES('i','sensitive-label','ACCEPTED')")
        db.execute("INSERT INTO occurrence_evidence VALUES('i','c','t','s','ACCEPTED','reason')")
    return path

def test_plans_from_installed_code_only_memory():
    rows=diag.offline_plans(ROOT)['queries']
    nine=next(r for r in rows if r['static_sql_sequence']==9)
    assert 'CORRELATED SCALAR SUBQUERY 1' in nine['plan']
    assert any('sqlite_autoindex_occurrence_evidence_1' in s for s in nine['plan'])

def test_metadata_plan_preserves_database_and_does_not_collect_values(database):
    before=hashlib.sha256(database.read_bytes()).hexdigest()
    report=diag.inspect_bounded(database)
    assert report['status']=='READABLE'
    assert report['indexes']['occurrence_evidence']
    assert 'sensitive-label' not in json.dumps(report)
    assert hashlib.sha256(database.read_bytes()).hexdigest()==before
    assert not Path(str(database)+'-journal').exists()

def test_locked_database_fast_skip(database):
    before=hashlib.sha256(database.read_bytes()).hexdigest()
    db=sqlite3.connect(database);db.execute('BEGIN EXCLUSIVE')
    try:
        started=time.monotonic();report=diag.inspect_bounded(database)
        assert report['status']=='UNAVAILABLE' and 'locked' in report['error']
        assert time.monotonic()-started<3
    finally:db.rollback();db.close()
    assert hashlib.sha256(database.read_bytes()).hexdigest()==before

def test_no_wal_shared_metadata_creation(database):
    wal=Path(str(database)+'-wal');wal.write_bytes(b'active')
    assert diag.inspect_database(database)['status']=='SKIPPED_ACTIVE_WAL'
    assert not Path(str(database)+'-shm').exists()

def test_live_cli_exact_run_no_signal_and_no_raw_log_leak(tmp_path):
    dev=tmp_path/'DEV';tool=dev/'06_TOOLS/OFFLINE/genos_reindex_runner.py'
    tool.parent.mkdir(parents=True);tool.write_text('import time;time.sleep(30)\n')
    core=dev/'02_BACKEND/semantic_runtime/term_links.py';core.parent.mkdir(parents=True)
    core.write_bytes((ROOT/'02_BACKEND/semantic_runtime/term_links.py').read_bytes())
    data=dev/'01_DATA';logs=data/'LOGS/selected/reindex-only-r8/test';logs.mkdir(parents=True)
    (logs/'run.log').write_text('SECRET MUST NOT COLLECT\nNAVIGATION glossary-evidence.sql-8 elapsed=130.995s thread_cpu=30.114s\n')
    processes=[subprocess.Popen([sys.executable,str(tool),'build','--dev',str(dev),'--run-id',run]) for run in ('selected','other')]
    try:
        time.sleep(.05)
        found=diag.discover(dev,'selected');assert [r['pid'] for r in found]==[processes[0].pid]
        out=tmp_path/'report'
        result=subprocess.run([sys.executable,str(Path(diag.__file__)),'--dev',str(dev),'--data-root',str(data),
                               '--run-id','selected','--output',str(out),'--samples','2','--interval','1'],capture_output=True,text=True,timeout=10)
        assert result.returncode==0,result.stderr
        assert 'SECRET' not in result.stdout
        report=json.loads((out/'report.json').read_text())
        assert report['likely_next_sql']==9 and report['read_only']
        assert 'SECRET' not in json.dumps(report)
        assert all(p.poll() is None for p in processes)
    finally:
        for p in processes:p.terminate();p.wait(timeout=3)

def test_packaged_execution_and_inventory(tmp_path):
    import package_genos_navigation_diagnose as pack
    archive=pack.OUT/(pack.STEM+'.zip')
    with zipfile.ZipFile(archive) as z:
        manifest=json.loads(z.read('CODE_MANIFEST.json'))
        assert set(z.namelist())==set(manifest['files'])|{'CODE_MANIFEST.json'}
        assert all(hashlib.sha256(z.read(n)).hexdigest()==s for n,s in manifest['files'].items())
        assert all(Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
    dev=tmp_path/'DEV';core=dev/'02_BACKEND/semantic_runtime/term_links.py';core.parent.mkdir(parents=True)
    core.write_bytes((ROOT/'02_BACKEND/semantic_runtime/term_links.py').read_bytes())
    before=core.read_bytes()
    env={**os.environ,'GENOS_DEV':str(dev),'GENOS_DATA_ROOT':str(dev/'01_DATA'),
         'GENOS_DIAG_RUN':'selected','GENOS_DIAG_SAMPLES':'2','GENOS_DIAG_INTERVAL':'1'}
    result=subprocess.run(['bash',str(pack.OUT/(pack.STEM+'.txt'))],env=env,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'ARCHIVE VERIFIED' in result.stdout and 'DIAGNOSTIC DONE' in result.stdout
    report=next((dev/'01_DATA/LOGS/selected/bottleneck-check').glob('*/report.json'))
    assert json.loads(report.read_text())['active_build_found'] is False
    assert core.read_bytes()==before
