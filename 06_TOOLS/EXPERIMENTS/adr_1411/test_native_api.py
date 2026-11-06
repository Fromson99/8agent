import json
import pytest
from copy import deepcopy
from fastapi.testclient import TestClient
from test_multiturn_structured_scope import tree
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT,wire
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import guided_navigation as guidance


@pytest.mark.parametrize('invalid',[False,True,'entry'])
def test_actual_api_pauses_and_repeats_without_another_generation(tree,tmp_path,invalid):
    gen,idx=tree;question='모의승인규정 제1조 승인 기준을 알려줘.'
    phases=[];views=[]
    class Transport:
        binding=settings()['model_binding']
        target=None
        conflict=False
        def validate_model(self):return {'verified':True,'synthetic':True}
        def send_once(self,*,body,ticket):
            from api_fixture_integrated import decode
            v=decode(json.loads(body['messages'][1]['content'])['view']);phase=v.get('source_stage') or v.get('phase')
            phases.append(phase);views.append(deepcopy(v))
            if phase=='request-entry':
                if invalid=='entry':return wire({'routing':{'mode':'INVALID'}})
                return wire({'routing':{'mode':'CASE','answer':'','reason':'원문 조사'},'command':{'method_id':'CASE_START','source_category':'ALL','facts':[],'queries':['승인 기준'],'format':'prose','reason':'명시 조항'},'intent':{'purpose':'승인 기준 조사','concepts':['승인'],'issues':[{'id':'Q1','question':question,'subject':'승인','kind':'OTHER','request_quote':question}]},'context_quotes':[],'search':{'mode':'FULLTEXT','scope_decision':{'mode':'NAMED_SCOPE','targets':[{'document':'모의승인규정','structure':'제1조','selection':None}],'user_quote':question,'reason':'명시 범위'},'reason':'범위 조회'}})
            if phase=='memory-reason-decision-review':return wire({'decision':'PASS'})
            if phase=='source-request-route':return wire({'mode':'CASE','answer':'','reason':'이전 조사 재개'})
            if phase=='memory-resolve':
                from test_memory_runtime_v2 import command
                return wire(command('RESEARCH_REENTER',target=self.target,stage='SELECT'))
            if phase=='memory-command-check':
                return wire({'valid':True,'reason':'현재 요청 대조',
                    'request_relation':'FOLLOWUP' if self.conflict else 'REVIEW',
                    'requested_task':'보고 의무 조사' if self.conflict else question})
            if phase.startswith('source-law-navigation') or 'read_candidates' in v:
                if invalid:return wire({'choice':'NONEXISTENT_ACTION'})
                def issues(node):
                    if isinstance(node,dict):
                        if 'issue_refs' in node.get('properties',{}):
                            return node['properties']['issue_refs']['items']['enum']
                        for child in node.values():
                            found=issues(child)
                            if found:return found
                    if isinstance(node,list):
                        for child in node:
                            found=issues(child)
                            if found:return found
                refs=issues(body['response_format']['json_schema']['schema'])
                return wire({'choice':'ASK_USER','questions':[{'issue_refs':refs[:1],'kind':'DECISION',
                    'uncertainty':'일반 승인 기준과 긴급 승인 예외 중 먼저 확인할 방향을 정해야 합니다.',
                    'question':'일반 기준부터 볼까요, 긴급 승인 예외부터 볼까요?'}]})
            raise AssertionError('Unexpected extra model phase: '+phase)
    profile=json.loads((ROOT/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile.update(model_binding=Transport.binding,max_read_chars=10000)
    profile['candidate_navigation']['guided_loop']=True
    runtime=tmp_path/'runtime'
    transport=Transport()
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile=profile,legal_agent_transport=transport,runtime_root=runtime,
        memory_identity=lambda _:{'user_id':'synthetic','team_id':'risk_team','document_ids':['d','other']})
    app.state.pipeline.term_agent.unit_fulltext=idx
    request={'session_id':'guided-native','request_id':'g1','question':question}
    with TestClient(app) as api:
        response=api.post('/v1/rag/ask',json=request)
        assert response.status_code==200,response.text
        value=response.json();before=len(phases)
        assert ('다시 시작' if invalid=='entry' else '오류' if invalid else '긴급 승인 예외부터') in value['answer']['text']
        assert 'memory-guided-answer' not in phases
        assert not any('repair' in phase or 'supervisor' in phase for phase in phases)
        again=api.post('/v1/rag/ask',json=request)
        assert again.status_code==200 and again.json()['answer']==value['answer'] and len(phases)==before
        if invalid=='entry':
            assert len(phases)==1
            return
        from semantic_runtime.legal_agent.shortcut_store import selected_store
        from semantic_runtime.legal_agent.journal_storage import connect
        db=connect(selected_store(runtime));selection=json.loads(db.execute("SELECT payload FROM node WHERE stage='SELECT' ORDER BY id DESC LIMIT 1").fetchone()[0]);db.close()
        if invalid:assert selection['stop_reason']=='MODEL_DECISION_UNRESOLVED'
        else:
            assert guidance.waiting(selection)
            db=connect(selected_store(runtime));gid,revision=db.execute('SELECT id,revision FROM goal').fetchone();db.close()
            transport.target=gid
            next_request={**request,'request_id':'g2','question':'일반 기준부터 이어서 확인해줘.'}
            response=api.post('/v1/rag/ask',json=next_request)
            assert response.status_code==200,response.text
            db=connect(selected_store(runtime));after=db.execute('SELECT id,revision FROM goal').fetchone();db.close()
            assert tuple(after)==(gid,revision+1)
            latest=next(v for v in reversed(views) if 'read_candidates' in v)
            history=json.dumps(latest.get('dialogue'),ensure_ascii=False)
            assert question in history and '긴급 승인 예외부터' in history
            assert next_request['question'] in history
            transport.conflict=True;before=len(phases)
            response=api.post('/v1/rag/ask',json={**request,'request_id':'g3','question':'그럼 보고 의무는?'})
            assert response.status_code==200,response.text
            assert '적용하지 않았습니다' in response.json()['answer']['text']
            assert not any('repair' in p for p in phases[before:])
            assert not any('read_candidates' in v for v in views[before:])
            db=connect(selected_store(runtime));unchanged=db.execute('SELECT id,revision FROM goal').fetchone();db.close()
            assert tuple(unchanged)==tuple(after)
