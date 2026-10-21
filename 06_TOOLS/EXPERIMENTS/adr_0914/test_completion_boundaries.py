"""Finite software boundaries for the unchanged candidate, no external model."""
from copy import deepcopy
import json,sqlite3
import pytest
from fastapi.testclient import TestClient
from test_main50_request_repair import tree,GAP
from test_source_span_norm import SpanTransport,proposal
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT,wire
from semantic_runtime.legal_agent.navigation_input import expand_cards
from semantic_runtime.legal_agent import completion_contracts as cc

@pytest.mark.parametrize('mode',['supported_gap','empty_then_supported','always_empty','one_bad_ref','repeated_bad_ref'])
def test_actual_api_supported_partial_and_missing_source_recovery(tmp_path,tree,mode):
    from semantic_runtime.app import create_app
    class Transport(SpanTransport):
        assessments=0
        def send_once(self,*,body,ticket):
            v=expand_cards(json.loads(body['messages'][1]['content'])['view']);phase=v.get('source_stage',v.get('phase',''))
            if '-read-choice' in phase:
                self.phases.append(phase)
                if v['sources']:
                    return wire({'choice':'FINISH','basis_refs':[s['id'] for s in v['sources']],
                        'issue_refs':[i['id'] for i in v['issues']],'evidence_sufficient':False,'reason':'미확보 범위를 보존하여 기존 원문 판단'})
                return wire({'choice':'READ','selections':[{'target':v['read_candidates'][0]['target'],'issue_id':v['issues'][0]['id'],
                    'missing_need':'현재 요청의 원문','relation':'DIRECT','source_ref':None}]})
            if phase.startswith('memory-assess'):
                self.phases.append(phase);self.assessments+=1
                ref=next(o['id'] for o in v['evidence_options'] if '승인 후 보고한다.' in o['text'])
                p=proposal('승인 후 보고한다.','OBLIGATION',[ref],ref);p.pop('disposition')
                for row in p['issue_assessments']:row.pop('reason')
                if mode in ('supported_gap','always_empty') or mode=='empty_then_supported' and self.assessments==1:p['gaps']=[deepcopy(GAP)]
                if mode=='always_empty' or mode=='empty_then_supported' and self.assessments==1:
                    p['claims']=[];p['issue_assessments'][0]['status']='INSUFFICIENT'
                if mode=='repeated_bad_ref' or mode=='one_bad_ref' and self.assessments==1:p['claims'][0]['rule']['norms'][0]['source_ref']='invented'
                return wire(p)
            return super().send_once(body=body,ticket=ticket)
    gen,idx=tree;t=Transport(False,False);t.direct_note=False
    profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,
        'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'completion_contract':True,'completion_policy_version':cc.V8,'compact_input':True,'answer_first':True}}
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile=profile,legal_agent_transport=t,memory_identity=lambda _: {'team_id':'test_team','document_ids':['d']})
    app.state.pipeline.term_agent.unit_fulltext=idx
    with TestClient(app) as api:
        body={'question':'모의승인규정 제1조 승인 기준은?','session_id':'boundary','request_id':'first'}
        r=api.post('/v1/rag/ask',json=body)
        if mode in ('always_empty','repeated_bad_ref'):
            assert r.status_code!=200,r.text
            assert t.assessments<=2
        else:
            assert r.status_code==200,r.text
            assert '승인 후 보고한다.' in r.json()['answer']['text']
            calls=len(t.phases);again=api.post('/v1/rag/ask',json=body)
            assert again.status_code==200 and again.json()['answer']==r.json()['answer'] and len(t.phases)==calls
            assert t.assessments==(1 if mode=='supported_gap' else 2)
    events=[]
    for p in tmp_path.rglob('journal.sqlite'):
        with sqlite3.connect(p) as db:events.extend(k for k, in db.execute('SELECT kind FROM event'))
    if mode=='supported_gap':assert 'ASSESSMENT_GAP_REENTRY_PLANNED' not in events and 'ASSESSMENT_RESEARCH_DEFERRED_TO_USER' in events
    if mode=='empty_then_supported':assert 'ASSESSMENT_GAP_REENTRY_PLANNED' in events
    app.state.pipeline.store.close()
