"""MAIN route contracts using public pinned assets and a scripted provider, not quality evaluation."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.pipeline import Pipeline
from semantic_runtime.provider import Haiku
from semantic_runtime.navigation_agent import ServingNavigationAgent, glossary_assets

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'00_SYSTEM/WORKSPACE.json').is_file())
GENERATION=ROOT/'01_DATA/SEMANTIC/GENERATIONS/navigation-source-20260916-v1'

class Provider(Haiku):
    def __init__(self,path):
        super().__init__(ROOT,path,False,backend='fixture',trust_zone='internal')
        self.calls=0
    def call(self,role,task,data,schema):
        self.calls+=1
        assert role=='navigation'
        if not data['active_segments']:
            article=data['initial']['explicit_articles']['items'][0]
            actions=[{'tool':'READ','args':json.dumps({'source_id':article['id']}),'reason':'명시 조문 확인'}]
        else:
            segment=data['active_segments'][0]
            actions=[{'tool':'JUDGE','args':json.dumps({'segment_id':segment['id'],'issue_id':'Q1','status':'adopted','quote':segment['text'],'claim':segment['text']}),'reason':'읽은 원문 구간 확인'},
                     {'tool':'STOP','args':json.dumps({'status':'sufficient','unresolved':[]}),'reason':'배선 검사 완료'}]
        return {'issues':[{'id':'Q1','text':'명시 조문 확인'}],'actions':actions},self.record_local({'fixture':True})

def test_main_ask_read_adopt_answer_feedback(tmp_path):
    provider=Provider(tmp_path/'provider')
    app=create_app(tmp_path,GENERATION,contracts_root=ROOT,provider=provider,implementation='navigation-loop-v1')
    with TestClient(app) as client:
        assert isinstance(app.state.pipeline.term_agent,ServingNavigationAgent)
        assert client.get('/health').json()['rag_mode']=='navigation-loop-v1'
        q={'question':'유가증권시장 상장규정 제1조 내용을 확인해 주세요.','use_llm':True}
        response=client.post('/v1/rag/ask',json=q)
        assert response.status_code==200,response.text
        result=response.json();state=result['retrieval']['term_agent']
        assert state['status']=='FINISH' and state['failure'] is None,state
        assert provider.calls==2 and result['answer']['claims']
        assert len(state['read_source_ids'])==len(state['selected_ids'])==1
        assert result['answer']['claims'][0]['text']==state['adopted'][0]['quote']
        assert client.post('/v1/rag/feedback',json={'run_id':result['run_id'],'signal':'MISSING_EVIDENCE','reason':'wiring fixture'}).status_code==200
        assert client.post('/v1/rag/ask',json={**q,'document_ids':['invented']}).status_code==422

def test_unknown_implementation_fails_closed(monkeypatch):
    import semantic_runtime.pipeline as module
    contracts=SimpleNamespace(pipeline={'profiles':{'legal-rag':{'nodes':[{'id':'retrieve','parameters':{'term_agent':{'enabled':True,'implementation':'invented'}}}]}}})
    monkeypatch.setattr(module,'Contracts',lambda root:contracts)
    with pytest.raises(ValueError,match='unknown term agent'):Pipeline('.',None)

def test_glossary_path_cannot_escape_generation(tmp_path):
    with pytest.raises(ValueError):glossary_assets(tmp_path,{'glossary':{'bundle':'../escape','dictionary':'dict','cache':'cache'}})


def test_metadata_mode_never_calls_provider_or_selects_articles(monkeypatch):
    import semantic_runtime.navigation_agent as module
    class Tools:
        db=SimpleNamespace(close=lambda:None)
    glossary=SimpleNamespace(check_unchanged=lambda:None,close=lambda:None)
    pipeline=SimpleNamespace(store=SimpleNamespace(path=Path('.'),db=None),provider=SimpleNamespace(call=lambda *a:pytest.fail('metadata mode must not call model')))
    agent=ServingNavigationAgent(pipeline,{})
    monkeypatch.setattr(agent,'get_index',lambda:SimpleNamespace(tools=lambda scope:Tools()))
    monkeypatch.setattr(module,'glossary_assets',lambda *args:glossary)
    monkeypatch.setattr(module,'ReverseMatcher',lambda *args:None)
    monkeypatch.setattr(module,'NavigationSession',lambda *args:SimpleNamespace(context=lambda:{'initial':{'terms':['T1']}}))
    result=agent.retrieve({'question':'질문','scope':{'document_version_ids':['doc']},'generation_id':'fixture'},False)
    assert result['candidates']==[]
    state=result['term_agent']
    assert state['status']=='METADATA_ONLY' and state['calls']==0 and state['selected_ids']==[]
    assert state['initial']=={'terms':['T1']}

def test_main_default_is_document_navigation_with_verified_folders(tmp_path):
    from semantic_runtime.document_agent import ServingDocumentAgent
    provider=Provider(tmp_path/'provider')
    app=create_app(tmp_path,GENERATION,contracts_root=ROOT,provider=provider)
    with TestClient(app) as client:
        assert type(app.state.pipeline.term_agent) is ServingDocumentAgent
        assert client.get('/health').json()['rag_mode']=='document-navigation-v1'
        listing=client.get('/v1/rag/documents',params={'limit':500}).json()
        assert listing['total']==159 and listing['unknown_category_count']==4
        rows={r['id']:r for r in listing['documents']}
        assert rows['00f033fddcef6be2']['navigation_folder']=='external/law/증권의 발행 및 공시 등에 관한 규정'
        assert rows['38803e534c832e19']['category']=='unknown'
        internal=client.get('/v1/rag/documents',params={'category':'internal','limit':500}).json()
        assert internal['total']==10 and all(r['navigation_folder'].startswith('internal/') for r in internal['documents'])
        response=client.post('/v1/rag/ask',json={'question':'내규 폴더에 어떤 문서가 있어?','use_llm':False})
        assert response.status_code==200,response.text
        state=response.json()['retrieval']['term_agent']
        assert state['status']=='METADATA_ONLY' and state['calls']==0 and provider.calls==0
