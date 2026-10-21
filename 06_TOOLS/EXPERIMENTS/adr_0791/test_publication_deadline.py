"""Expired investigation still publishes verified receipts; no renewed research."""
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
from pathlib import Path
import json,sqlite3,time
import pytest
from fastapi.testclient import TestClient
from test_orchestration import tree,application,BODY
from semantic_runtime.workflow_bridge import Services,SourcePort
from semantic_runtime.legal_agent.errors import DeadlineExceeded,BudgetExhausted,ProposalError,TransportError,ContractError

@pytest.mark.parametrize('error',[DeadlineExceeded,BudgetExhausted,ProposalError,TransportError])
def test_expired_sql_callback_returns_verified_partial_and_duplicate(tmp_path,tree,monkeypatch,error):
    app,transport=application(tmp_path,tree)
    original=Services.structured;tools=Services.tools;ports=[];before={}
    @contextmanager
    def capture(self,work,context):
        with tools(self,work,context) as port:
            ports.append(port);yield port
    def expire(self,work,context,stage,*args,**kwargs):
        if stage=='BASIS':
            before.update(budget=work.budget(),deadline=work.run()['deadline_at'],calls=len(transport.views))
            object.__setattr__(context,'deadline',time.monotonic()-1)
            # Force the real SQLite interruption even for the small fixture.
            ports[-1].session.store.db.set_progress_handler(lambda:1,1)
            ports[-1].session.tools.db.set_progress_handler(lambda:1,1)
            raise error('synthetic expired investigation after both RAG returns')
        return original(self,work,context,stage,*args,**kwargs)
    monkeypatch.setattr(Services,'tools',capture);monkeypatch.setattr(Services,'structured',expire)
    with TestClient(app,raise_server_exceptions=False) as client:
        response=client.post('/v1/rag/ask',json=BODY)
        assert response.status_code==200,response.text
        value=response.json();assert value['status']=='partial' and value['answer']['answer_status']=='PARTIAL'
        assert value['evidence_refs'] and set(value['rag_results'])=={'internal','external'}
        assert value['usage']==before['budget'] and len(transport.views)==before['calls']
        expected='WORKFLOW_REPAIR_EXHAUSTED' if error is ProposalError else error.code
        assert value['error_code']==expected
        path=tmp_path/'runtime/workflows'/value['run_id']/'journal.sqlite'
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT deadline_at FROM run').fetchone()[0]==before['deadline']
            end=db.execute('SELECT deadline_at FROM workflow_publication_window').fetchone()[0]
            assert 0<(datetime.fromisoformat(end)-datetime.now(timezone.utc)).total_seconds()<=30
            assert db.execute("SELECT count(*) FROM event WHERE kind='WORKFLOW_PUBLICATION_VERIFY_STARTED'").fetchone()[0]==1
        repeat=client.post('/v1/rag/ask',json=BODY)
        assert repeat.status_code==200 and repeat.json()['answer']==value['answer']
        assert len(transport.views)==before['calls']

@pytest.mark.parametrize('fault',['tamper','window_expired'])
def test_failed_publication_verification_never_returns_unverified_answer(tmp_path,tree,monkeypatch,fault):
    app,transport=application(tmp_path,tree);original=Services.structured;before={}
    def expire(self,work,context,stage,*args,**kwargs):
        if stage=='BASIS':
            before['calls']=len(transport.views)
            object.__setattr__(context,'deadline',time.monotonic()-1)
            if fault=='window_expired':
                work.db.execute('CREATE TABLE workflow_publication_window(singleton INTEGER PRIMARY KEY,deadline_at TEXT NOT NULL)')
                work.db.execute('INSERT INTO workflow_publication_window VALUES(1,?)',((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),))
            raise DeadlineExceeded('synthetic expired investigation')
        return original(self,work,context,stage,*args,**kwargs)
    monkeypatch.setattr(Services,'structured',expire)
    if fault=='tamper':
        verify=SourcePort.verify_all
        def invalid(self):
            if self._verification_deadline is not None:raise ContractError('synthetic changed source bytes')
            return verify(self)
        monkeypatch.setattr(SourcePort,'verify_all',invalid)
    with TestClient(app,raise_server_exceptions=False) as client:
        response=client.post('/v1/rag/ask',json=BODY)
        assert response.status_code!=200 and 'answer' not in response.json()
        assert len(transport.views)==before['calls']
        path=next((tmp_path/'runtime/workflows').glob('*/journal.sqlite'))
        with sqlite3.connect(path) as db:
            status,result=db.execute('SELECT status,result_json FROM workflow_state').fetchone()
            assert status=='failed' and result is None
        again=client.post('/v1/rag/ask',json=BODY)
        assert again.status_code==409 and len(transport.views)==before['calls']

def test_no_evidence_deadline_produces_failed_result_without_model_calls(tmp_path,tree,monkeypatch):
    app,transport=application(tmp_path,tree);original=Services.structured
    def expire(self,work,context,stage,*args,**kwargs):
        if stage=='INTAKE':
            object.__setattr__(context,'deadline',time.monotonic()-1)
            raise DeadlineExceeded('synthetic before any verified evidence')
        return original(self,work,context,stage,*args,**kwargs)
    monkeypatch.setattr(Services,'structured',expire)
    with TestClient(app) as client:
        response=client.post('/v1/rag/ask',json=BODY)
        assert response.status_code==200,response.text
        value=response.json();assert value['status']=='failed' and value['evidence_refs']==[]
        assert value['usage']['model_reserved']==0 and not transport.views
