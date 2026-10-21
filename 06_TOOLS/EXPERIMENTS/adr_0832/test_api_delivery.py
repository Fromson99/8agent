"""Supplement: the initial direct_note fixture failed before assessment.

This uses the valid navigation fixture and checks the assessment delivery ledger,
publication and duplicate-request reuse. The known legacy publication guard is
checked separately using the actual failed journal in memory.
"""
import json
import sqlite3
import pytest
from test_main50_request_repair import tree
from test_source_span_norm import SpanTransport
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT
from test_unified_legal_agent import ok


@pytest.mark.parametrize('reject_once',[False,True])
def test_assessment_owns_exact_delivery_and_duplicate_does_not_call(tmp_path,tree,reject_once):
    from semantic_runtime.app import create_app
    from fastapi.testclient import TestClient
    from semantic_runtime.legal_agent import completion_contracts as cc
    class Capture(SpanTransport):
        def send_once(self,*,body,ticket):
            view=json.loads(body['messages'][1]['content'])['view']
            if view.get('source_stage','').startswith('memory-assess'):
                assert all('text' not in s for s in view['sources'])
                assert 'exact_evidence' not in view and view['evidence_options']
                paths=list(tmp_path.rglob('journal.sqlite'))
                assert len(paths)==1
                self.assessment_journal=paths[0]
                with sqlite3.connect('file:'+str(paths[0])+'?mode=ro',uri=True) as db:
                    self.assessment_view_id=db.execute("SELECT view_id FROM model_attempt WHERE status='SENT' ORDER BY created_seq DESC LIMIT 1").fetchone()[0]
                    assert db.execute('SELECT count(*) FROM presentation WHERE view_id=?',(self.assessment_view_id,)).fetchone()[0]>0
            return super().send_once(body=body,ticket=ticket)
    gen,idx=tree;t=Capture(False,reject_once);t.direct_note=False
    profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,
        'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'completion_contract':True,
            'completion_policy_version':cc.V8,'compact_input':True}}
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile=profile,legal_agent_transport=t,
        memory_identity=lambda _:{'user_id':'u','team_id':'t','document_ids':['d']})
    app.state.pipeline.term_agent.unit_fulltext=idx
    with TestClient(app) as api:
        body={'question':'모의승인규정 제1조 승인 기준은?','session_id':'delivery','request_id':'r1'}
        out=ok(api.post('/v1/rag/ask',json=body));calls=len(t.phases)
        assert '승인 후 보고한다.' in out['answer']['text']
        again=ok(api.post('/v1/rag/ask',json=body))
        assert again['answer']==out['answer'] and len(t.phases)==calls
    path=t.assessment_journal
    with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
        assert db.execute("SELECT count(*) FROM presentation p JOIN model_attempt a USING(view_id) WHERE p.view_id=? AND a.status='SUCCEEDED'",(t.assessment_view_id,)).fetchone()[0]>0
