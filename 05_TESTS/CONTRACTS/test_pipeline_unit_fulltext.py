"""Minimum-unit build, immutable navigation reuse and real tool search/read wiring."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import pytest
from semantic_runtime import fulltext,unit_fulltext
from semantic_runtime.contracts import sha
from lawrag.pipeline.term_generation import build_generation
from lawrag.pipeline.fulltext_stage import derive
from test_document_release import source
from test_legal_agent_v5 import app_for, SETTINGS
from test_bounded_source_main import settings

ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture
def built(tmp_path,term_glossary):
    texts=['제1조 승인 규칙','① 다음 각 호의 기준을 적용한다.',
           '1. 원칙은 다음 목과 같다.','가. 긴급 승인을 허용한다.',
           '2. 일반 승인은 금지한다.','② 승인 후 보고한다.']
    raw=source(tmp_path/'raw.sqlite',[('d','모의규정',texts),('other','다른규정',['비밀 원문'])])
    nodes=[('0',None,'kr_article','제1조',0,6),('1','0','circled','①',1,5),
           ('2','1','dot_number:1','1.',2,4),('3','2','hangul_dot','가.',3,4),
           ('4','1','dot_number:1','2.',4,5),('5','0','circled','②',5,6)]
    with sqlite3.connect(raw) as db:
        db.execute("DELETE FROM source_unit WHERE document_id='d'")
        for uid,parent,family,surface,lo,hi in nodes:
            db.execute('INSERT INTO source_unit VALUES(?,?,?,?)',('d',uid,parent,json.dumps(dict(family=family,surface=surface,title='',span=[lo,hi]))))
            db.execute('UPDATE source_block SET unit_id=? WHERE document_id=? AND block_id=?',(uid,'d',uid))
    build_generation(raw,term_glossary,tmp_path/'baseline',serving=True)
    return tmp_path/'baseline/generation'

def test_derive_preserves_parent_navigation_and_structure_and_reuses_completed_output(built,tmp_path):
    before={str(p.relative_to(built)):sha(p) for p in built.rglob('*') if p.is_file()}
    out=tmp_path/'unit-generation';receipt=derive(built,out,workers=1)
    assert receipt['completed'] and not receipt['navigation_rebuilt'] and not receipt['activated']
    assert sha(out/'navigation/navigation.sqlite')==sha(built/'navigation/navigation.sqlite')
    assert sha(out/'store.sqlite')==sha(built/'store.sqlite')
    assert all(sha(built/name)==value for name,value in before.items())
    manifest=json.loads((out/'manifest.json').read_text());nav=json.loads((out/'navigation/manifest.json').read_text())
    idx=fulltext.open_bound(out,manifest['fulltext'],nav)
    assert isinstance(idx,unit_fulltext.UnitFulltextIndex)
    with closing(idx.connect()) as db:
        hits=idx.rank_units(db,['긴급'])
        assert len(hits)==1 and hits[0]['unit_id']=='3' and hits[0]['block_ids']==['3']
        assert '일반' not in hits[0]['text'] and '보고' not in hits[0]['text']
        assert idx.rank(db,['긴급'])==[hits[0]['source_id']]
        assert idx.rank_units(db,['긴급'],set())==[]
        assert idx.rank_units(db,['긴급'],limit=0)==[]
        with pytest.raises(ValueError,match='scope'):idx.rank_units(db,['긴급'],{'foreign'})
    assert derive(built,out,workers=1)==receipt
    assert fulltext.cached_open_bound(out,manifest['fulltext'],nav) is fulltext.cached_open_bound(out,manifest['fulltext'],nav)

def test_pipeline_cli_minimum_unit_and_changed_parent_rejected(built,tmp_path):
    out=tmp_path/'cli-generation'
    result=subprocess.run([sys.executable,str(ROOT/'06_TOOLS/pipeline.py'),'fulltext','--generation',str(built),'--output',str(out),'--workers','1'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert 'FULLTEXT_STAGE VERIFIED' in result.stdout
    logdir=out.parent/(out.name+'.logs')
    assert 'FULLTEXT_STAGE VERIFIED' in (logdir/'build.log').read_text()
    events=[json.loads(line) for line in (logdir/'progress.jsonl').read_text().splitlines()]
    assert events[0]['status']=='START' and events[-1]['status']=='FINISHED'
    assert any(e.get('total')==7 and e.get('completed')==7 for e in events)
    assert json.loads((out/'fulltext-units/manifest.json').read_text())['granularity']=='stored-own-block-owner'
    with pytest.raises(ValueError,match='separate'):derive(built,built/'child')
    with (built/'navigation/navigation.sqlite').open('ab') as f:f.write(b'drift')
    with pytest.raises(ValueError):derive(built,tmp_path/'bad')

def test_tool_fulltext_hit_reads_only_actual_leaf_and_scope(built,tmp_path):
    out=tmp_path/'unit-generation';derive(built,out,workers=1)
    app=app_for(tmp_path/'runtime',out,profile={**SETTINGS,**settings()});p=app.state.pipeline
    try:
        request={'question':'긴급 승인','document_ids':['d'],'use_llm':False}
        with p.term_agent.open_session(request,query=p.plan(request['question'],['d']),runtime=tmp_path/'runtime2') as s:
            sources=s.sources
            page,_,_,meta=sources.search({'target':sources.root,'query':'긴급','mode':'fulltext'},0)
            assert meta['search_receipt']['granularity']=='stored-own-block-owner'
            assert len(page)==1 and page[0]['fulltext_hit']['unit_id']=='3'
            action={**page[0]['read_action'],'question_refs':[], 'expected_information':'검색된 목의 원문 확인'}
            result=sources.execute(action,action_id='leaf-read',actor='SYSTEM_POLICY')
            assert result['status']=='OK',result.get('server_reason',result)
            evidence=[s.work.evidence(eid) for eid in result['evidence_ids']]
            assert {span['block_id'] for e in evidence for span in e['spans']}=={'3'}
            assert all(e['document_id']=='d' for e in evidence)
    finally:p.store.close()

def test_native_generation_build_can_select_unit_fulltext(tmp_path,term_glossary):
    raw=source(tmp_path/'raw.sqlite',[('d','모의규정',['승인 신청'])])
    build_generation(raw,term_glossary,tmp_path/'unit-build',serving=True,fulltext_granularity='unit')
    gen=tmp_path/'unit-build/generation';m=json.loads((gen/'manifest.json').read_text())
    idx=fulltext.open_bound(gen,m['fulltext'],json.loads((gen/'navigation/manifest.json').read_text()))
    assert isinstance(idx,unit_fulltext.UnitFulltextIndex)
    from lawrag.pipeline.term_serving_bundle import verify_assets
    verify_assets(gen)

def test_parallel_build_exact_progress_scope_and_payload_drift(built,tmp_path,monkeypatch):
    events=[]
    monkeypatch.setattr(fulltext,'_BUILD_PROGRESS',lambda **kw:events.append(kw),raising=False)
    nav=built/'navigation';out=tmp_path/'scoped-index'
    manifest=unit_fulltext.build(built,nav,out,document_ids=['d'],workers=2)
    assert manifest['counts']['unit']==6
    assert manifest['counts']['covered_blocks']==6
    assert manifest['scope']['document_version_ids']==['d']
    ticks=[e for e in events if e['task']=='unit-tokenize-and-index']
    assert ticks[0]['completed']==0 and ticks[-1]['completed']==ticks[-1]['total']==6
    idx=fulltext.open_index(out,json.loads((nav/'manifest.json').read_text()))
    with closing(idx.connect()) as db:
        assert {h['unit_id'] for h in idx.rank_units(db,['승인'])}=={'3','4','5'}
        assert not idx.rank_units(db,['비밀'])
    with (out/'units.sqlite').open('ab') as f:f.write(b'changed')
    with pytest.raises(ValueError,match='changed'):idx.connect()
    with pytest.raises(ValueError,match='hash'):fulltext.open_index(out,json.loads((nav/'manifest.json').read_text()))

def test_reuse_rejects_derived_manifest_drift(built,tmp_path):
    out=tmp_path/'unit-generation';derive(built,out,workers=1)
    manifest=json.loads((out/'manifest.json').read_text());manifest['unexpected']='drift'
    (out/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='manifest changed'):derive(built,out,workers=1)
