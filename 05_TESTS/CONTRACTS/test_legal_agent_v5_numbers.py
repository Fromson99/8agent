"""Wire/reference invariants, not Gemma quality scores. All transports are mocks."""
import json
from copy import deepcopy
import pytest
from jsonschema import Draft202012Validator, ValidationError
from semantic_runtime.legal_agent.numbered_references import NumberedReferences
from semantic_runtime.legal_agent import obligation_protocol as protocol
from semantic_runtime.legal_agent.errors import ProposalError, ContractError, StaleProposal
from test_legal_agent_v5 import session, SETTINGS, drafted, review, decision, plan, choices
from test_legal_agent_double_harness import generation, wire
from conftest import term_glossary
from test_tool_exploration_v3 import delivered


def sample():
    return {'view_id':'V-private', 'corpus_root':'R1', 'offered_handles':['R1','P7','E-abc'],
        'original_question':'제3조의 1, 2, 3 조건 또는 예외는?',
        'question_pieces':[{'id':'Q1','text':'제3조의 조건은?'}],
        'exact_evidence':[{'source':x,'evidence':x,'focus':x,'breadcrumb':['R1','P7',x],'source_id':'article:private-'+x,
            'text':'제3조: A 또는 B. E-abc라는 원문 표기는 보존.',
            'spans':[{'block_id':str(i+999),'start_cp':0,'end_cp':34}]}
            for i,x in enumerate(['E-abc','E-def','E-ghi'])],
        'question_plan':{'demands':[{'id':'O-secret','question_refs':['Q1'],'requirement':'조건을 설명'}]},
        'answer_obligations':[{'id':'O-secret','claims':['C7'],'evidence_ids':['E-def']}],
        'claims':[{'claim':'C7','text':'A 또는 B','evidence':['E-def'],'question_refs':['Q1'],'obligation_refs':['O-secret']}],
        'continuations':[{'action':{'tool':'read','args':{'target':'P7','extent':'article','cursor':'P-cursor'}}}],
        'relation_menu':[{'relation_id':'REL-private','target_labels':[{'target':'P7'}]}]}


def test_three_sources_display_one_two_three_without_mutating_prose_or_server_view():
    v=sample(); before=deepcopy(v); refs=NumberedReferences(v); shown=refs.view(v)
    assert v==before
    assert [x['source'] for x in shown['exact_evidence']]==[1,2,3]
    assert [x['evidence'] for x in shown['exact_evidence']]==[1,2,3]
    assert shown['question_pieces'][0]['id']==shown['question_plan']['demands'][0]['id']==shown['claims'][0]['claim']==1
    assert shown['answer_obligations'][0]['claims']==[1]
    assert shown['original_question']==v['original_question']
    assert [e['text'] for e in shown['exact_evidence']]==[e['text'] for e in v['exact_evidence']]
    assert shown['exact_evidence'][0]['spans'][0]['end_cp']==34
    assert 'source_id' not in shown['exact_evidence'][0] and 'view_id' not in shown
    assert 'article:private' not in json.dumps(shown)
    assert all(type(e['focus']) is int and all(type(n) is int for n in e['breadcrumb']) for e in shown['exact_evidence'])


@pytest.mark.parametrize('name',['TurnDecision','SourceSelectionDecision','Draft','ReviewDecision','Rebuttal'])
def test_dynamic_schema_is_valid_and_uses_integer_enums(name):
    r=NumberedReferences(sample()); s=r.schema(protocol.schema(name));Draft202012Validator.check_schema(s)
    text=json.dumps(s);assert 'E-abc' not in text and 'O-secret' not in text and 'C7' not in text
    if name=='ReviewDecision':
        p=s['properties'];assert p['checks']['items']['properties']['claim']=={'type':'integer','enum':[1]}
        assert p['obligation_checks']['items']['properties']['obligation']=={'type':'integer','enum':[1]}
        assert p['obligation_checks']['minItems']==p['obligation_checks']['maxItems']==1


@pytest.mark.parametrize('bad',[0,4,-1,True,1.0,'1','E-abc','질문 전체를 여기에 작성',None])
def test_unknown_or_noninteger_source_rejected(bad):
    r=NumberedReferences(sample());schema=r.schema(protocol.schema('SourceSelectionDecision'))
    with pytest.raises(ProposalError):r.decode({'choices':[{'source':bad,'decision':'KEEP_CORE','reason':'관련 근거'}]},schema,'SourceSelectionDecision')


def test_reordered_requests_have_independent_maps_and_receipts():
    a=sample();b=sample();b['exact_evidence'].reverse();b['view_id']='V-next'
    x=NumberedReferences(a);y=NumberedReferences(b)
    response={'choices':[{'source':1,'decision':'KEEP_CORE','reason':'관련 근거'}]}
    assert x.decode(response,x.schema(protocol.schema('SourceSelectionDecision')))['choices'][0]['source']=='E-abc'
    assert y.decode(response,y.schema(protocol.schema('SourceSelectionDecision')))['choices'][0]['source']=='E-ghi'
    b['exact_evidence'].clear()
    assert y.receipt(b)['number_to_id']['sources']==['E-ghi','E-def','E-abc']
    assert x.receipt(a)['view_id']=='V-private'


def test_json_key_sorting_does_not_change_reference_numbers():
    a=sample();b=json.loads(json.dumps(a,sort_keys=True))
    assert NumberedReferences(a).receipt(a)==NumberedReferences(b).receipt(b)


def test_tool_action_cursor_question_and_source_references_roundtrip():
    v=sample();r=NumberedReferences(v);s=r.schema(protocol.schema('TurnDecision'))
    original=decision(plan(),actions=[{'tool':'read','args':{'target':'P7','extent':'article','cursor':'P-cursor'},
        'reason':'예외의 남은 페이지 확인','question_refs':['Q1'],'expected_information':'예외 조건'}])
    original['source_selection']={'choices':[{'source':'E-def','decision':'KEEP_CORE','reason':'관련 근거'}]}
    wire_value=r.project(original)
    assert wire_value['actions'][0]['args']=={'target':2,'extent':'article','cursor':1}
    assert r.decode(wire_value,s,'TurnDecision')==original


def test_partial_operation_validation_is_not_replaced_by_all_or_nothing_validation():
    r=NumberedReferences(sample());s=r.schema(protocol.schema('TurnDecision'))
    value=decision();value['source_selection']={'choices':[{'source':2,'decision':'KEEP_CORE','reason':'유효한 선택'}]}
    value['actions']=[{'tool':'read','args':{'target':2,'extent':'invalid','cursor':None}}]
    decoded=r.decode(value,s,'TurnDecision')
    assert decoded['source_selection']['choices'][0]['source']=='E-def'
    assert decoded['actions'][0]['args']['extent']=='invalid'
    assert decoded['actions'][0]['args']['target']=='P7'
    protocol.validate_wire('TurnDecision',decoded)
    value['actions'][0]['args']['target']=999
    with pytest.raises(ProposalError):r.decode(value,s,'TurnDecision')


def test_invalid_search_action_still_decodes_numbered_references_for_precise_repair():
    r=NumberedReferences(sample());s=r.schema(protocol.schema('TurnDecision'))
    original=decision(plan(),actions=[{'tool':'search','args':{
        'query':'무보증사채 수요예측 모범규준','target':'R1','mode':'title','cursor':None},
        'reason':'문서 제목으로 검색합니다','question_refs':['Q1'],
        'expected_information':'해당 문서의 정확한 제목과 위치를 확인합니다'}])
    wire_value=r.project(original)
    del wire_value['actions'][0]['reason']
    decoded=r.decode(wire_value,s,'TurnDecision')
    assert decoded['actions'][0]['args']['target']=='R1'
    assert decoded['actions'][0]['question_refs']==['Q1']
    with pytest.raises(ValidationError):
        Draft202012Validator(protocol.base.v3.TOOL).validate(decoded['actions'][0])


def test_empty_choices_allow_first_turn_but_never_invent_ids():
    v={'question_pieces':[{'id':'Q1','text':'조건은?'}],'corpus_root':'R1'}
    r=NumberedReferences(v);s=r.schema(protocol.schema('TurnDecision'))
    Draft202012Validator.check_schema(s)
    assert r.decode(r.project(decision(plan())),s,'TurnDecision')==decision(plan())
    value={'choices':[{'source':None,'decision':'KEEP_CORE','reason':'없는 원문'}]}
    with pytest.raises(ProposalError):r.decode(value,r.schema(protocol.schema('SourceSelectionDecision')),'SourceSelectionDecision')


def test_empty_obligations_keep_draft_wire_cardinality_valid():
    view = {'question_pieces': [{'id': 'Q1', 'text': '조건은?'}],
            'corpus_root': 'R1', 'exact_evidence': [{'evidence': 'E1'}]}
    refs = NumberedReferences(view)
    wire_schema = refs.schema(protocol.schema('Draft'))
    choices = wire_schema['properties']['paragraphs']['items']['properties']['obligation_refs']
    assert choices['minItems'] == choices['maxItems'] == 0
    assert protocol.schema('Draft')['properties']['paragraphs']['items']['properties']['obligation_refs']['minItems'] == 1
    with pytest.raises(ProposalError):
        protocol.validate('Draft', {
            'paragraphs': [{'text': '원문에 따른 답변', 'evidence': ['E1'],
                            'question_refs': ['Q1'], 'fact_dependencies': [],
                            'relation_dependencies': [], 'obligation_refs': []}],
            'limitations': []})
    for name in ('TurnDecision', 'SourceSelectionDecision', 'Draft', 'ReviewDecision', 'Rebuttal'):
        for node in walk_schema(refs.schema(protocol.schema(name))):
            if 'minItems' in node and 'maxItems' in node:
                assert node['minItems'] <= node['maxItems'], name


def walk_schema(node):
    if isinstance(node, dict):
        yield node
        for child in node.values():
            yield from walk_schema(child)
    elif isinstance(node, list):
        for child in node:
            yield from walk_schema(child)


def test_generated_review_decodes_into_original_claim_and_obligation_state(tmp_path,generation):
    with session(tmp_path,generation,profile={**SETTINGS,'numbered_references_enabled':True}) as s:
        drafted(s);v,original=review(s)
        refs=NumberedReferences(v); expected=refs.project(original)
        def respond(*,body,ticket):
            shown=json.loads(body['messages'][1]['content'])['view']
            assert shown['claims'][0]['claim']==1
            assert [d['id'] for d in shown['question_plan']['demands']]==[1,2]
            return wire(expected)
        s.gateway.transport.send_once=respond
        decoded=s.gateway.generate('review',v,'ReviewDecision')
        assert decoded==original
        s.commit_review(v,decoded)
        assert [x['status'] for x in s.obligation_status()]==['ANSWERED','MISSING_FACT']
        assert all(x['id'].startswith('O') for x in s.obligation_status())
        assert s.work.heads('claim',current=True)[0]['entity_id'].startswith('C')


def test_invalid_review_is_repaired_using_same_numbered_map_without_state_mutation(tmp_path,generation):
    with session(tmp_path,generation,profile={**SETTINGS,'numbered_references_enabled':True}) as s:
        drafted(s);v,original=review(s);r=NumberedReferences(v);value=r.project(original)
        calls=[]
        def respond(*,body,ticket):
            calls.append(deepcopy(body))
            if len(calls)==1:
                bad=deepcopy(value);bad['obligation_checks'][0]['obligation']='검토할 요구 전체 문장';return wire(bad)
            assert not s.work.heads('obligation_review',current=True)
            assert json.loads(body['messages'][-1]['content'])['valid_claim_ids']==[1]
            assert body['messages'][:2]==calls[0]['messages'][:2]
            return wire(value)
        s.gateway.transport.send_once=respond
        assert s.gateway.generate('review',v,'ReviewDecision')==original
        assert len(calls)==2


def test_request_packing_is_pure_and_v5_defaults_to_numbers(tmp_path,generation):
    with session(tmp_path,generation) as s:
        drafted(s);v,_=review(s)
        a=s.gateway.request('review',v,'ReviewDecision')
        assert json.loads(a['messages'][1]['content'])['view']['claims'][0]['claim']==1
        s.gateway.profile['numbered_references_enabled']=True
        a=s.gateway.request('review',v,'ReviewDecision');b=s.gateway.request('review',v,'ReviewDecision')
        assert a==b and not s.gateway.transport.calls
        assert json.loads(a['messages'][1]['content'])['view']['claims'][0]['claim']==1


def test_projection_receipt_rejects_changed_source_text_and_foreign_mapping(tmp_path,generation):
    with session(tmp_path,generation,profile={**SETTINGS,'numbered_references_enabled':True}) as s:
        drafted(s);v,_=review(s);r=NumberedReferences(v)
        request=s.gateway.request('review',v,'ReviewDecision',references=r)
        payload=json.loads(request['messages'][1]['content'])
        payload['view']['exact_evidence'][0]['text']='모델에 보내기 직전 변조한 원문'
        request['messages'][1]['content']=json.dumps(payload,ensure_ascii=False)
        with pytest.raises(ContractError,match='wire view differs'):
            s.work.reserve_attempt(v,request,'L-tamper',1,'review',numbered_references=r)
        request=s.gateway.request('review',v,'ReviewDecision',references=r)
        r.ids['sources'][0]='E-another-request'
        with pytest.raises(ContractError,match='numbered references differ'):
            s.work.reserve_attempt(v,request,'L-foreign',1,'review',numbered_references=r)


def test_late_numbered_response_still_cannot_mutate_current_state(tmp_path,generation):
    with session(tmp_path,generation,profile={**SETTINGS,'numbered_references_enabled':True}) as s:
        drafted(s);v,original=review(s);value=NumberedReferences(v).project(original)
        def respond(*,body,ticket):
            with s.work.transaction():s.work.event('SYNTHETIC_STATE_CHANGE',{},advance=True)
            return wire(value)
        s.gateway.transport.send_once=respond
        with pytest.raises(StaleProposal):s.gateway.generate('review',v,'ReviewDecision')
        assert not s.work.heads('obligation_review',current=True)
