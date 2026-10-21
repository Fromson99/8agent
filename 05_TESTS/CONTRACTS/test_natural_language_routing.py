"""Real API contracts with scripted decisions; no live model/quality experiment."""
from copy import deepcopy
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from semantic_runtime.app import create_app
from semantic_runtime.pipeline import route_question
from semantic_runtime.folder_navigation import request
from semantic_runtime.legal_agent.coordinator import system_request
from semantic_runtime.legal_agent import completion_contracts as cc
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT, wire
from test_structure_first_search import structured_generation
from test_unified_legal_agent import ScriptedTransport, ok


class EntryTransport(ScriptedTransport):
    def __init__(self, mode='DIRECT', *, invalid_first=False, fail=False, invalid_always=False):
        super().__init__()
        self.mode=mode;self.views=[];self.invalid_first=invalid_first;self.reject=fail
        self.invalid_always=invalid_always

    def send_once(self, *, body, ticket):
        view=json.loads(body['messages'][1]['content'])['view']
        phase=view.get('source_stage',view['phase'])
        if phase in ('source-request-route','source-request-route-repair','request-entry','request-entry-repair'):
            self.views.append(deepcopy(view));self.phases.append(phase)
            if self.reject:raise RuntimeError('synthetic routing failure')
            route={'mode':self.mode,'answer':'모의 안내' if self.mode=='DIRECT' else '',
                   'reason':'질문 전체를 받은 모의 의도 판단'}
            if self.mode=='BROWSE':
                route['catalogue']={'browse_view':'documents','document_category':'all','title_query':''}
                if self.invalid_always or self.invalid_first and len(self.views)==1:route['answer']='목록을 모델이 만들어서는 안 됩니다.'
            if phase.startswith('request-entry'):
                return wire({'routing':route,'command':None,'intent':None,'search':None,'context_quotes':[]})
            return wire(route)
        return super().send_once(body=body,ticket=ticket)


def app(tmp_path, generation, transport, fused=False):
    profile={**settings(),'max_model_attempts':40}
    if fused:
        profile.update(request_entry_policy='fused-title-v1',candidate_navigation={
            'mode':'law-first-v1','investigation_control':True,'completion_contract':True,
            'completion_policy_version':cc.V8})
    return create_app(tmp_path,generation,contracts_root=ROOT,provider=object(),
        implementation='legal-agent-unified-v6',legal_agent_profile=profile,
        legal_agent_transport=transport,
        memory_identity=lambda _: {'user_id':'u','team_id':'risk_team','document_ids':['d','other']})


QUESTIONS=[
    '양도차익 산정할 때 양도가액에서 공제되는 경비는 뭐가 있어?',
    '양도차익 산전할때 양도가액에서 공제되는 경비는 뭐가잇어',
    '면제되는 경우는 어떤 게 있어?', '문서 보관 의무에는 어떤 것이 있나요?',
    '내규와 외규의 차이는?', '목록으로 답하지 말고 공제 경비를 설명해 줘',
    '전체 문서 목록 보여줘', '안녕', '그럼 어떤 게 있어?',
]


@pytest.mark.parametrize('question',QUESTIONS)
@pytest.mark.parametrize('fused',[False,True])
def test_every_natural_language_request_reaches_model(tmp_path,structured_generation,question,fused):
    transport=EntryTransport()
    with TestClient(app(tmp_path,structured_generation,transport,fused)) as api:
        result=ok(api.post('/v1/rag/ask',json={'question':question,'session_id':'s','request_id':'r'}))
        assert len(transport.views)==1
        assert transport.views[0]['question']==question
        assert result['answer']['text']=='모의 안내'
        assert result['assembly']['term_agent']['request_routing']['mode']=='DIRECT'
        assert not result['answer']['claims']
    assert request(question) is None and system_request(question) is False


@pytest.mark.parametrize('fused',[False,True])
def test_model_catalogue_preserves_scope_reuse_and_restart(tmp_path,structured_generation,fused):
    transport=EntryTransport('BROWSE')
    body={'question':'지금 읽을 수 있는 자료를 알려줘','document_ids':['d'],'session_id':'s','request_id':'r'}
    for attempt in range(2):
        with TestClient(app(tmp_path,structured_generation,transport,fused)) as api:
            result=ok(api.post('/v1/rag/ask',json=body))
            assert '모의승인규정' in result['answer']['text']
            assert '다른문서' not in result['answer']['text']
            assert result['assembly']['term_agent']['request_routing']['mode']=='BROWSE'
            assert result['question_id'] is None and not result['answer']['claims']
            again=ok(api.post('/v1/rag/ask',json=body))
            assert again['answer']==result['answer']
            assert len(transport.views)==1
    journal=next((tmp_path/'90_RUNTIME/semantic/legal-agent/runs').glob('*/'+result['run_id']+'/journal.sqlite'))
    with sqlite3.connect(journal) as db:
        assert db.execute('SELECT count(*) FROM evidence_unit').fetchone()[0]==0
        assert db.execute("SELECT count(*) FROM event WHERE kind='CATALOGUE_OBSERVED'").fetchone()[0]==1


@pytest.mark.parametrize('fused',[False,True])
def test_catalogue_repair_has_one_owner(tmp_path,structured_generation,fused):
    transport=EntryTransport('BROWSE',invalid_first=True)
    with TestClient(app(tmp_path,structured_generation,transport,fused)) as api:
        result=ok(api.post('/v1/rag/ask',json={'question':'자료를 알려줘','session_id':'s','request_id':'r'}))
        phase='request-entry' if fused else 'source-request-route'
        assert transport.phases==[phase,phase+'-repair']
        assert '모의승인규정' in result['answer']['text']


@pytest.mark.parametrize('fused',[False,True])
def test_routing_failure_is_not_published_as_catalogue(tmp_path,structured_generation,fused):
    transport=EntryTransport(fail=True)
    with TestClient(app(tmp_path,structured_generation,transport,fused)) as api:
        response=api.post('/v1/rag/ask',json={'question':'공제 경비는 뭐가 있어?','session_id':'s','request_id':'r'})
        assert response.status_code>=400
        assert '모의승인규정' not in response.text
        assert transport.views


@pytest.mark.parametrize('fused',[False,True])
def test_repeated_conflict_exhausts_one_repair_without_restarting_budget(tmp_path,structured_generation,fused):
    transport=EntryTransport('BROWSE',invalid_always=True)
    body={'question':'목록을 알려줘','session_id':'s','request_id':'r'}
    for restart in range(2):
        with TestClient(app(tmp_path,structured_generation,transport,fused)) as api:
            response=api.post('/v1/rag/ask',json=body)
            assert response.status_code>=400
            assert '모의승인규정' not in response.text
            assert len(transport.views)==2


def test_management_does_not_parse_raw_chat_when_model_missing(tmp_path):
    from semantic_runtime.ad_mode import handle, ENTER, EXIT
    path=tmp_path/'management.sqlite'
    args=(path, str(tmp_path), 'web', 's')
    assert handle(*args,ENTER,'enter')['ad_mode'] is True
    result=handle(*args,'위키 꺼','change')
    assert result['answer_status']=='error' and 'AD_MODEL_REQUIRED' in result['text']
    assert handle(*args,EXIT,'exit')['ad_mode'] is False


@pytest.mark.parametrize('question',[
    '전문 검색이 뭔가요?', '전문검색 하지 말고 먼저 승인규정을 읽지 마',
    '먼저 승인규정을 읽어줘',
])
def test_legacy_navigation_does_not_infer_mandatory_tool_order(question):
    from semantic_runtime.legal_navigation import request_contract
    contract=request_contract(question,{'d':'승인규정'},['d'])
    assert contract['search_mode'] is None and contract['first_document_id'] is None


def test_content_question_reaches_case_and_originals(tmp_path,structured_generation):
    question='승인 대상에는 뭐가 있어?'
    transport=EntryTransport('CASE');transport.command['task']=question
    with TestClient(app(tmp_path,structured_generation,transport)) as api:
        result=ok(api.post('/v1/rag/ask',json={'question':question,'document_ids':['d'],'session_id':'s','request_id':'r'}))
        assert transport.phases[0]=='source-request-route'
        assert result['question_id'] is not None
        assert result['answer']['claims'] and result['assembly']['context']


@pytest.mark.parametrize('question', ['내규 적용의 예외는?', '외규란 무엇인가?', '내규와 외규 차이는?'])
def test_natural_source_words_are_not_hard_scope_filters(question):
    assert route_question(question)==(question,None)


def test_explicit_source_selector_keeps_exact_remaining_question():
    question='공제 경비는 뭐가 있어?'
    assert route_question('내규: '+question)==(question,'internal')
    assert route_question('외규: 내규 데이터 뭐있냐')==('내규 데이터 뭐있냐','external')


def test_model_modality_is_not_rewritten_but_source_integrity_remains():
    from test_source_span_norm import proposal,accepted
    from semantic_runtime.legal_agent.errors import ContractError
    from semantic_runtime.legal_agent import completion_v5 as v5
    text='요건을 갖춘 경우 신청할 수 있다.'
    result=accepted(proposal(text,'UNSPECIFIED'),[{'id':'S1','source_id':'s','text':text}])
    claim=result['claims'][0]
    assert claim['answer_content']['rule']['norms'][0]['kind']=='UNSPECIFIED'
    assert result['model_proposal']['norm_label_corrections']==[]
    bad=deepcopy(claim);bad['span_receipts'][0]['text']='다른 원문'
    with pytest.raises(ContractError):v5.verify_content(bad)
