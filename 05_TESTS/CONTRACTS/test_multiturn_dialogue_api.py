"""Actual HTTP/store/pipeline boundary with scripted model transport only."""
from copy import deepcopy
import json
import pytest

from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.journal_storage import connect
from semantic_runtime.legal_agent.shortcut_store import selected_store
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT, wire
from test_memory_runtime_v2 import command, fit
from test_multiturn_structured_scope import tree
from test_structure_first_search import structured_generation
from test_natural_language_routing import EntryTransport, app as routing_app

# The request-entry search field asks_definition exists from the definition-priority change on; older
# code rejects it, so scripted entries carry it only when the loaded schema has it.
from semantic_runtime.legal_agent import request_entry as _asks_entry
import json as _asks_json
ASKS_DEFINITION = {'asks_definition': True} if 'asks_definition' in _asks_json.dumps(_asks_entry.schema(model=True)) else {}


def issue_refs(node):
    if isinstance(node,dict):
        if 'issue_refs' in node.get('properties',{}):return node['properties']['issue_refs']['items']['enum']
        for child in node.values():
            found=issue_refs(child)
            if found:return found
    if isinstance(node,list):
        for child in node:
            found=issue_refs(child)
            if found:return found


@pytest.mark.parametrize('prefix',['','전체: '])
def test_real_api_keeps_rejected_turn_then_commits_changed_task_and_wider_scope(tree,tmp_path,prefix):
    gen,idx=tree
    question='모의승인규정 제1조제1항의 승인 기준을 알려줘'
    first=prefix+question
    follow='모의승인규정 제1조 전체 본문을 찾아봐'
    short='확인할 목적을 바꿔줘'
    class Transport:
        binding=settings()['model_binding']
        turn=1;target=None
        def __init__(self):self.views=[];self.phases=[];self.intent_boundary=False
        def validate_model(self):return {'verified':True,'synthetic':True}
        def send_once(self,*,body,ticket):
            from api_fixture_integrated import decode
            v=decode(json.loads(body['messages'][1]['content'])['view'])
            phase=v.get('source_stage') or v['phase'];self.views.append(deepcopy(v));self.phases.append(phase)
            if phase=='request-entry':
                assert v['question']==question
                return wire({'routing':{'mode':'CASE','answer':'','reason':'모의 조사'},
                    'command':{'method_id':'CASE_START','source_category':'ALL','facts':[],
                        'queries':['승인'],'format':'prose','reason':'명시된 항'},
                    'intent':{'purpose':first,'concepts':['승인'],'issues':[{'id':'Q1','question':first,
                        'subject':'승인','kind':'OTHER','request_quote':first}]},'context_quotes':[],
                    'search':{**ASKS_DEFINITION, 'mode':'FULLTEXT','scope_decision':{'mode':'NAMED_SCOPE',
                        'targets':[{'document':'모의승인규정','structure':'제1조제1항','selection':None}],
                        'user_quote':first,'reason':'명시된 항'},'reason':'범위 조회'}})
            if phase=='memory-reason-decision-review':return wire({'decision':'PASS'})
            if phase=='source-request-route':return wire({'mode':'CASE','answer':'','reason':'기존 조사 후속'})
            if phase.startswith('memory-resolve'):
                # The rejected re-entry is repeated in the one guided correction, so the turn is still kept.
                schema=body['response_format']['json_schema']['schema']
                if self.turn==2:return wire(fit(command('RESEARCH_REENTER',target=self.target,stage='SELECT'),schema))
                history=json.dumps(v['recent_dialogue'],ensure_ascii=False)
                assert follow in history and '이어서 확인할까요' in history
                return wire(fit(command('PURPOSE_REVISE',target=self.target,task=follow,
                    search_scope_change={'operation':'REPLACE','targets':[{'document':'모의승인규정',
                        'structure':'제1조','selection':None}],'user_quote':follow}),schema))
            if phase=='memory-command-check':
                return wire({'valid':True,'reason':'모의 현재 목적 대조','request_relation':'FOLLOWUP',
                    'requested_task':follow})
            if self.turn==3 and phase=='memory-intent':
                self.intent_boundary=True
                assert follow in json.dumps(v,ensure_ascii=False)
                raise RuntimeError('intentional stop after applied new task and scope; not a final-answer test')
            if phase.startswith('source-law-navigation') or 'read_candidates' in v:
                return wire({'choice':'ASK_USER','questions':[{'issue_refs':issue_refs(
                    body['response_format']['json_schema']['schema'])[:1],
                    'kind':'SCOPE','uncertainty':'항의 기준과 조 전체의 관계를 더 확인할 수 있습니다.',
                    'question':'조 전체를 이어서 읽어볼까요?'}]})
            raise AssertionError(phase)
    transport=Transport();runtime=tmp_path/'runtime'
    profile=json.loads((ROOT/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile.update(model_binding=transport.binding,max_read_chars=10000)
    actual=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),
        implementation='legal-agent-unified-v6',legal_agent_profile=profile,
        legal_agent_transport=transport,runtime_root=runtime,
        memory_identity=lambda _:{'user_id':'u','team_id':'risk_team','document_ids':['d','other']})
    actual.state.pipeline.term_agent.unit_fulltext=idx
    def goal():
        db=connect(selected_store(runtime))
        row=dict(db.execute('SELECT id,revision,state FROM goal ORDER BY ordinal DESC LIMIT 1').fetchone())
        db.close();row['state']=json.loads(row['state']);return row
    with TestClient(actual) as api:
        request={'session_id':'s','request_id':'1','question':first}
        response=api.post('/v1/rag/ask',json=request)
        assert response.status_code==200,response.text
        before=goal();transport.target=before['id']
        assert before['state']['search_scope']['targets'][0]['unit_id']=='1'
        transport.turn=2
        response=api.post('/v1/rag/ask',json={**request,'request_id':'2','question':follow})
        assert response.status_code==200,response.text
        assert '아직 조사를 시작하지 않았습니다' in response.json()['answer']['text']
        assert goal()==before
        transport.turn=3
        response=api.post('/v1/rag/ask',json={**request,'request_id':'3','question':short})
        assert response.status_code>=400 and transport.intent_boundary,response.text
        after=goal()
        assert after['id']==before['id'] and after['revision']==before['revision']+1
        assert after['state']['task']==follow
        assert after['state']['search_scope']['targets'][0]['unit_id']=='0'
        assert transport.phases[-1]=='memory-intent'


def test_actual_entry_transport_separates_source_marker_and_duplicate_restores_response(tmp_path,structured_generation):
    transport=EntryTransport('DIRECT')
    request={'question':'외규: 어떤 도움을 줄 수 있어?','session_id':'s','request_id':'r'}
    for _ in range(2):
        with TestClient(routing_app(tmp_path,structured_generation,transport,fused=True)) as api:
            response=api.post('/v1/rag/ask',json=request)
            assert response.status_code==200,response.text
            assert response.json()['answer']['text']=='모의 안내'
    assert len(transport.views)==1
    assert transport.views[0]['question']=='어떤 도움을 줄 수 있어?'
    assert transport.views[0]['request_configuration']['source_category']=='external'
