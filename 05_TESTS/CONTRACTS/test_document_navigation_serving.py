"""GENOS serving with actual small source/index/glossary assets and scripted models."""
import asyncio
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.document_agent import ServingDocumentAgent
from lawrag.pipeline.term_generation import build_generation

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def generation(tmp_path, term_glossary):
    source = tmp_path/'source.sqlite'
    with sqlite3.connect(source) as db:
        db.executescript('''CREATE TABLE document(document_id TEXT PRIMARY KEY,name TEXT,source_artifact_sha256 TEXT,json TEXT);
        CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT);
        CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT);''')
        documents = [('hr','가상내규','internal/hr/가상내규.html',['영업일에 신청한다.','「가상외규」 제1조에 따른다.']),
                     ('public','가상외규','external/kofia/규정/가상외규.html',['영업일에 확인한다.']),
                     ('unknown','출처미확인',None,['영업일 원문.'])]
        for did,name,path,texts in documents:
            artifact=hashlib.sha256(json.dumps(texts).encode()).hexdigest()
            meta={'document_metadata':{'relative_path':path,'source_category':'internal' if did=='hr' else 'external'}} if path else {}
            db.execute('INSERT INTO document VALUES (?,?,?,?)',(did,name,artifact,json.dumps(meta)))
            for i,text in enumerate(texts):
                unit={'family':'kr_article','surface':f'제{i+1}조','title':'절차','span':[i,i+1],
                      'coordinate_scope':'body','coordinate_key':f'body:제{i+1}조'}
                db.execute('INSERT INTO source_unit VALUES (?,?,?,?)',(did,str(i),None,json.dumps(unit)))
                db.execute('INSERT INTO source_block VALUES (?,?,?,?,?,?)',(did,str(i),str(i),text,artifact,'{}'))
    build_generation(source,term_glossary,tmp_path/'built',serving=True)
    return tmp_path/'built/generation'


class ScriptedProvider:
    def __init__(self, intent='catalogue'):
        self.intent=intent;self.calls=[];self.sources=[]
    def record_local(self,value):return {'kind':'scripted-local'}
    def call(self,role,system,data,schema):
        self.calls.append((role,data))
        if role=='structured_navigation' and 'work_state' not in data:
            scope='all' if self.intent=='catalogue' else 'current'
            if self.intent=='tree':
                scope=[next(x['handle'] for x in data['scope_menu']['items'] if x.get('identity')=='external/kofia')]
            if self.intent=='outline':
                scope=[next(x['handle'] for x in data['keyword_types']['items'] if x['type']=='document')]
            out={'action':{'tool':'INTERPRET_QUERY','args':{'intent':self.intent,'scope':scope,'bindings':[],
                   'title_query':'','clarification':''},'reason':'contract fixture'}}
        elif role=='navigation_requirements':
            out={'requirements':[{'id':'Q1','text':'영업일 절차','question_span':'영업일'}]}
        elif role=='structured_navigation':
            pending=[x for x in data['candidates']['items'] if x['review_status']=='unreviewed']
            out={'action':{'tool':'READ_BATCH','args':{'read_handles':[x['read_handle'] for x in pending[:3]]},'reason':'read actual candidates'}}
        elif role=='navigation_review':
            out={'reviews':[{'segment_id':x['id'],'status':'adopted','requirement_ids':['Q1'],
                            'quote_ref':x['quote_refs'][0]['id'],'claim':x['text']} for x in data['pending_review']]}
        elif role=='navigation_synthesis':
            self.sources=[x['id'] for x in data['sources']]
            out={'findings':[{'text':'선택된 원문에 신청·확인 절차가 있다.','source_ids':self.sources,'requirement_ids':['Q1']}],
                 'coverage':[{'requirement_id':'Q1','status':'complete','source_ids':self.sources,'missing':''}]}
        elif role=='navigation_verify':
            out={'requirements':[{'requirement_id':'Q1','status':'verified','missing':''}],
                 'findings':[{'index':0,'supported':True,'reason':'scripted contract'}],'search_queries':[]}
        else:raise AssertionError(role)
        return out,{'kind':'scripted','role':role}


def app_for(tmp_path,generation,provider):
    return create_app(tmp_path,generation,contracts_root=ROOT,provider=provider,implementation='document-navigation-v1')


def test_http_catalogue_outline_full_read_and_gateway(tmp_path,generation,monkeypatch):
    p=ScriptedProvider();app=app_for(tmp_path,generation,p)
    with TestClient(app) as client:
        assert isinstance(app.state.pipeline.term_agent,ServingDocumentAgent)
        assert client.get('/health').json()['rag_mode']=='document-navigation-v1'
        first=client.get('/v1/rag/documents',params={'limit':1}).json()
        assert first['total']==3 and first['next_offset']==1 and first['unknown_category_count']==1
        assert len(client.get('/v1/rag/documents',params={'offset':1}).json()['documents'])==2
        assert client.get('/v1/rag/documents',params={'folder':'external/kofia'}).json()['total']==1
        assert client.get('/v1/rag/documents',params={'title_query':'신청'}).json()['total']==0
        assert client.get('/v1/rag/documents',params={'category':'internal'}).json()['documents'][0]['id']=='hr'
        assert client.get('/v1/rag/document/outline',params={'doc_id':'hr'}).json()['total']==2
        a=client.get('/v1/rag/document/read',params={'doc_id':'hr','limit':1}).json()
        b=client.get('/v1/rag/document/read',params={'doc_id':'hr','offset':1}).json()
        assert a['next_offset']==1 and not a['complete'] and b['next_offset'] is None
        assert a['text']=='영업일에 신청한다.' and '가상외규' in b['text']
        assert client.get('/v1/rag/document/read',params={'doc_id':'hr','unit_id':'1'}).json()['total']==1
        assert client.get('/v1/rag/document/read',params={'doc_id':'invented'}).status_code==404
        assert client.get('/v1/rag/documents',params={'offset':-1}).status_code==422
        assert not p.calls
        import service
        monkeypatch.setattr(service,'_APP',app)
        result=asyncio.run(service.service({}, {'op':'call','method':'GET','path':'/v1/rag/documents'}))
        assert result['status']==200 and result['body']['total']==3


@pytest.mark.parametrize(('intent','question','kind'),[
    ('catalogue','전체 문서 목록 보여줘','CATALOG'),
    ('tree','kofia 폴더 트리를 보여줘','FOLDER_TREE'),
    ('outline','가상내규 목차 보여줘','TOC'),
])
def test_chat_metadata_is_rendered_without_legal_claims(tmp_path,generation,intent,question,kind):
    provider=ScriptedProvider(intent)
    with TestClient(app_for(tmp_path,generation,provider)) as client:
        response=client.post('/v1/rag/ask',json={'question':question})
        assert response.status_code==200,response.text
        result=response.json();state=result['retrieval']['term_agent']
        assert state['failure'] is None,state
        assert state['navigation_output']['kind']==kind
        assert result['answer']['text']==state['navigation_output']['text']
        assert not result['answer']['claims'] and not state['read_source_ids']
        assert state['mapping_persistence']=='REQUEST_ONLY' and len(provider.calls)==1


def test_actual_index_multi_read_answer_feedback_and_scope(tmp_path,generation):
    provider=ScriptedProvider('content')
    with TestClient(app_for(tmp_path,generation,provider)) as client:
        response=client.post('/v1/rag/ask',json={'question':'영업일 절차를 설명해줘','document_ids':['hr','public']})
        assert response.status_code==200,response.text
        result=response.json();state=result['retrieval']['term_agent']
        assert state['failure'] is None,state
        assert state['status']=='FINISH' and len(state['selected_ids'])>=2,state
        assert result['answer']['claims'][0]['source_ids']==provider.sources
        assert {x['document_id'] for x in result['selection']['selected']}=={'hr','public'}
        assert 'unknown' not in state['effective_document_ids']
        assert client.post('/v1/rag/feedback',json={'run_id':result['run_id'],'signal':'MISSING_EVIDENCE','reason':'synthetic'}).status_code==200
        previous=len(provider.calls)
        response=client.post('/v1/rag/ask',json={'question':'영업일','use_llm':False})
        assert response.status_code==200,response.text
        assert len(provider.calls)==previous and response.json()['retrieval']['term_agent']['selected_ids']==[]


def test_resolved_reference_contracts():
    from semantic_runtime.multi_entry_navigation import reference_resolved
    assert reference_resolved('EXACT_NAMED_DOCUMENT_ARTICLE')
    assert reference_resolved('EXACT_SAME_DOCUMENT_ARTICLE')
    assert not reference_resolved('UNRESOLVED')


def test_genos_entrypoint_selects_mode_without_model_calls(tmp_path,generation,monkeypatch):
    import service
    monkeypatch.setattr(service,'_APP',None)
    monkeypatch.setattr(service,'_BINDING',None)
    monkeypatch.setenv('GENOS_GENERATION',str(generation))
    monkeypatch.setenv('GENOS_RUNTIME_DIR',str(tmp_path/'runtime'))
    monkeypatch.setenv('GENOS_RAG_IMPLEMENTATION','document-navigation-v1')
    monkeypatch.setenv('SEMANTIC_LLM_BACKEND','genos')
    app=service.application()
    with TestClient(app) as client:
        assert client.get('/health').json()['rag_mode']=='document-navigation-v1'
        assert client.get('/v1/rag/documents').json()['total']==3


def test_stored_reference_targets_reach_work_queue(tmp_path,generation):
    from semantic_runtime.work_navigation import WorkSession
    provider=ScriptedProvider('content');app=app_for(tmp_path,generation,provider)
    with TestClient(app):
        agent=app.state.pipeline.term_agent
        with agent.resources(['hr','public']) as (_,tools,glossary,matcher):
            s=WorkSession(matcher,tools,glossary,'가상내규 영업일', ['hr','public'])
            try:
                sid=next(k for k,v in tools.sources.items() if '가상외규' in v['text'])
                s.discover_references(sid)
                refs=s.reference_rows()
                assert refs and refs[0]['resolution']=='EXACT_NAMED_DOCUMENT_ARTICLE'
                assert refs[0]['target_source_ids']
            finally:
                if s.fts:s.fts.close()


def test_http_mapping_proposal_is_reported_as_not_saved(tmp_path,generation):
    class MappingProvider(ScriptedProvider):
        def call(self,role,system,data,schema):
            self.calls.append((role,data))
            handle=next(x['handle'] for x in data['keyword_types']['items'] if x['type']=='document')
            return {'action':{'tool':'INTERPRET_QUERY','args':{'intent':'mapping','scope':'current',
                    'bindings':[{'expression':'가외규','handle':handle}],'title_query':'','clarification':''},
                    'reason':'contract fixture'}},{'kind':'scripted','role':role}
    with TestClient(app_for(tmp_path,generation,MappingProvider())) as client:
        response=client.post('/v1/rag/ask',json={'question':'가외규는 가상외규를 뜻해. 매핑해줘'})
        assert response.status_code==200,response.text
        result=response.json();state=result['retrieval']['term_agent']
        assert state['navigation_output']['kind']=='MAPPING_PROPOSALS' and state['mapping_proposal_ids']
        assert state['mapping_persistence']=='REQUEST_ONLY'
        assert '저장되지 않으므로' in result['answer']['text'] and '저장했습니다' not in result['answer']['text']


def test_origin_projection_classifies_only_its_own_generation(tmp_path,generation):
    from semantic_runtime.folder_navigation import load_origin_projection
    from semantic_runtime.storage import Store
    from semantic_runtime.document_browser import documents
    store=Store(generation)
    try:
        artifact=store.db.execute("SELECT source_artifact_sha256 FROM document WHERE document_id='unknown'").fetchone()[0]
        value={'schema_version':'document-origin-projection-v1','generation_id':store.manifest['generation_id'],
               'store_sha256':store.manifest['store_sha256'],
               'documents':{'unknown':{'document_id':'unknown','status':'verified','raw_relative_path':'internal/risk_team/forms/출처미확인.hwp','source_artifact_sha256':artifact}}}
        path=tmp_path/'projection.json';path.write_text(json.dumps(value,ensure_ascii=False))
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        config={'origin_projections':[{'generation_id':store.manifest['generation_id'],'path':'projection.json','sha256':digest}]}
        projection=load_origin_projection(tmp_path,config,store)
        rows={r['id']:r for r in documents(store,projection=projection)['documents']}
        assert rows['unknown']['category']=='internal' and rows['unknown']['navigation_folder']=='internal/risk_team/forms'
        assert documents(store,projection=projection)['unknown_category_count']==0
        assert load_origin_projection(tmp_path,{'origin_projections':[{**config['origin_projections'][0],'generation_id':'other'}]},store) is None
        with pytest.raises(ValueError,match='hash mismatch'):
            load_origin_projection(tmp_path,{'origin_projections':[{**config['origin_projections'][0],'sha256':'0'*64}]},store)
        value['documents']['unknown']['source_artifact_sha256']='0'*64;path.write_text(json.dumps(value))
        forged={'origin_projections':[{**config['origin_projections'][0],'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]}
        with pytest.raises(ValueError,match='source artifact mismatch'):
            documents(store,projection=load_origin_projection(tmp_path,forged,store))
    finally:store.close()
