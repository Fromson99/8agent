"""Official law abbreviations name a document, and a law name is not split into glossary terms."""
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest
from semantic_runtime import document_aliases
from semantic_runtime.app import create_app
from semantic_runtime.document_navigation import EntityRegistry
from semantic_runtime.navigation_match import ReverseMatcher
from semantic_runtime.storage import Store
from lawrag.pipeline.term_generation import build_generation

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def generation(tmp_path, term_glossary):
    source = tmp_path/'source.sqlite'
    with sqlite3.connect(source) as db:
        db.executescript('''CREATE TABLE document(document_id TEXT PRIMARY KEY,name TEXT,source_artifact_sha256 TEXT,json TEXT);
        CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT);
        CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT);''')
        documents = [('law','가상 영업일 운영에 관한 법률',['영업일에 신청한다.']),
                     ('rule','가상내규',['영업일에 확인한다.'])]
        for did,name,texts in documents:
            artifact=hashlib.sha256(json.dumps(texts).encode()).hexdigest()
            db.execute('INSERT INTO document VALUES (?,?,?,?)',(did,name,artifact,'{}'))
            for i,text in enumerate(texts):
                unit={'family':'kr_article','surface':f'제{i+1}조','title':'절차','span':[i,i+1],
                      'coordinate_scope':'body','coordinate_key':f'body:제{i+1}조'}
                db.execute('INSERT INTO source_unit VALUES (?,?,?,?)',(did,str(i),None,json.dumps(unit)))
                db.execute('INSERT INTO source_block VALUES (?,?,?,?,?,?)',(did,str(i),str(i),text,artifact,'{}'))
    build_generation(source,term_glossary,tmp_path/'built',serving=True)
    return tmp_path/'built/generation'


class NoProvider:
    model=None


def matcher_for(tmp_path, generation, aliases):
    app=create_app(tmp_path,generation,contracts_root=ROOT,provider=NoProvider(),implementation='document-navigation-v1')
    agent=app.state.pipeline.term_agent;store=app.state.pipeline.store
    scope=[r[0] for r in store.db.execute('SELECT document_id FROM document')]
    with agent.resources(scope) as (index,tools,glossary,bound):
        yield ReverseMatcher(store.db,tools,glossary,document_aliases=aliases),bound,scope


def test_abbreviation_names_the_document_and_narrows_locators(tmp_path, generation):
    question='영업일법 제1조의 영업일 요건'
    for plain,_,scope in matcher_for(tmp_path,generation,{}):
        before=plain.starts(question,scope)
    for aliased,_,scope in matcher_for(tmp_path,generation,{'law':('영업일법',)}):
        after=aliased.starts(question,scope)
    assert before['documents']==[]
    assert {x['document_id'] for x in before['structures']}=={'law','rule'}
    assert [d['id'] for d in after['documents']]==['law']
    # 제1조 now binds to the named law only.
    assert {x['document_id'] for x in after['structures']}=={'law'}


def test_glossary_term_inside_a_law_name_is_not_a_question_concept(tmp_path, generation):
    question='영업일법 제1조의 영업일 요건'
    for plain,_,scope in matcher_for(tmp_path,generation,{}):
        before=[s for t in plain.starts(question,scope)['terms'] for s in t['question_spans']]
    for aliased,_,scope in matcher_for(tmp_path,generation,{'law':('영업일법',)}):
        after=[s for t in aliased.starts(question,scope)['terms'] for s in t['question_spans']]
    law_span=(0,len('영업일법'))
    assert any(law_span[0]<=s['start'] and s['end']<=law_span[1] for s in before)
    assert after and all(s['start']>=law_span[1] for s in after)
    # A term equal to the whole name is not shadowed; only strictly inner surfaces are.
    assert [s['text'] for s in after]==['영업일']


def test_interpretation_offers_the_abbreviated_document(tmp_path, generation):
    for aliased,bound,scope in matcher_for(tmp_path,generation,{'law':('영업일법',)}):
        bound.document_names=aliased.document_names;bound.title_keys=aliased.title_keys
        bound.document_aliases=aliased.document_aliases
        registry=EntityRegistry(bound,scope,'영업일법 제1조',[])
        items=registry.matches('영업일법 제1조')['items']
        found=registry.lookup('document','영업일법')['items']
    assert items[0]['type']=='document' and items[0]['identity']=='law'
    assert items[0]['question_spans'][0]['text']=='영업일법'
    assert [x['identity'] for x in found]==['law']


def law_xml(title, short):
    return ('<?xml version="1.0" encoding="UTF-8"?><법령><기본정보><법령명_한글><![CDATA['+title+']]></법령명_한글>'
            '<법령명약칭><![CDATA['+short+']]></법령명약칭></기본정보></법령>').encode()


def origin_for(root, store, files):
    package=root/'package';package.mkdir()
    (package/'manifest.json').write_text('{}')
    evidence={}
    for did,body in files.items():
        artifact=package/did/'source.xml';artifact.parent.mkdir();artifact.write_bytes(body)
        evidence[did]={'alias_raw_paths':[],'chain':[{'package_manifest':'package/manifest.json',
            'package_manifest_sha256':hashlib.sha256(b'{}').hexdigest(),'structure_artifact':did+'/result.json',
            'source_artifact':did+'/source.xml','source_sha256':hashlib.sha256(body).hexdigest(),'raw_paths':[]}]}
    return {'generation_id':store.manifest['generation_id'],'store_sha256':store.manifest['store_sha256'],'evidence':evidence}


def test_projection_reads_verified_xml_and_requires_the_same_law(tmp_path, generation):
    store=Store(generation)
    try:
        origin=origin_for(tmp_path,store,{'law':law_xml('가상 영업일 운영에 관한 법률','영업일법'),
                                         'rule':law_xml('다른 법률','다른법')})
        value=document_aliases.build(tmp_path,store,origin)
        assert value['documents']=={'law':{'name':'가상 영업일 운영에 관한 법률','aliases':[{
            'surface':'영업일법','field':'법령명약칭','source_artifact':'package/law/source.xml',
            'source_sha256':origin['evidence']['law']['chain'][0]['source_sha256']}]}}
        assert set(value['skipped'])=={'rule'}
        path=tmp_path/'aliases.json';path.write_text(json.dumps(value,ensure_ascii=False))
        binding={'generation_id':store.manifest['generation_id'],'path':'aliases.json',
                 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        assert document_aliases.load(tmp_path,{'alias_projections':[binding]},store)=={'law':('영업일법',)}
        with pytest.raises(ValueError,match='hash mismatch'):
            document_aliases.load(tmp_path,{'alias_projections':[{**binding,'sha256':'0'*64}]},store)
        (tmp_path/'package/law/source.xml').write_bytes(law_xml('가상 영업일 운영에 관한 법률','변조법'))
        with pytest.raises(ValueError,match='source artifact hash mismatch'):
            document_aliases.build(tmp_path,store,origin)
    finally:
        store.close()


def test_middle_dot_variants_name_the_same_law():
    assert document_aliases._key('주식ㆍ사채 등의 전자등록에 관한 법률')==document_aliases._key('주식·사채 등의 전자등록에 관한 법률')


@pytest.fixture
def stored_generation(tmp_path, term_glossary):
    """A current build: the abbreviation is stored in document_metadata by genos_build."""
    source = tmp_path/'stored.sqlite'
    with sqlite3.connect(source) as db:
        db.executescript('''CREATE TABLE document(document_id TEXT PRIMARY KEY,name TEXT,source_artifact_sha256 TEXT,json TEXT);
        CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT);
        CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT);''')
        for did,name,meta in [('law','가상 영업일 운영에 관한 법률',{'document_title':'가상 영업일 운영에 관한 법률','official_abbreviation':'영업일법'}),
                              ('rule','가상내규',{})]:
            artifact=hashlib.sha256(did.encode()).hexdigest()
            db.execute('INSERT INTO document VALUES (?,?,?,?)',(did,name,artifact,json.dumps({'document_metadata':meta})))
            unit={'family':'kr_article','surface':'제1조','title':'절차','span':[0,1],'coordinate_scope':'body','coordinate_key':'body:제1조'}
            db.execute('INSERT INTO source_unit VALUES (?,?,?,?)',(did,'0',None,json.dumps(unit)))
            db.execute('INSERT INTO source_block VALUES (?,?,?,?,?,?)',(did,'0','0','영업일에 신청한다.',artifact,'{}'))
    build_generation(source,term_glossary,tmp_path/'stored-built',serving=True)
    return tmp_path/'stored-built/generation'


def test_stored_abbreviation_wins_over_projection(tmp_path, stored_generation):
    for m,_,scope in matcher_for(tmp_path,stored_generation,{'law':('투영법',),'rule':('내규법',)}):
        assert m.document_aliases=={'law':('영업일법',),'rule':('내규법',)}
        assert m.alias_sources=={'store':1,'projection':1}
        assert [d['id'] for d in m.starts('영업일법 제1조',scope)['documents']]==['law']
        assert m.starts('투영법 제1조',scope)['documents']==[]


def test_alias_status_is_reported_including_none(tmp_path, generation, stored_generation):
    for path,expected in [(generation,'NONE'),(stored_generation,'STORE')]:
        store=Store(path)
        try:assert document_aliases.status(tmp_path,{},store)['status']==expected
        finally:store.close()
    app=create_app(tmp_path,stored_generation,contracts_root=ROOT,provider=NoProvider(),implementation='document-navigation-v1')
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        health=client.get('/health').json()
    assert health['document_aliases']['status']=='STORE' and health['document_aliases']['store_documents']==1


def test_genos_build_stores_the_xml_abbreviation(tmp_path):
    from lawrag.pipeline import genos_build
    from lawrag.pipeline.document_representations import metadata
    raw=tmp_path/'raw';(raw/'law').mkdir(parents=True)
    (raw/'law/자본시장법.xml').write_bytes(law_xml('자본시장과 금융투자업에 관한 법률','자본시장법'))
    (raw/'law/무약칭.xml').write_bytes(law_xml('약칭 없는 법률',''))
    rows={r['name']:r for r in genos_build.inventory(raw,'external',None)['files']}
    assert rows['자본시장과 금융투자업에 관한 법률']['official_abbreviation']=='자본시장법'
    assert 'official_abbreviation' not in rows['약칭 없는 법률']
    assert metadata(rows['자본시장과 금융투자업에 관한 법률'])['official_abbreviation']=='자본시장법'
