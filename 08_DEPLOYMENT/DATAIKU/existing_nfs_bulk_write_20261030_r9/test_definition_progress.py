import contextlib
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
from unittest.mock import patch
import zipfile

import pytest

HERE=Path(__file__).resolve().parent
CODE=HERE/'candidate'
sys.path[:0]=[str(CODE),str(CODE/'client'),str(CODE/'client/02_BACKEND')]
from lawrag.pipeline import oracle_query_navigation_publish as nav, oracle_transfer_progress as progress
from projection_preflight import preflight


def definition_files(folder):
    source=folder/'store.sqlite';db=sqlite3.connect(source)
    db.execute('CREATE TABLE source_unit(document_id TEXT,unit_id INTEGER,parent_id INTEGER)')
    db.commit();db.close()
    path=folder/'navigation.sqlite';db=sqlite3.connect(path)
    db.execute('CREATE TABLE source(document_id TEXT,id TEXT,json TEXT)')
    db.execute('CREATE TABLE term(id TEXT,json TEXT)')
    db.execute('CREATE TABLE definition(document_id TEXT,id TEXT,json TEXT)')
    value={'source_id':'source-1','key':'Ａ B\t가','scope_status':'EXPLICIT'}
    db.execute('INSERT INTO definition VALUES(?,?,?)',('doc-1','def-1',json.dumps(value)))
    db.commit();db.close()
    return path, source


def test_nonempty_definition_executes_formerly_missing_lazy_import(tmp_path):
    path,source=definition_files(tmp_path)
    rows=list(nav.navigation(path,source))
    assert len(rows)==1 and rows[0]['kind']=='native.definition_summary'
    assert rows[0]['value']['normalized']=='ab가'
    assert rows[0]['document_id']=='doc-1' and rows[0]['owner_id']=='source-1'
    assert rows[0]['value']['scope_status']=='EXPLICIT'


def test_isolated_sealed_r7_reproduces_field_error_and_r8_fixes_it(tmp_path):
    path,source=definition_files(tmp_path)
    base=HERE.parent/'existing_nfs_projection_20261030_r7/DATAIKU_EXISTING_NFS_CLIENT_20261030_R7.zip'
    root=tmp_path/'r7'
    with zipfile.ZipFile(base) as z:z.extractall(root)
    def run(root):
        text=('import sys;from pathlib import Path;'
              f'r=Path({str(root)!r});sys.path[:0]=[str(r),str(r/"client"),str(r/"client/02_BACKEND")];'
              'from lawrag.pipeline.oracle_query_navigation_publish import navigation;'
              f'print(len(list(navigation(Path({str(path)!r}),Path({str(source)!r})))))')
        return subprocess.run([sys.executable,'-I','-c',text],cwd=tmp_path,capture_output=True,text=True,timeout=20)
    old=run(root);assert old.returncode!=0 and "No module named 'semantic_runtime.term_links'" in old.stderr
    new=run(CODE);assert new.returncode==0 and new.stdout.strip()=='1',new.stderr


def test_preflight_checks_package_origin_hash_and_lazy_function(capsys):
    preflight(CODE)
    assert 'DEPENDENCY_PREFLIGHT_PASS' in capsys.readouterr().out


def test_missing_dependency_fails_early_in_isolated_package(tmp_path):
    root=tmp_path/'broken'
    with zipfile.ZipFile(HERE/'DATAIKU_EXISTING_NFS_CLIENT_20261030_R9.zip') as z:z.extractall(root)
    (root/'client/02_BACKEND/semantic_runtime/term_links.py').unlink()
    text=f'import sys;from pathlib import Path;r=Path({str(root)!r});sys.path[:0]=[str(r),str(r/"client"),str(r/"client/02_BACKEND")];from projection_preflight import preflight;preflight(r)'
    run=subprocess.run([sys.executable,'-I','-c',text],cwd=tmp_path,capture_output=True,text=True,timeout=20)
    assert run.returncode!=0 and 'term_links' in run.stderr


def test_progress_formatter_avoids_invented_total_percentage(tmp_path,capsys):
    progress.console_event(tmp_path,'PROGRESS',phase='FTS_POSTINGS_SORT',asset='fulltext/units.sqlite',
        elapsed_seconds=90,phase_seconds=45,sqlite_steps=10000,cpu_seconds=30,
        temp_free_bytes=3*1024**3)
    text=capsys.readouterr().out
    assert 'FTS_POSTINGS_SORT' in text and 'fulltext/units.sqlite' in text
    assert 'SQLite작업량=10000' in text and '경과=90초' in text
    assert '%' not in text
    saved=json.loads((tmp_path/'progress-latest.json').read_text())
    assert saved['phase']=='FTS_POSTINGS_SORT'


def test_heartbeat_runs_while_main_work_has_no_row_updates(tmp_path):
    tick=threading.Event();seen=[]
    def emit(status,**fields):
        seen.append((status,fields))
        if status=='PROGRESS':tick.set()
    with patch.object(progress.Progress,'check',return_value=None):
        with progress.tracking(tmp_path,emit,interval=0.01):
            progress.report('FTS_POSTINGS_SORT',asset='unit.sqlite')
            assert tick.wait(2)
    assert any(s=='PROGRESS' and f['phase']=='FTS_POSTINGS_SORT' for s,f in seen)


def test_sqlite_vm_callback_reports_real_work(tmp_path):
    db=sqlite3.connect(':memory:')
    with patch.object(progress.Progress,'check',return_value=None):
        with progress.tracking(tmp_path,lambda *a,**k:None) as current:
            with progress.sqlite_work(db):
                db.execute('WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<5000) SELECT SUM(x) FROM n').fetchone()
            assert current.fields['sqlite_steps']>0
    db.close()


def test_stage_change_clears_old_table_counter(tmp_path):
    p=progress.Progress(tmp_path,lambda *a,**k:None)
    p.set('SOURCE_DESCRIPTOR_TABLE',table='document',rows_processed=10,rows_total=10)
    p.set('FTS_POSTINGS_SORT',asset='unit.sqlite')
    assert 'rows_total' not in p.fields and 'rows_processed' not in p.fields
