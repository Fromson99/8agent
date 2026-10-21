"""Independent actual API consumers of a frozen scope candidate."""
from copy import deepcopy
import json,sqlite3
import pytest
qs=pytest.importorskip('semantic_runtime.legal_agent.query_scope')
from test_multiturn_structured_scope import tree,change
from test_assessment_source_reply import EmptyAssessment
from test_memory_runtime_v2 import command
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT,wire
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.shortcut_store import selected_store
from fastapi.testclient import TestClient

@pytest.mark.parametrize('fused',[True,False])
@pytest.mark.parametrize('replace',[True,False])
def test_scope_survives_actual_ask_correction_and_duplicate(tmp_path,tree,fused,replace):
    question='모의승인규정 제1조제1항에서 승인 예외를 찾아줘.'
    first=change('모의승인규정','제1조제1항',quote=question)
    class Transport(EmptyAssessment):
        def send_once(self,*,body,ticket):
            view=json.loads(body['messages'][1]['content'])['view'];phase=view.get('source_stage',view.get('phase'))
            if phase.startswith('memory-intent'):
                self.phases.append(phase)
                utterance=view['current_request']
                return wire({'purpose':'현재 요청 조사','concepts':['승인'],'background_quotes':[],
                    'issues':[{'id':'Q1','question':utterance,'request_quote':utterance,
                        'subject':'승인','kind':'OTHER'}]})
            if '-read-choice' in phase:
                from semantic_runtime.legal_agent.navigation_input import expand_cards
                expanded=expand_cards(view)
                if not expanded['sources'] and not expanded['read_candidates']:
                    self.phases.append(phase)
                    option=next((o for o in expanded['tool_options'] if o['choice']=='OPEN_LAW'),None)
                    if option:
                        return wire({'choice':'OPEN_LAW','target':option['target'],
                            'issue_id':expanded['issues'][0]['id'],'missing_need':'지정한 범위의 원문 조회',
                            'relation':'DIRECT','source_ref':None})
                    return wire({'choice':'PENDING','reason':'지정 범위에서 현재 검색어의 원문을 확보하지 못함'})
            if phase.startswith('request-entry'):
                self.phases.append(phase)
                return wire({'routing':{'mode':'CASE','answer':'','reason':'지정 범위 조사'},
                    'command':{'method_id':'CASE_START','source_category':'ALL','facts':[],
                        'queries':['승인 예외'],'format':'prose','reason':'조항 지정','search_scope_change':first},
                    'intent':{'purpose':'승인 예외 조사','concepts':['승인'],
                        'issues':[{'id':'Q1','question':'승인 예외는?','subject':'승인','kind':'OTHER','request_quote':question}]},
                    'context_quotes':[],'search':{'mode':'FULLTEXT','title_hint_ids':[],'reason':'범위 안에서 승인 표현 검색'}})
            return super().send_once(body=body,ticket=ticket)
    gen,idx=tree;transport=Transport('repaired')
    transport.command=command('CASE_START',document_scope_mode='AUTHORIZED',task=question,queries=['승인 예외'],facts=[],search_scope_change=first)
    profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,
        'request_entry_policy':'fused-title-v1' if fused else 'legacy',
        'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'completion_contract':True,
            'completion_policy_version':'investigation-completion-v8','compact_input':True,'structure_first':True,
            'selectable_search':True,'answer_first':True,'assessment_reentry_limit':0}}
    runtime=tmp_path/'runtime'
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile=profile,legal_agent_transport=transport,runtime_root=runtime,
        memory_identity=lambda _:{'user_id':'synthetic','team_id':'risk_team','document_ids':['d','other']})
    app.state.pipeline.term_agent.unit_fulltext=idx
    body={'question':question,'session_id':'scoped-api','request_id':'r1'}
    with TestClient(app) as api:
        response=api.post('/v1/rag/ask',json=body)
        assert response.status_code==200,response.text
        one=response.json();gid=one['question_id']
        with sqlite3.connect(selected_store(runtime)) as db:
            before=json.loads(db.execute('SELECT state FROM goal WHERE id=?',(gid,)).fetchone()[0])
        assert before['search_scope']['targets'][0]['unit_id']=='1'
        correction='같은 규정 제1조제2항에서 보고 의무를 찾아줘.' if replace else '못 찾은 승인 예외를 긴급 승인 예외로 고쳐서 다시 찾아줘.'
        transport.command=command('RESEARCH_REPLAN',target=gid,queries=['보고'] if replace else ['긴급 승인 예외'],
            search_scope_change=change(structure='제1조제2항',quote=correction) if replace else change(operation='KEEP'))
        second={**body,'question':correction,'request_id':'r2'}
        response=api.post('/v1/rag/ask',json=second)
        assert response.status_code==200,response.text
        two=response.json();assert two['question_id']==gid and two['revision']==one['revision']+1
        count=len(transport.phases);again=api.post('/v1/rag/ask',json=second)
        assert again.status_code==200 and again.json()['answer']==two['answer']
        assert len(transport.phases)==count
    with sqlite3.connect(selected_store(runtime)) as db:
        after=json.loads(db.execute('SELECT state FROM goal WHERE id=?',(gid,)).fetchone()[0])
        events=[json.loads(r[0]) for r in db.execute('SELECT after_state FROM event WHERE goal=? AND after_state IS NOT NULL',(gid,))]
    assert after['search_scope']['targets'][0]['unit_id']==('5' if replace else '1')
    assert events[0]['search_scope']==before['search_scope']
    journal=next((runtime/'legal-agent/runs').glob('*/'+two['run_id']+'/journal.sqlite'))
    with sqlite3.connect(journal) as db:
        bound=[json.loads(r[0]) for r in db.execute("SELECT payload_json FROM event WHERE kind='DIRECT_SEARCH_SCOPE_BOUND'")]
    assert bound and bound[-1]['scope']==after['search_scope']
