"""Exact loop counters, estimated ETA, frozen R8 predecessor apply/rollback."""
import io
import json
import threading
import zipfile
import importlib.util
from contextlib import closing
import sqlite3
import pytest
from test_genos_reindex_only_r8 import selected, prepared, forbid_extra_work
from test_genos_optimized_rebuild_r7 import mixed
from test_genos_optimized_rebuild_r6 import historical
from test_genos_optimized_rebuild_r5 import real_checkout
from semantic_runtime.contracts import sha
import genos_reindex_logging as logging
import genos_reindex_only as index
import package_genos_reindex_r9 as pack

def test_loop_counters_match_actual_inputs_and_outputs(selected, prepared, tmp_path, monkeypatch):
    forbid_extra_work(monkeypatch)
    log=logging.BuildLog(tmp_path/'log',terminal=io.StringIO())
    try: result=index.rebuild(selected,log=log)
    finally: log.close(0)
    events=[json.loads(s) for s in (tmp_path/'log/events.jsonl').read_text().splitlines()]
    completed={r['task']:r for r in events if r.get('total') and r.get('completed')==r['total']}
    with closing(sqlite3.connect(prepared['source'])) as db:
        blocks=db.execute('SELECT count(*) FROM source_block').fetchone()[0]
    assert completed['block-matching']['completed']==blocks
    assert completed['document-navigation']['completed']==result['document_count']==3
    with closing(sqlite3.connect(result['fulltext_path']+'/fulltext.sqlite')) as db:
        sources=db.execute('SELECT count(*) FROM source_fts').fetchone()[0]
    assert completed['tokenize-and-index']['completed']==sources
    assert completed['catalogue-linking']['completed']>0
    from lawrag.pipeline import glossary_linking
    from semantic_runtime import term_index,fulltext
    assert all(not hasattr(m,'_BUILD_PROGRESS') for m in (glossary_linking,term_index,fulltext))

def test_eta_warmup_recent_speed_stall_and_uncounted_finalization(tmp_path,monkeypatch):
    now=[100.0]; monkeypatch.setattr(logging.time,'monotonic',lambda:now[0])
    log=logging.BuildLog(tmp_path/'log',terminal=io.StringIO(),interval=100)
    tid=threading.get_ident()
    try:
        with log.phase('links'):
            log.progress(task='blocks',completed=0,total=100,unit='blocks')
            assert log.progress_snapshot(tid)['remaining_seconds'] is None
            now[0]+=20; log.progress(task='blocks',completed=20,total=100,unit='blocks')
            value=log.progress_snapshot(tid)
            assert value['remaining_seconds']==80 and value['percent']==20
            assert value['overall_eta']=='unmeasured_later_stages'
            now[0]+=31
            assert log.progress_snapshot(tid)['remaining_seconds'] is None
            log.progress(task='validation',completed=0,total=None,unit='checks')
            assert log.progress_snapshot(tid)['total'] is None
            with log.phase('copy'):
                assert 'task' not in log.progress_snapshot(tid)
    finally:log.close(0)

def test_r9_apply_over_exact_r8_and_rollback(mixed):
    import package_genos_reindex_r8 as r8
    payload,dev,*rest=mixed
    with zipfile.ZipFile(r8.OUT/(r8.STEM+'.zip')) as z:z.extractall(payload)
    spec=importlib.util.spec_from_file_location('r9_apply',payload/'APPLY.py')
    applier=importlib.util.module_from_spec(spec);spec.loader.exec_module(applier)
    applier.apply(dev)
    before={name:sha(dev/name) for name in pack.CHANGED}
    with zipfile.ZipFile(pack.OUT/(pack.STEM+'.zip')) as z:
        rows=json.loads(z.read('CODE_MANIFEST.json'))['files']
        assert set(z.namelist())=={r['path'] for r in rows}|{'CODE_MANIFEST.json'}
        assert all(sha_bytes(z.read(row['path']))==row['sha256'] for row in rows)
        z.extractall(payload)
    receipt=applier.apply(dev)
    expected={row['path']:row['sha256'] for row in rows}
    assert all(sha(dev/name)==expected[name] for name in pack.CHANGED)
    backups=sorted((dev/'.genos-pipeline-optimization-backups').iterdir(),key=lambda p:p.stat().st_mtime_ns)
    applier.dependency().rollback(backups[-1])
    assert all(sha(dev/name)==expected for name,expected in before.items())

def sha_bytes(content):
    import hashlib
    return hashlib.sha256(content).hexdigest()
