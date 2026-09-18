"""Source/term build and serving contracts. Synthetic documents, zero model calls."""
import json
from pathlib import Path
import sqlite3
from contextlib import closing
import pytest
from semantic_runtime.contracts import Contracts,sha
from semantic_runtime.storage import Store,publish
from semantic_runtime.term_index import TermIndex
from semantic_runtime.pipeline import Pipeline
from semantic_runtime.term_agent import TermAgent
from semantic_runtime.provider import Haiku
from lawrag.pipeline import glossary_assembly as assembly,glossary_v1 as v1
from lawrag.pipeline.term_generation import build_generation

ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture
def inputs(tmp_path):
    source=tmp_path/'source.sqlite'
    with sqlite3.connect(source) as db:
        db.executescript('''CREATE TABLE document(document_id TEXT PRIMARY KEY,name TEXT,source_artifact_sha256 TEXT,json TEXT);
        CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT);
        CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT);''')
        for did in ['mock-a','mock-b']:
            db.execute('INSERT INTO document VALUES (?,?,?,?)',(did,'가상규정 '+did,'a'*64,'{}'))
            for i,text in enumerate(['제1조(정의) 이 규정에서 “영업일”이란 토요일을 제외한 날을 말한다.','제2조(기간) 영업일의 계산에는 제1조를 준용한다.']):
                unit={'id':str(i),'parent':None,'title':['정의','기간'][i],'surface':f'제{i+1}조','family':'kr_article','span':[i,i+1],'block':i}
                db.execute('INSERT INTO source_unit VALUES (?,?,?,?)',(did,str(i),None,json.dumps(unit)))
                db.execute('INSERT INTO source_block VALUES (?,?,?,?,?,?)',(did,str(i),str(i),text,'a'*64,json.dumps({'idx':i,'text':text,'node':str(i)})))
    glossary=tmp_path/'glossary';glossary.mkdir()
    with sqlite3.connect(glossary/'dictionary.sqlite') as db:
        assembly.tables(db)
        v1.add_entry(db,'test:business-day','econedu','영업일','사전 설명')
    (glossary/'report.json').write_text(json.dumps({'schema_version':assembly.VERSION,'dictionary_sha256':sha(glossary/'dictionary.sqlite')}))
    return source,glossary

def test_publish_keeps_exact_originals_and_removes_legacy_tables(inputs,tmp_path):
    source,_=inputs
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE entity(id TEXT)');db.execute('CREATE TABLE authoring_job(id TEXT)')
    result=publish(ROOT,source,tmp_path/'published')
    with closing(Store(tmp_path/'published')) as store:
        assert not hasattr(store,'bundles')
        assert set(result['counts'])=={'document','source_unit','source_block'}
        with sqlite3.connect(source) as original:
            assert list(store.db.execute('SELECT text FROM source_block'))
            assert [tuple(r) for r in store.db.execute('SELECT * FROM source_block')]==original.execute('SELECT * FROM source_block').fetchall()
    with pytest.raises(ValueError,match='immutable'):publish(ROOT,source,tmp_path/'published')

def test_complete_source_term_build_resume_and_scoped_rag(inputs,tmp_path,monkeypatch):
    source,glossary=inputs
    # Any attempted extraction call is an error; the builder doesn't construct a provider.
    from semantic_runtime.genos_backend import Genos
    monkeypatch.setattr(Genos,'call',lambda *a,**k:pytest.fail('unexpected model call'))
    output=tmp_path/'build';result=build_generation(source,glossary,output)
    assert result['llm_calls']==0 and result['counts']['definition']>=2
    assert result['counts']['reference']>=2
    assert build_generation(source,glossary,output)==result
    with closing(Store(output/'generation')) as store:
        p=Pipeline(ROOT,store,Haiku(ROOT,tmp_path/'provider',False,backend='fixture',trust_zone='internal'))
        # Explicit old source-only adapter contract; current navigation is tested with a serving bundle.
        p.term_agent=TermAgent(p, {})
        result=p.run('영업일은 무엇인가요?',['mock-a'],False)
        assert result['assembly']['context']
        assert all(s['document_id']=='mock-a' for s in result['assembly']['context'])
        assert not {'cards','condition_assessments','relationship_paths'} & result['assembly'].keys()
        assert 'query_plan' not in result
        assert any(d['action']=='LOOKUP_DEFINITION' for d in result['retrieval']['term_agent']['trace'][0]['bounded_prefetch']['results'])
        tools=p.term_agent.get_index().tools(['mock-a'])
        try:
            seen=[s['id'] for s in result['assembly']['context']]
            tools.navigation_menu(seen,[],'영업일',['mock-a'])
            assert all(r['document_id']=='mock-a' for r in tools.references.values())
        finally:tools.db.close()
    with (output/'generation/navigation/navigation.sqlite').open('ab') as f:f.write(b'drift')
    with pytest.raises(ValueError,match='hash mismatch'):build_generation(source,glossary,output)

def test_runtime_loads_only_term_schema(monkeypatch):
    read=Path.read_text
    def guarded(path,*a,**kw):
        if path.name in {'LEGAL_SCHEMA.json','legal-semantic-v2.schema.json','rag-stage-v2.schema.json'}:
            pytest.fail('legacy schema read')
        return read(path,*a,**kw)
    monkeypatch.setattr(Path,'read_text',guarded)
    contracts=Contracts(ROOT)
    assert set(contracts.schemas)=={'urn:8-agent:term-runtime-v1'}
    with pytest.raises(Exception):contracts.validate({'question':'x','clause_values':{}},'urn:8-agent:term-runtime-v1','Request')

def test_removed_extraction_stage_fails_before_work(tmp_path):
    from lawrag.pipeline import genos_stages
    with pytest.raises(ValueError,match='retired'):
        genos_stages.execute({},None,tmp_path,'run','llm',progress=None)

def test_raw_xml_through_current_data_stages_to_rag(inputs,tmp_path,monkeypatch):
    from lawrag.pipeline import genos_build as build,genos_stages as stages
    from lawrag.core import llm
    from lawrag.pipeline.genos_status import Ledger,export_report
    monkeypatch.setattr(llm,'load_env',lambda:None)
    _,glossary=inputs
    raw=tmp_path/'raw';raw.mkdir()
    (raw/'rule.xml').write_text('''<법령><기본정보><법령명_한글>가상규정</법령명_한글></기본정보><조문>
    <조문단위><조문번호>1</조문번호><조문여부>조문</조문여부><조문제목>정의</조문제목>
    <조문내용>제1조(정의) 이 규정에서 “영업일”이란 토요일을 제외한 날을 말한다.</조문내용></조문단위></조문></법령>''')
    options=build.parser().parse_args(['build','--input-root',str(raw),'--build-dir',str(tmp_path/'out'),'--glossary-dir',str(glossary),'--execute'])
    plan=build.inventory(raw,'external',None)
    class Progress:
        def document(self,*a,**kw):pass
        def emit(self,*a,**kw):pass
        def finish(self,*a,**kw):pass
        def error(self,e):raise e
    logs=tmp_path/'logs';logs.mkdir()
    ledger=Ledger(logs);ledger.start(plan['files'],'all')
    try:
        result=stages.execute(plan,options,tmp_path/'data','fixture','all',progress=Progress(),dependencies={'fixture':'xml'},status=ledger,
                              provider_factory=lambda *a,**kw:pytest.fail('unexpected generation model'))
        ledger.finish('COMPLETED');export_report(logs)
    finally:ledger.close()
    assert result['ok'] and result['llm_calls']==0
    generated=next((tmp_path/'data/TERM/fixture').glob('*/generation'))
    with closing(Store(generated)) as store:
        p=Pipeline(ROOT,store,Haiku(ROOT,tmp_path/'provider',False,backend='fixture',trust_zone='internal'))
        p.term_agent=TermAgent(p, {})
        run=p.run('영업일의 정의',use_llm=False)
        assert run['assembly']['context']
        assert '토요일' in run['answer']['text']
    cached=next((tmp_path/'data/STRUCTURE').glob('*/source.sqlite'))
    with sqlite3.connect(cached) as db:
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='authoring_job'").fetchone()
    monkeypatch.setattr(build,'ingest_files',lambda *a,**kw:pytest.fail('unexpected reparse'))
    assert stages.execute(plan,options,tmp_path/'data','fixture','index',progress=Progress(),dependencies={'fixture':'xml'})['ok']

def test_declared_load_engine_consumes_source_only(inputs,tmp_path):
    import importlib.util
    spec=importlib.util.spec_from_file_location('term_engine_host',ROOT/'02_BACKEND/PIPELINE/engine_host.py')
    host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
    source,_=inputs
    request=tmp_path/'load.json';request.write_text(json.dumps({'source_store':str(source),'output':str(tmp_path/'loaded')}))
    config=host.load(ROOT)
    receipt=host.execute(config,'legal-load',{'request':{'path':str(request),'sha256':sha(request)}},tmp_path/'load-run',root=ROOT)
    assert receipt['status']=='COMPLETE'
    with closing(Store(tmp_path/'loaded')) as store:assert set(store.manifest['counts'])=={'document','source_unit','source_block'}
