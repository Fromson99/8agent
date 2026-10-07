"""Previously reproduced discrepancies and whole reader/state contracts."""
import copy
import json
from pathlib import Path
import pytest
from jsonschema import validate, ValidationError
from test_unit_fulltext_adaptive_read import tree, session, hit
from test_law_grouped_navigation import prepared, decide, reader, cards
from semantic_runtime.legal_agent import law_navigation as ln, law_candidates as lc
from semantic_runtime.legal_agent import unit_relations as rel, unit_reading as ur, unit_selection as us
from semantic_runtime.legal_agent.source_selection import checked_choices
from semantic_runtime.legal_agent.errors import ProposalError
from semantic_runtime.contracts import digest


def investigation(session):
    native,_=session;s=native.sources;rec=prepared(s)
    return ln.Investigation(s,'긴급 승인 예외',rec,reader,60,None,None)


def acquire(inv, defer=False):
    data,actions=inv.view();branch=cards(data)[0]
    value=decide(data,'READ_PARENT',branch['read_parent_action'],branch)
    if defer:value['branch_decisions']=[{'branch_id':branch['id'],'status':'DEFER','reason':'읽고 채택은 보류',
                                       'issue_refs':['Q1'],'basis_refs':[]}]
    inv.validate(value,data,actions);inv.execute(value,data,actions)
    return branch['id']


def test_read_without_automatic_adoption_and_defer_can_read(session):
    inv=investigation(session);gid=acquire(inv,True)
    assert inv.p['selected'][gid]['complete'] and inv.p['groups'][gid]['status']=='DEFERRED'
    assert not inv.active_records()
    data,_=inv.view();assert data['sources'] and any('ADOPT' in r['allowed_decisions'] for r in data['branches'])


def test_acquired_original_has_read_state_until_explicit_adoption(session):
    inv=investigation(session);gid=acquire(inv)
    assert inv.p['groups'][gid]['status']=='READ' and not inv.active_records()
    while True:
        data,actions=inv.view();card=next(c for c in cards(data) if c['id']==gid)
        if not card.get('read_parent_action'):break
        value=decide(data,'READ_PARENT',card['read_parent_action'],card)
        inv.validate(value,data,actions);inv.execute(value,data,actions)
    finish=decide(data)
    inv.validate(finish,data,actions);inv.execute(finish,data,actions)
    assert inv.p['groups'][gid]['status']=='ACTIVE' and inv.active_records()


def test_law_cards_preserve_directory_order_and_nest_originals_once(session):
    inv=investigation(session);data,_=inv.view()
    assert [l['document_id'] for l in data['laws']][:len(inv.p['law_page']['items'])]==[l['document_id'] for l in inv.p['law_page']['items']]
    wire=ln.Investigation.model_view(data)
    assert 'articles' not in wire
    nested=[c for l in wire['laws'] for c in l['articles']]
    assert [c['id'] for c in nested]==[c['id'] for c in cards(data)]
    assert all(c['law_id']==l['id'] for l in wire['laws'] for c in l['articles'])


def test_executed_law_open_is_not_offered_again(session):
    inv=investigation(session);data,actions=inv.view()
    a=next(a for a in actions.values() if a['action']=='OPEN_LAW')
    inv.p['seen_actions'].append(digest({'action':a,'query':inv.p['catalogue']['query_fingerprint']}))
    _,actions=inv.view();assert a['id'] not in actions


def test_search_limit_hides_research_menu(session):
    inv=investigation(session);inv.policy['search_rounds']=len(inv.p['query_history'])
    _,actions=inv.view();assert all(a['action']!='RESEARCH' for a in actions.values())


def test_previously_acquired_extent_is_not_offered_again(session):
    inv=investigation(session);data,actions=inv.view()
    a=next(a for a in actions.values() if a['action']=='READ_SCOPE')
    inv.p['read_choices']=[digest({'action':a,'query':inv.p['catalogue']['query_fingerprint']})]
    _,actions=inv.view();assert a['id'] not in actions


def test_action_and_target_mismatch_rejected_by_wire_schema(session):
    inv=investigation(session);data,actions=inv.view()
    a=next(a for a in actions.values() if a['action']=='OPEN_LAW')
    value=decide(data,'READ_PARENT',a['id'])
    with pytest.raises(ValidationError):validate(value,ln.decision_schema(data,actions,set(inv.p['groups'])))


def test_law_defer_updates_state_and_cannot_read_with_old_reason(session):
    inv=investigation(session);data,actions=inv.view();card=cards(data)[0]
    value=decide(data,'PENDING',branch=card);lid=card['law_id']
    inv.validate(value,data,actions);inv.execute(value,data,actions)
    value=decide(data,'READ_PARENT',card['read_parent_action'],card);value['law_decisions'][0]['status']='DEFER'
    with pytest.raises(ProposalError,match='investigation'):inv.validate(value,data,actions)
    value.update(next_action='PENDING',targets=[]);inv.validate(value,data,actions);inv.execute(value,data,actions)
    assert inv.p['law_reasons'][lid]['status']=='DEFER'
    assert all(g['status']=='DEFERRED' for g in inv.p['groups'].values() if g['law_id']==lid)


def test_finish_cannot_use_only_deferred_original_basis(session):
    inv=investigation(session);gid=acquire(inv)
    data,actions=inv.view();inv.p['groups'][gid]['status']='ACTIVE'
    fake='deferred-branch';inv.p['groups'][fake]={**inv.p['groups'][gid],'id':fake,'status':'DEFERRED'}
    inv.p['selected'][fake]=inv.p['selected'][gid]
    # Complete delivery of the active branch isolates the basis ownership guard.
    inv.p['groups'][gid]['delivery']=len(inv.p['groups'][gid]['page_plan'])
    data,actions=inv.view();data['basis'].append({'id':'old-page','branch_id':fake})
    data['branches'].append({'id':fake,'allowed_decisions':['DEFER']})
    value=decide(data);value['branch_decisions']=[];value['basis_refs']=['old-page']
    with pytest.raises(ProposalError,match='currently adopted'):inv.validate(value,data,actions)


@pytest.mark.parametrize('action,applicability,scopes',[('FOLLOW','DOES_NOT_APPLY',['scope']),('DEFER','APPLIES',[])])
def test_reference_action_applicability_must_match(action,applicability,scopes):
    group={'offers':{'scope':({}, {'block_ids':['1']})},'read_blocks':[],
           'connections':[{'already_read':False,'reading_policy':{'obligation':'OPTIONAL'},'required_block_ids':['1']}]}
    value={'decisions':[{'id':'g','action':action,'scopes':scopes,'reason':'review',
                         'applicability':applicability,'applicability_reason':'review'}],'needs_more':False}
    with pytest.raises(ValidationError):validate(value,rel.schema({'g':group}))
    with pytest.raises(Exception):rel.validate(value,{'g':group})


def test_legacy_choice_requires_status_and_deferral_is_not_selected():
    rows={'choices':[{'id':'U1','scope':'exact:1','reason':'선택하지 않음'}]}
    offered={'U1':{'offers':[{'id':'exact:1'}]}}
    with pytest.raises(ValueError,match='explicit'):us.validate(rows,offered,16)
    rows['choices'][0]['status']='DEFER';us.validate(rows,offered,16)
    assert checked_choices(rows,{'U1'},16)==[]
    rows['choices'][0]['status']='ADOPT';assert checked_choices(rows,{'U1'},16)==['U1']


def test_historical_read_defer_now_valid_before_any_corrective_call(session):
    inv=investigation(session);data,actions=inv.view();card=cards(data)[0]
    value=decide(data,'READ_PARENT',card['read_parent_action'],card)
    value['branch_decisions']=[{'branch_id':card['id'],'status':'DEFER','reason':'읽기 전 채택 보류',
                              'issue_refs':['Q1'],'basis_refs':[]}]
    inv.validate(value,data,actions)
    assert not inv.p['rejected_decisions']


@pytest.mark.parametrize('status', ['ADOPT','DEFER'])
def test_legacy_status_controls_actual_read_and_selected_originals(session,status):
    native,_=session;s=native.sources;rec=prepared(s)
    def invoke(system,data,schema,phase,timeout):
        if phase.startswith('source-reference-'):
            return {'decisions':[],'needs_more':False}
        choices=[]
        if 'triage' in phase:
            row=data['units'][0]
            choices=[{'id':row['id'],'scope':row['read_options'][0][0],'reason':'명시적 상태 판단','status':status}]
        return {'issues':[],'choices':choices,'needs_search':False,'evidence_sufficient':status=='ADOPT','sufficiency_reason':'제시 원문 판단'}
    out=us.select('승인 예외',rec,invoke,session=s,remaining_seconds=60,max_fulltext_chars=80000)
    assert bool(out['final_ids'])==(status=='ADOPT')
    assert (out['status']=='complete')==(status=='ADOPT')


def test_field_replacement_repair_revalidates_active_original_basis_once(session):
    inv=investigation(session);inv.s.profile['max_read_chars']=8000;acquire(inv)
    data,actions=inv.view();valid=decide(data);invalid=copy.deepcopy(valid)
    invalid['branch_decisions'] += copy.deepcopy(invalid['branch_decisions'])
    calls=[]
    def invoke(system,data,schema,phase,timeout):
        calls.append(phase)
        if len(calls)==1:return invalid
        assert data['repair_contract']['response_mode']=='FIELD_REPLACEMENTS'
        return {'branch_decisions':valid['branch_decisions']}
    inv.invoke=invoke
    result=inv.request_decision(data,actions,'source-law-navigation-2')
    assert len(calls)==2 and result==valid and not inv.active_records()


def test_second_bad_decision_remains_bounded_across_resume(session):
    inv=investigation(session);data,actions=inv.view();calls=[]
    def invoke(*args):
        calls.append(args[3]);return {'reason':''}
    inv.invoke=invoke
    with pytest.raises(ValidationError):inv.request_decision(data,actions,'source-law-navigation-1')
    assert len(calls)==2 and inv.p['decision_retry']['attempt']==1 and not inv.p['selected']
    with pytest.raises(ProposalError,match='already attempted'):inv.request_decision(data,actions,'source-law-navigation-1')
    assert len(calls)==2


def test_each_action_union_branch_requires_the_complete_decision(session):
    inv=investigation(session);data,actions=inv.view();schema=ln.decision_schema(data,actions,set(inv.p['groups']))
    for branch in schema['anyOf']:
        assert branch['required']==schema['required']
        assert set(branch['properties'])==set(schema['properties'])
        assert branch['additionalProperties'] is False
    # Exact failure shape from both actual ADR0665 calls remains rejected even
    # when validating ONLY the provider's selected union branch.
    branch=next(b for b in schema['anyOf'] if b['properties']['next_action']['const']=='READ_PARENT')
    partial={'next_action':'READ_PARENT','targets':[next(a['id'] for a in actions.values() if a['action']=='READ_PARENT')], 'evidence_sufficient':False}
    with pytest.raises(ValidationError):validate(partial,branch)


@pytest.mark.parametrize('status', ['ADOPT', 'EXCLUDE'])
def test_branch_grounding_only_permits_own_delivered_original(session,status):
    inv=investigation(session);inv.s.profile['max_read_chars']=8000;gid=acquire(inv)
    data,actions=inv.view();valid=decide(data);value=copy.deepcopy(valid)
    value.update(next_action='PENDING',evidence_sufficient=False,sufficiency_reason='')
    value['branch_decisions'][0]['status']=status
    schema=ln.decision_schema(data,actions,set(inv.p['groups']))
    validate(value,schema)
    assert next(c for c in cards(data) if c['id']==gid)['original_basis_refs']==value['branch_decisions'][0]['basis_refs']
    value['branch_decisions'][0]['basis_refs']=[next(b['id'] for b in data['basis'] if not b.get('branch_id'))]
    with pytest.raises(ValidationError):validate(value,schema)
    data['basis'].append({'id':'another-original','branch_id':'other'})
    value['branch_decisions'][0]['basis_refs']=['another-original']
    with pytest.raises(ValidationError):validate(value,ln.decision_schema(data,actions,set(inv.p['groups'])))


def test_finish_preview_only_is_rejected_at_wire_boundary(session):
    inv=investigation(session);inv.s.profile['max_read_chars']=8000;acquire(inv)
    data,actions=inv.view();value=decide(data);schema=ln.decision_schema(data,actions,set(inv.p['groups']))
    validate(value,schema)
    value['basis_refs']=[next(b['id'] for b in data['basis'] if not b.get('branch_id'))]
    with pytest.raises(ValidationError):validate(value,schema)


def test_selection_explanations_are_bounded_without_truncating_sources(session):
    inv=investigation(session);data,actions=inv.view();a=next(a for a in actions.values() if a['action']=='OPEN_LAW')
    value=decide(data,'OPEN_LAW',a['id']);value['reason']='r'*513
    with pytest.raises(ValidationError):validate(value,ln.decision_schema(data,actions,set(inv.p['groups'])))


def test_reference_alternatives_preserve_all_fields_including_observed_missing_reason():
    offered={'R1':{'offers':{'exact:1':({}, {})}}}
    shape=rel.schema(offered)['properties']['decisions']['items']
    for branch in shape['anyOf']:
        assert set(branch['required'])=={'id','action','scopes','reason','applicability','applicability_reason'}
        assert set(branch['properties'])==set(branch['required'])
        broken={'id':'R1','action':branch['properties']['action']['const'],'scopes':[],
                'applicability':'UNDETERMINED','applicability_reason':'기록된 판단'}
        with pytest.raises(ValidationError):validate(broken,branch)


def test_reference_follow_scope_is_bound_to_its_group_at_wire_boundary():
    offered={k:{'offers':{scope:({}, {'block_ids':[scope]})},'connections':[]} for k,scope in [('R1','exact:1'),('R2','exact:2')]}
    value={'decisions':[{'id':'R1','action':'FOLLOW','scopes':['exact:1'],'reason':'직접 연결 확인',
            'applicability':'APPLIES','applicability_reason':'질문과 관련'},
            {'id':'R2','action':'DEFER','scopes':[],'reason':'판단 보류',
            'applicability':'UNDETERMINED','applicability_reason':'추가 판단 필요'}], 'needs_more':False}
    validate(value,rel.schema(offered));rel.validate(value,offered)
    value['decisions'][0]['scopes']=['exact:2']
    with pytest.raises(ValidationError):validate(value,rel.schema(offered))


def test_external_wire_adapter_preserves_the_original_runtime_schema():
    from semantic_runtime.legal_agent.local_gemma import provider_request
    offered={'R1':{'offers':{'exact:1':({}, {'block_ids':['1']})},'connections':[]}}
    body={'model':'pinned','messages':[{'role':'user','content':'original'}],
          'response_format':{'type':'json_schema','json_schema':{'schema':rel.schema(offered)}}}
    before=copy.deepcopy(body);wire=provider_request(body)
    assert body==before and wire['messages']==body['messages'] and wire['model']==body['model']
    shape=wire['response_format']['json_schema']['schema']
    for branch in shape['properties']['decisions']['items']['anyOf']:
        assert 'uniqueItems' not in branch['properties']['scopes']
        assert len(branch['required'])==6
    # A property named uniqueItems is ordinary product data, not the keyword.
    named={'response_format':{'json_schema':{'schema':{'type':'object','properties':{'uniqueItems':{'type':'string'}}}}}}
    assert provider_request(named)==named


def test_provider_unsupported_duplicate_keyword_remains_enforced_before_read():
    from semantic_runtime.legal_agent.local_gemma import provider_request
    offered={'R1':{'offers':{'exact:1':({}, {'block_ids':['1']})},'connections':[]}}
    shape=rel.schema(offered);wire=provider_request({'response_format':{'json_schema':{'schema':shape}}})
    value={'decisions':[{'id':'R1','action':'FOLLOW','scopes':['exact:1','exact:1'],'reason':'원문 확인',
             'applicability':'APPLIES','applicability_reason':'질문과 관련'}],'needs_more':False}
    validate(value,wire['response_format']['json_schema']['schema'])
    with pytest.raises(ValidationError):validate(value,shape)
    with pytest.raises(Exception,match='scope choice'):rel.validate(value,offered)


def test_real_public_transport_sends_the_adapted_copy(monkeypatch):
    from types import SimpleNamespace
    from semantic_runtime.legal_agent import local_gemma as local
    posted=[];model='qwen/qwen3.8-27b'
    raw={'provider':'Parasail','model':model,'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]}
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,**kwargs):
            posted.append(kwargs['json'])
            return SimpleNamespace(status_code=200,is_success=True,content=b'{}',json=lambda:raw)
    monkeypatch.setattr(local.httpx,'Client',Client)
    transport=local.LocalGemmaTransport.__new__(local.LocalGemmaTransport)
    transport.binding={'model':model};transport._key='synthetic-test-key'
    transport.policy={'endpoint':'https://synthetic.invalid','provider_routing':{'only':['parasail/fp8'],'allow_fallbacks':False},'reasoning':{'effort':'none'}}
    original={'type':'array','uniqueItems':True,'items':{'type':'string'}}
    body={'model':model,'stream':False,'response_format':{'json_schema':{'schema':original}}}
    result=transport.send_once(body=body,ticket={'remaining_seconds':60})
    assert result['status_code']==200 and len(posted)==1
    assert original['uniqueItems'] is True and 'uniqueItems' not in posted[0]['response_format']['json_schema']['schema']
    assert posted[0]['reasoning']=={'effort':'none'} and not posted[0]['provider']['allow_fallbacks']
