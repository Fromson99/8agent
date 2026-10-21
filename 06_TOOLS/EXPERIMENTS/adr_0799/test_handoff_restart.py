from copy import deepcopy
import json,sqlite3
import pytest
from fastapi.testclient import TestClient
import test_handoff_orchestration as helper
from test_handoff_orchestration import tree,BODY,PRINCIPAL

RELEASE={'mode':'local-release','release_id':'synthetic','generation':1,'code_sha256':'code',
 'profile_sha256':'profile','data_manifest_sha256':'data','search_policy_sha256':'search',
 'schema_sha256':'schema','effective_profile_sha256':'effective','service_entry_sha256':'service',
 'investigation_budget':{'max_model_attempts':80},'process_id':101,'process_instance_id':'first'}

def app_with_release(tmp_path,tree,monkeypatch,release):
    create=helper.create_app
    def bound(*args,**kwargs):return create(*args,release=release,**kwargs)
    with monkeypatch.context() as m:
        m.setattr(helper,'create_app',bound)
        return helper.application(tmp_path,tree)

def restarted():return {**deepcopy(RELEASE),'process_id':202,'process_instance_id':'second'}

def test_restart_reuses_completed_answer(tmp_path,tree,monkeypatch):
    first,t=app_with_release(tmp_path,tree,monkeypatch,deepcopy(RELEASE))
    with TestClient(first) as c:
        response=c.post('/v1/rag/ask',json=BODY);assert response.status_code==200,response.text
        original=response.json()
    first.state.pipeline.store.close()
    second,t2=app_with_release(tmp_path,tree,monkeypatch,restarted())
    with TestClient(second) as c:
        response=c.post('/v1/rag/ask',json=BODY);assert response.status_code==200,response.text
        reused=response.json()
        assert {k:v for k,v in reused.items() if k!='execution_stats'}=={k:v for k,v in original.items() if k!='execution_stats'}
        assert reused['execution_stats']['llm_calls']==0 and not t2.views
        status=c.get('/v1/workflows/runs/'+original['run_id'],params={'session_id':BODY['session_id']})
        assert status.status_code==200 and status.json()['answer']==original['answer']
        assert status.json()['usage']==original['usage'] and not t2.views
    second.state.pipeline.store.close()

def test_restart_resumes_interrupted_child(tmp_path,tree,monkeypatch):
    from semantic_runtime import workflow_rag
    original=workflow_rag.execute
    first,t=app_with_release(tmp_path,tree,monkeypatch,deepcopy(RELEASE))
    def interrupt(*args,**kwargs):
        original(*args,**kwargs)
        raise KeyboardInterrupt('synthetic after child return')
    with monkeypatch.context() as m:
        m.setattr(workflow_rag,'execute',interrupt)
        with pytest.raises(KeyboardInterrupt):
            first.state.workflow_runtime.execute({**BODY,'workflow_id':'risk_team_compare_workflow'},PRINCIPAL)
    path=next((tmp_path/'runtime/workflows').glob('*/journal.sqlite'))
    with sqlite3.connect(path) as db:
        revision=db.execute('SELECT revision FROM workflow_state').fetchone()[0]
        deadline=db.execute('SELECT deadline_at FROM run').fetchone()[0]
    first.state.pipeline.store.close()
    second,t2=app_with_release(tmp_path,tree,monkeypatch,restarted())
    with TestClient(second) as c:
        r=c.post('/v1/workflows/resume',json={'run_id':path.parent.name,'session_id':'s','expected_revision':revision})
        assert r.status_code==200,r.text
        assert r.json()['status']=='completed'
        assert sum(stage=='memory-assess' for stage,_ in t2.views)==1
        assert r.json()['rag_results']['internal']['records']
    with sqlite3.connect(path) as db:assert db.execute('SELECT deadline_at FROM run').fetchone()[0]==deadline
    second.state.pipeline.store.close()

@pytest.mark.parametrize('key',[k for k in RELEASE if k not in ('mode','process_id','process_instance_id')])
def test_restart_rejects_changed_stable_binding(tmp_path,tree,monkeypatch,key):
    first,t=app_with_release(tmp_path,tree,monkeypatch,deepcopy(RELEASE))
    with TestClient(first) as c:assert c.post('/v1/rag/ask',json=BODY).status_code==200
    first.state.pipeline.store.close()
    changed=restarted();changed[key]={'changed':True} if isinstance(changed[key],dict) else str(changed[key])+'-changed'
    second,t2=app_with_release(tmp_path,tree,monkeypatch,changed)
    with TestClient(second) as c:
        r=c.post('/v1/rag/ask',json=BODY)
        assert r.status_code==409 and r.json()['error_code']=='WORKFLOW_BINDING_CHANGED'
        assert not t2.views
    second.state.pipeline.store.close()
