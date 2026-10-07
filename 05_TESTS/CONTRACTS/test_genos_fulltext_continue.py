"""Continuation reuses complete navigation and preserves article FTS/inputs."""
from contextlib import closing
import fcntl
import io
import json
from pathlib import Path
import sqlite3
import sys
import pytest
from semantic_runtime.contracts import sha
from semantic_runtime import unit_fulltext
from lawrag.pipeline.term_generation import build_generation
from test_document_release import source
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'06_TOOLS/OFFLINE'))
import genos_fulltext_continue as tool
from genos_reindex_logging import BuildLog

@pytest.fixture
def baseline(tmp_path,term_glossary):
    raw=source(tmp_path/'raw.sqlite',[('d','모의규정',['제1조 승인 규칙','① 적용 기준','1. 승인 절차','가. 긴급 승인 허용','2. 일반 승인 금지'])])
    nodes=[('0',None,'kr_article','제1조',0,5),('1','0','circled','①',1,5),('2','1','dot_number:1','1.',2,4),('3','2','hangul_dot','가.',3,4),('4','1','dot_number:1','2.',4,5)]
    with sqlite3.connect(raw) as db:
        db.execute('DELETE FROM source_unit')
        for uid,parent,family,surface,lo,hi in nodes:
            db.execute('INSERT INTO source_unit VALUES(?,?,?,?)',('d',uid,parent,json.dumps(dict(family=family,surface=surface,title='',span=[lo,hi]))))
            db.execute('UPDATE source_block SET unit_id=? WHERE block_id=?',(uid,uid))
    path=tmp_path/'reindex/baseline';build_generation(raw,term_glossary,path,serving=False)
    (path.parent/'fulltext').mkdir();(path.parent/'fulltext/partial').write_text('existing article FTS retained')
    return path


def execute(baseline,out,helper=unit_fulltext):
    log=BuildLog(out.parent/'log',terminal=io.StringIO(),interval=.01)
    try:return tool.run(baseline,out,helper,log,workers=1)
    finally:log.close(0)


def test_continuation_exact_minimum_unit_coverage_input_preservation_and_reuse(baseline,monkeypatch):
    from lawrag.pipeline import term_generation
    monkeypatch.setattr(term_generation,'build_generation',lambda *a,**kw:pytest.fail('navigation must never rebuild'))
    before={str(p):sha(p) for p in baseline.parent.rglob('*') if p.is_file()}
    out=baseline.parent/'fulltext-unit-r1';r=execute(baseline,out)
    assert r['completed'] and r['counts']['unit']==5 and r['counts']['covered_blocks']==5
    assert not r['activated'] and not r['shared_published'] and not r['navigation_rebuilt']
    assert all(sha(p)==v for p,v in before.items())
    idx=unit_fulltext.UnitFulltextIndex(out/'fulltext-units',json.loads((baseline/'generation/navigation/manifest.json').read_text()))
    with closing(idx.connect()) as db:
        hits=idx.rank_units(db,['긴급']);assert len(hits)==1 and hits[0]['unit_id']=='3' and hits[0]['block_ids']==['3']
    assert execute(baseline,out)['fulltext_manifest_sha256']==r['fulltext_manifest_sha256']
    events=[json.loads(x) for x in (out.parent/'log/events.jsonl').read_text().splitlines()]
    assert any(x.get('task')=='unit-tokenize-and-index' and x.get('completed')==x.get('total')==5 for x in events)
    assert any(str(x.get('task','')).startswith('sha256:') and x.get('unit')=='bytes' for x in events)


def test_active_r8_lock_refuses_without_modifying_output(baseline):
    out=baseline.parent/'fulltext-unit-r1'
    with (baseline.parent/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(RuntimeError,match='worker'):execute(baseline,out)
    assert not out.exists()


def test_incomplete_retained_and_only_fulltext_restarted(baseline):
    out=baseline.parent/'fulltext-unit-r1';out.mkdir();(out/'partial').write_text('retained')
    execute(baseline,out)
    assert list(out.parent.glob(out.name+'.incomplete-*/partial'))[0].read_text()=='retained'


def test_completed_manifest_drift_rejected(baseline):
    out=baseline.parent/'fulltext-unit-r1';execute(baseline,out)
    m=out/'fulltext-units/manifest.json';obj=json.loads(m.read_text());obj['changed']=True;m.write_text(json.dumps(obj))
    with pytest.raises(ValueError,match='manifest changed'):execute(baseline,out)


def test_completed_audit_drift_rejected_no_completed_receipt(baseline):
    p=baseline/'audit/navigation/navigation.sqlite'
    with p.open('ab') as stream:stream.write(b'drift')
    out=baseline.parent/'fulltext-unit-r1'
    with pytest.raises(ValueError,match='audit snapshot'):execute(baseline,out)
    assert not (out/'continuation.json').exists()


def test_output_inside_parent_refused(baseline):
    with pytest.raises(ValueError,match='sibling'):execute(baseline,baseline/'generation/new')


def test_nfs_publication_complete_generation_and_audit_verified_without_activation(baseline,tmp_path):
    out=baseline.parent/'fulltext-unit-r1';execute(baseline,out)
    shared=tmp_path/'shared';shared.mkdir()
    log=BuildLog(tmp_path/'shared-log',terminal=io.StringIO())
    try:
        receipt=tool.publish_shared(baseline,out,shared,unit_fulltext,log)
        gen=Path(receipt['generation_path'])
        assert gen.is_dir() and not receipt['activated'] and not receipt['serving_verified']
        assert (gen/'fulltext-units/units.sqlite').is_file()
        assert sha(gen/'navigation/navigation.sqlite')==sha(baseline/'generation/navigation/navigation.sqlite')
        assert sha(gen.parent/'audit/navigation/navigation.sqlite')==sha(baseline/'audit/navigation/navigation.sqlite')
        assert tool.publish_shared(baseline,out,shared,unit_fulltext,log)['files']==receipt['files']
        assert not (shared/'CURRENT.json').exists()
        with (gen/'fulltext-units/units.sqlite').open('ab') as f:f.write(b'drift')
        with pytest.raises(ValueError,match='size'):tool.publish_shared(baseline,out,shared,unit_fulltext,log)
    finally:log.close(0)


def test_frozen_r8_backend_standalone_package_build_and_nfs_publication(baseline,tmp_path):
    import os,shutil,subprocess,zipfile
    import package_genos_fulltext_continue_r2 as pack
    # Freeze the native R8 runtime, while retaining unchanged package dependencies.
    dev=tmp_path/'dev';backend=dev/'02_BACKEND';backend.mkdir(parents=True)
    shutil.copytree(ROOT/'02_BACKEND/semantic_runtime',backend/'semantic_runtime',ignore=shutil.ignore_patterns('__pycache__'))
    r8=ROOT/'08_DEPLOYMENT/GENOS/handoffs/reindex_only_20261002_r8/GENOS_REINDEX_ONLY_20261002_R8.zip'
    with zipfile.ZipFile(r8) as z:
        for name in z.namelist():
            if name.startswith('02_BACKEND/semantic_runtime/') and name.endswith('.py'):
                (dev/name).write_bytes(z.read(name))
    assert sha(backend/'semantic_runtime/fulltext.py')=='bff0476d8edc2bb1f7be29261a4e85f0fe9a30aacec727eae8952cbcbad65237'
    payload=tmp_path/'payload';payload.mkdir()
    pack.main()
    with zipfile.ZipFile(pack.OUT/(pack.STEM+'.zip')) as z:z.extractall(payload)
    shared=tmp_path/'nfs';shared.mkdir()
    env={**os.environ,'PYTHONPATH':str(ROOT/'02_BACKEND')}
    result=subprocess.run([sys.executable,str(payload/'genos_fulltext_continue.py'),'--dev',str(dev),
        '--baseline',str(baseline),'--output',str(baseline.parent/'fulltext-unit-r1'),
        '--log-dir',str(tmp_path/'field-log'),'--workers','2','--shared-root',str(shared)],env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert 'shared-publication' in result.stdout
    publication=list(shared.rglob('publication.json'))
    assert len(publication)==1 and json.loads(publication[0].read_text())['completed']
    assert (tmp_path/'field-log/events.jsonl').is_file()


def test_locator_missing_input_does_not_create_empty_reindex(tmp_path,capsys):
    root=tmp_path/'data';root.mkdir()
    with pytest.raises(ValueError,match='No completed baseline'):
        tool.locate_baseline(tmp_path/'dev',root,'missing',roots=[root])
    assert not (root/'TERM_RELEASES').exists()
    assert 'BASELINE CHECK' in capsys.readouterr().out


def test_locator_same_run_alias_reuse_and_unknown_run_not_auto_selected(baseline,tmp_path,capsys):
    root=tmp_path/'data';target=root/'TERM_RELEASES/right/reindex';target.mkdir(parents=True)
    import shutil
    shutil.copytree(baseline,target/'baseline')
    assert tool.locate_baseline(tmp_path/'dev',root,'right',roots=[root])==target/'baseline'
    with pytest.raises(ValueError,match='No completed baseline'):
        tool.locate_baseline(tmp_path/'dev',root,'wrong',roots=[root])
    assert 'AVAILABLE BASELINE (not selected) run=right' in capsys.readouterr().out
    assert not (root/'TERM_RELEASES/wrong').exists()


def test_locator_ambiguous_roots_require_explicit_selection(baseline,tmp_path):
    import shutil
    roots=[tmp_path/'one',tmp_path/'two']
    for root in roots:shutil.copytree(baseline,root/'TERM_RELEASES/selected/reindex/baseline')
    with pytest.raises(ValueError,match='Multiple completed'):
        tool.locate_baseline(tmp_path/'dev',roots[0],'selected',roots=roots)
    exact=roots[1]/'TERM_RELEASES/selected/reindex/baseline'
    assert tool.locate_baseline(tmp_path/'dev',roots[0],'selected',roots=roots,explicit=exact)==exact


def test_lock_missing_baseline_explained_and_not_created(tmp_path):
    path=tmp_path/'absent/reindex'
    with pytest.raises(ValueError,match='Completed baseline'):
        with tool.exclusive(path):pytest.fail('missing input accepted')
    assert not path.exists()
