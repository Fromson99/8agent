"""Session ownership, unsigned ingress and legal projection contracts."""
import copy,hashlib,json,sqlite3
from types import SimpleNamespace
import pytest
from semantic_runtime import chat_adapter
from semantic_runtime.legal_agent import memory_identity
from semantic_runtime.legal_agent.corrected_memory import MemoryError
from semantic_runtime.legal_agent.knowledge_repository import KnowledgeRepository
from semantic_runtime.legal_agent.unified_runtime import open_cases
from test_unified_legal_agent import unified,ok
from test_memory_runtime_v2 import command
from test_structure_first_search import structured_generation

def body():
    return dict(question='모의 질문',memory=True,user_id='u',team_id='risk_team',session_id='s',request_id='r')

def test_unsigned_session_does_not_read_signing_key(monkeypatch):
    monkeypatch.delenv('GENOS_MEMORY_SIGNING_KEY',raising=False)
    assert memory_identity.validate_session(body())=={'user_id':'u','team_id':'risk_team'}
    monkeypatch.setenv('GENOS_MEMORY_SIGNING_KEY','invalid-unused')
    assert memory_identity.validate_session(body())=={'user_id':'u','team_id':'risk_team'}
    assert not hasattr(memory_identity,'signed_bytes') and not hasattr(memory_identity,'verify_assertion')

@pytest.mark.parametrize('field,value',[(k,v) for k in ('user_id','team_id','session_id','request_id') for v in ('',None,'anonymous')]+[('expected_revision',0),('expected_revision',True),('use_llm',False)])
def test_unsigned_session_still_validates_selectors(field,value):
    with pytest.raises(MemoryError):memory_identity.validate_session({**body(),field:value})

def test_document_selection_and_public_export_boundary_remain(monkeypatch):
    from semantic_runtime import team_scope
    monkeypatch.setattr(team_scope,'select_documents',lambda store,team:['d','other'])
    pipeline=SimpleNamespace(store=object(),term_agent=SimpleNamespace(unified=True,transport=SimpleNamespace(public_scope=['d'])))
    with pytest.raises(MemoryError):memory_identity.resolve(pipeline,body())
    assert memory_identity.resolve(pipeline,{**body(),'public_question':True})['document_ids']==['d']

def test_native_and_workflow_need_no_secret_and_ignore_old_signature(monkeypatch):
    monkeypatch.setenv('GENOS_MEMORY_ENABLED','1');monkeypatch.setenv('TEAM_ID','risk_team')
    monkeypatch.delenv('GENOS_MEMORY_SIGNING_KEY',raising=False)
    data={'userId':'full/user/id','chatId':'full/session/id','request_id':'r','memory_authorization':{'signature':'obsolete'}}
    direct=chat_adapter.request_body(data,'모의 질문')
    workflow=chat_adapter.views()._request_body('모의 질문',data)
    assert direct==workflow and direct['memory'] is True and 'memory_authorization' not in direct
    assert direct['user_id']=='u-'+hashlib.sha256(data['userId'].encode()).hexdigest()
    assert direct['session_id']=='s-'+hashlib.sha256(data['chatId'].encode()).hexdigest()
    assert direct['team_id']=='risk_team'
    assert chat_adapter.request_body({**data,'chatId':'other'},'모의 질문')['session_id']!=direct['session_id']

def test_removed_user_wiki_is_not_a_repository_view():
    class Cases:
        def __getattr__(self,name):raise AssertionError('Removed view must not read case history')
    with pytest.raises(MemoryError):KnowledgeRepository(Cases()).wiki('user_wiki',{})

def test_projection_only_writes_legal_wiki_and_preserves_old_files(tmp_path,monkeypatch):
    class EmptyKnowledge(KnowledgeRepository):
        def search(self,*a,**k):return {'experiences':[],'next':None}
    class Cases:
        def transaction(self):
            from contextlib import nullcontext
            return nullcontext()
        db=sqlite3.connect(':memory:')
    c=Cases();c.db.execute('CREATE TABLE outbox(id,payload,hash,kind,status)')
    from semantic_runtime.legal_agent.corrected_memory import digest
    principal={'user_id':'u','team_id':'risk_team'}
    root=tmp_path/digest(['u','risk_team']);old=root/'user_wiki/index.json';old.parent.mkdir(parents=True);old.write_text('historical')
    result=EmptyKnowledge(c).rebuild(principal,tmp_path)
    assert set(result)=={'legal_wiki'} and old.read_text()=='historical'
    assert (root/'legal_wiki/index.json').is_file()
    assert not (root/'user_wiki/index.md').exists()
    c.db.close()

def test_actual_session_correction_and_shortcut_survive_without_personal_context(unified,monkeypatch):
    client,send,t,p,runtime=unified
    client.app.state.pipeline.contracts.pipeline['shortcut_v4']={'features':{'capture':True,'hint':True}}
    seen=[];t.before_return=lambda phase,view:seen.append(copy.deepcopy(view))
    first=ok(send());gid=first['question_id']
    corrected=ok(send(command('FACT_UPDATE',target=gid,facts=[{'name':'대상','value':'A'}])))
    assert corrected['question_id']==gid and corrected['executed']==['ASSESS','COMPOSE']
    stored=ok(send(command('EXPERIENCE_CONFIRM',target=gid)))
    assert stored['status']=='STORED' and stored['experience_id']
    assert not any('user_wiki' in json.dumps(v) or 'personal_history' in json.dumps(v) for v in seen)
    with sqlite3.connect(runtime/'case-memory/cases-v4.sqlite') as db:
        assert db.execute('SELECT count(*) FROM sw_intake').fetchone()[0]==3
        assert db.execute('SELECT count(*) FROM sw_trace').fetchone()[0]>=7
        assert db.execute("SELECT count(*) FROM sw_queue WHERE consumer='wiki'").fetchone()[0]>0
    assert not list((runtime/'case-memory/wikis').glob('*/user_wiki/*'))
    assert list((runtime/'case-memory/wikis').glob('*/legal_wiki/index.json'))
    second=ok(send(command('CASE_START',document_scope_mode='AUTHORIZED',task='별도 모의 질문',queries=['승인'],facts=[]),session_id='s2'))
    assert second['question_id']!=gid and second['investigation_id']!=first['investigation_id']

def test_unsigned_real_resolver_and_removed_query(unified,monkeypatch):
    client,send,t,p,runtime=unified
    import semantic_runtime.team_scope as teams
    monkeypatch.setattr(teams,'select_documents',lambda store,team:['d'] if team=='risk_team' else ['other'])
    # Rebuild an app without the fixture's injected identity resolver.
    from semantic_runtime.app import create_app
    from test_bounded_source_main import settings
    from test_legal_agent_double_harness import ROOT
    from fastapi.testclient import TestClient
    app=create_app(runtime.parent.parent,client.app.state.pipeline.store.path,contracts_root=ROOT,provider=object(),
                   implementation='legal-agent-unified-v6',legal_agent_profile={**settings(),'max_model_attempts':40},legal_agent_transport=t)
    with TestClient(app) as c:
        first=c.post('/v1/rag/ask',json={**body(),'question':'모의승인규정 대상은?'})
        assert first.status_code==200,first.text
        denied=c.post('/v1/rag/ask',json={**body(),'request_id':'denied','document_ids':['other']})
        assert denied.status_code==422,denied.text
        # AD mode remains the management boundary; user_wiki fails even inside it.
        assert c.post('/v1/rag/ask',json={**body(),'question':'[AD모드 시작]','request_id':'enter'}).json()['ad_mode']
        response=c.post('/v1/rag/memory/query',json={**body(),'question':'','request_id':'wiki','query_kind':'user_wiki'})
        assert response.status_code==422 and 'query_kind' in response.text,response.text
        legal=c.post('/v1/rag/memory/query',json={**body(),'question':'','request_id':'legal','query_kind':'legal_wiki'})
        assert legal.status_code==200,legal.text
