from copy import deepcopy
import json,sqlite3
import pytest
from fastapi.testclient import TestClient
from test_transitions import fixtures
General,prior,tree=fixtures.General,fixtures.prior,fixtures.tree
from semantic_runtime import workflow_rag
from semantic_runtime.legal_agent.research_continuity import history


def test_parent_child_continuity_survives_loss_after_followup_commit(tmp_path,tree,monkeypatch):
    app,_=prior.app_for(tmp_path,tree);transport=General('followup');app.state.pipeline.term_agent.transport=transport
    original=workflow_rag.execute;attempts=[];stopped=[]
    def interrupt(port,action,call_id):
        result=original(port,action,call_id)
        if action['args']['task'].get('research_task'):
            attempts.append((call_id,deepcopy(action['args']['task']['research_continuity']),len(transport.views)))
            if not stopped:
                stopped.append(True)
                raise KeyboardInterrupt('followup committed before parent receipt')
        return result
    monkeypatch.setattr(workflow_rag,'execute',interrupt)
    with pytest.raises(KeyboardInterrupt):
        app.state.workflow_runtime.execute({**prior.BODY,'workflow_id':'risk_team_compare_workflow'},prior.prior._base.PRINCIPAL)
    journal=next(app.state.workflow_runtime.root.glob('*/journal.sqlite'))
    with sqlite3.connect(journal) as db:
        revision=db.execute('SELECT revision FROM workflow_state').fetchone()[0]
        deadline=db.execute('SELECT deadline_at FROM run').fetchone()[0]
        reserved=db.execute('SELECT model_reserved FROM budget').fetchone()[0]
    with TestClient(app) as client:
        response=client.post('/v1/workflows/resume',json={'run_id':journal.parent.name,'session_id':'s','expected_revision':revision})
        assert response.status_code==200,response.text
        result=response.json()
        assert result['research_attempts'] and result['evidence_refs']
        count=len(transport.views)
        saved=client.get('/v1/workflows/runs/'+result['run_id'],params={'session_id':'s'})
        assert saved.json()['answer']==result['answer'] and len(transport.views)==count
    assert len(attempts)>=2 and attempts[0]==attempts[1]
    with sqlite3.connect(journal) as db:
        assert db.execute('SELECT deadline_at FROM run').fetchone()[0]==deadline
        assert db.execute('SELECT model_reserved FROM budget').fetchone()[0]>=reserved


def test_legacy_incomplete_history_is_visible_without_inventing_operation():
    task={'issue_id':'i','requested_fields':['condition'],'target_side':'external','missing_target':'원문 미확인','target_locator':None}
    board={'tasks':{'old':{'task':task,'status':'PARTIAL'}}}
    view=history(board)
    assert view[0]['operation']=='UNKNOWN' and view[0]['status']=='PARTIAL'
    assert 'operation' not in task and not view[0]['new_evidence_ids']
