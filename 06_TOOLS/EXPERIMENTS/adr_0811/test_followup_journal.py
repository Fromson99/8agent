"""The old input-view assertion is replaced with the durable consumer contract.

No product code, model behavior or source changes from frozen rev001.
"""
import json,sqlite3
from fastapi.testclient import TestClient
from test_handoff_orchestration import tree,application,BODY


def test_followup_preserves_child_case_in_journal_and_unaffected_side(tmp_path,tree):
    app,t=application(tmp_path,tree,'followup')
    with TestClient(app) as client:
        response=client.post('/v1/rag/ask',json=BODY)
        assert response.status_code==200,response.text
        out=response.json();views=[v for stage,v in t.views if stage=='workflow-basis']
        assert len(views)==2 and views[0]['rag_results']['external']==views[1]['rag_results']['external']
        assert out['status']=='completed' and out['rag_results']['internal']['records']
        journal=app.state.workflow_runtime.root/out['run_id']/'journal.sqlite'
        with sqlite3.connect(journal) as db:
            results=[json.loads(r[0]) for r in db.execute("SELECT result_json FROM workflow_call WHERE kind='rag' AND status='COMPLETE'")]
        inside=[r for r in results if r['side']=='internal'];outside=[r for r in results if r['side']=='external']
        assert len(inside)==2 and len(outside)==1
        assert len({r['continuation']['goal_id'] for r in inside})==1
        revisions=[r['continuation']['revision'] for r in inside]
        assert len(set(revisions))==2 and out['rag_results']['internal']['continuation']['revision']==max(revisions)
        calls=len(t.views);again=client.post('/v1/rag/ask',json=BODY)
        assert again.status_code==200 and again.json()['answer']==out['answer'] and len(t.views)==calls
