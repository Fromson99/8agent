from copy import deepcopy
import pytest
from jsonschema import validate, ValidationError
from semantic_runtime.legal_agent import connection_scope as cs, decision_projection as dp, law_navigation as nav, request_repair as rr, completion_execution as ce, completion_v8 as v8, output_contract as oc
from semantic_runtime.legal_agent.errors import ProposalError
from test_final_connection_selection import setup
from test_answer_progress import fixture as choice_fixture, read_choice
from test_main50_request_repair import GAP

@pytest.mark.parametrize('status',['COMPLETE','PARTIAL','FAILED'])
def test_scope_is_required_before_finish_but_incomplete_lookup_allows_exit(monkeypatch,status):
    inv,data=setup(monkeypatch)
    monkeypatch.setattr(cs,'preview',lambda *a:dict(status=status,groups=[],connection_count=0,absence_proven=False))
    actions={};cs.offer_choices(inv,data,actions)
    assert data['connection_review']['required_before_finish']
    choice=next(s for s,_ in cs.candidates(inv,data) if s['structural_selection'].get('unit_id')=='6')
    cs.accept(inv,choice,data,'원문으로 고른 범위')
    cs.offer_choices(inv,data,{})
    assert not data['connection_review']['required_before_finish']
    assert data['connection_review']['status']==status
    assert not next(c for c in data['connection_scope_choices'] if c['selected'])['connection_preview']['absence_proven']
    assert data['connection_review']['scope_id']==choice['id']
    assert not data['connection_review']['all_targets_required']
    inv.p=deepcopy(inv.p);cs.offer_choices(inv,data,{})
    assert not data['connection_review']['required_before_finish']


def test_both_wire_schemas_remove_premature_finish(monkeypatch):
    inv,data,actions,events,payloads=choice_fixture(monkeypatch,read_choice())
    inv.policy['answer_progress_control']=False
    data['connection_review']={'required_before_finish':True,'status':'SELECT_SCOPE'}
    assert 'FINISH' not in {r['properties']['next_action']['const'] for r in nav.decision_schema(data,actions,set())['anyOf']}
    def capture(session,phase,payload,schema,invoke,expand,**kw):
        assert payload['connection_review']==data['connection_review']
        assert 'FINISH' not in {r['properties']['choice']['const'] for r in schema['anyOf']}
        value=read_choice();value.pop('answer_progress');value['selections'][0]['missing_need']='필수 원문';return value
    monkeypatch.setattr(oc,'bounded_decision',capture)
    assert dp.choose_read(inv,data,actions,'fixture')['next_action']=='READ_ARTICLES'


def test_verified_location_options_exclude_model_opinions_and_keep_links():
    src=[dict(source_id='a',document_id='d',document_name='모의법',heading='제1조',text='실제 원문')]
    ref={'groups':[{'target':dict(source_id='b',document_id='e',document_name='모의시행령',heading='제8조'), 'connections':[{'reference_id':'r'}]}], 'reason':'모의시행령 제99조가 필요함'}
    rows=rr.assessment_locator_options(src,ref);labels=[r['target'] for r in rows]
    assert '모의법 제1조' in labels and '모의시행령 제8조' in labels
    assert not any('99' in t for t in labels)
    assert next(r for r in rows if r['target']=='모의시행령 제8조')['origin']=='STORED_REFERENCE_TARGET'
    assert '모의시행령' in labels


def test_unverified_gap_never_reaches_structure_resolver(monkeypatch):
    calls=[]
    monkeypatch.setattr(rr,'bind_gap',lambda *a:(calls.append(a) or {}))
    value={'gaps':[{**GAP,'missing_target':'모의시행령 제99조'}]}
    for _ in range(2):
        with pytest.raises(ProposalError,match='verified source/reference'):
            rr.bind_gaps(value,None,[],allowed_targets=['','모의시행령 제8조'])
    assert not calls and value['gaps'][0]['missing_target']=='모의시행령 제99조'


def test_unknown_location_keeps_material_gap_without_fabricated_coordinate(monkeypatch):
    monkeypatch.setattr(rr,'bind_gap',lambda g,s:{**g,'target_binding':{'status':'UNLOCATED'},'identity_key':'K','target_binding_hash':'H'})
    value={'gaps':[{**GAP,'missing_target':'','reason':'위임된 비용의 구체적인 구성 원문 필요'}]}
    actual=rr.bind_gaps(value,None,[],allowed_targets=['','모의법 제1조'])
    assert actual['gaps'][0]['material'] and actual['gaps'][0]['missing_target']==''
    assert actual['gaps'][0]['reason']==value['gaps'][0]['reason']


def test_stale_previous_unverified_target_is_not_restored(monkeypatch):
    monkeypatch.setattr(rr,'bind_gap',lambda g,s:{**g,'target_binding':{'status':'UNLOCATED'},'identity_key':'new','target_binding_hash':'H'})
    old={**GAP,'missing_target':'모의법 제99조','gap_key':'old','target_binding_hash':'H','target_binding':{'status':'EXACT'}}
    value={'gaps':[{**GAP,'missing_target':'','previous_gap_key':'old'}]}
    actual=rr.bind_gaps(value,None,[{'gaps':[old]}],allowed_targets=['','모의법 제1조'])
    assert actual['gaps'][0]['missing_target']==''
    assert actual['gaps'][0]['target_binding']['status']=='UNLOCATED'
    assert actual['gaps'][0]['identity_key']=='old'


def test_assessment_target_enum_preserves_unknown_and_fact_gap():
    from semantic_runtime.legal_agent import completion_contracts as cc
    schema=v8.assessment_schema([{'id':'Q1','question':'질문'}],[],[],[],[])
    wire,expand=ce.assessment_projection(schema,allowed_targets=['','모의법 제1조'])
    def nodes(v):
        if isinstance(v,dict):
            if 'missing_target' in v.get('properties',{}):yield v
            for child in v.values():yield from nodes(child)
        elif isinstance(v,list):
            for child in v:yield from nodes(child)
    rows=list(nodes(wire));assert rows
    for row in rows:
        p=row['properties']['missing_target']
        if p.get('const')=='':continue
        assert p['enum']==['','모의법 제1조']
        with pytest.raises(ValidationError):validate('모의법 제99조',p)
        validate('',p)


@pytest.mark.parametrize('mutation',['none','hash','binding','acl','source'])
def test_persisted_connection_locator_receipt_rechecks_identity(mutation):
    from types import SimpleNamespace as S
    from semantic_runtime.contracts import digest
    from semantic_runtime.legal_agent.errors import ContractError
    scope={'members':[]};scope['id']=digest(scope)
    binding={'generation':'one'}
    target=dict(source_id='s',document_id='d',document_name='모의법',heading='제8조')
    receipt=dict(scope_id=scope['id'],binding=digest(binding),targets=[target],status='COMPLETE')
    receipt['sha256']=digest(receipt)
    selected=dict(scope=scope,binding=digest(binding),locator_receipt=receipt)
    session=S(scope=['d'],tools=S(sources={'s':dict(target)}))
    if mutation=='hash':receipt['targets'][0]['heading']='제99조'
    if mutation=='binding':binding={'generation':'two'}
    if mutation=='acl':session.scope=[]
    if mutation=='source':session.tools.sources['s']['heading']='제99조'
    if mutation=='none':
        rows=rr.assessment_locator_options([],{},selected_scope=selected,binding=binding,session=session)
        assert any(r['target']=='모의법 제8조' for r in rows)
    else:
        with pytest.raises(ContractError):rr.assessment_locator_options([],{},selected_scope=selected,binding=binding,session=session)
