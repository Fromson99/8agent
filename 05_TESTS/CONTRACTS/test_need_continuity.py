"""Regression contracts for declared needs; all model proposals are synthetic."""
from copy import deepcopy
import json

import pytest
from jsonschema import validate, ValidationError
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import investigation_supervisor as su
from semantic_runtime.legal_agent import read_judgment_final as final, need_continuity as nc
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from test_read_judgment import setup, commit, options, ISSUES


def declaration(text='필수 예외 기준 확인'):
    return {'choice':'FINISH', 'answer_progress':{'goals':[{'issue_id':'Q1',
        'status':'NEEDS_SOURCE','answer_so_far':'현재 확인 범위', 'basis_refs':['Ba'],
        'material_need':text,'next_answer_change':'예외 기준 설명','previous_effect':'NO_CHANGE'}]}}


def fixture(*, target=False, complete=True):
    inv,data,*_=setup()
    commit(inv,data,'first')
    su.record(inv,data,declaration(),'d1')
    st=su.state_for(inv,data)
    st['halt']='TERMINATION_SCOPE_REVIEW:BOUNDED_HANDOFF';st['calls']=2
    opts=options(data)
    if target:
        expected=[{k:opts[0][k] for k in ('block_id','start_cp','end_cp')}]
        if not complete:expected.append({'block_id':'unread-child','start_cp':0,'end_cp':10})
        st['source_goals']=[{'goal_id':'SG1','identity':'source-identity','issue_id':'Q1',
            'document_id':'d','document_name':'모의규정','coordinate':'제2조','coordinate_scope':'body',
            'reason':'모델이 선택한 예외 범위','status':'ACQUIRED','arrivals':['a'],'expected':expected}]
    su.save(inv,st)
    ctx=final.context(inv.p,inv.question,ISSUES,opts,inv.s.scope,review_changes=True)
    refs=[o['id'] for o in opts]
    value={'claims':[{'claim_id':'C1','issue_refs':['Q1'],'evidence_refs':refs}], 'gaps':[],
        'issue_assessments':[{'issue_id':'Q1','status':'COVERED','reason':'기준 설명'}],
        final.FIELD:{'judgments':[{'id':h['id'],'disposition':'USE','claim_refs':['C1'],
            'basis_refs':refs,'reason':'현재 근거로 설명'} for h in ctx['judgments']],
            'needs':[{'id':n['id'],'status':'RESOLVED','material':True,'reason':'현재 근거로 필요 충족',
                'basis_refs':refs,'claim_refs':['C1'],'gap_indices':[],
                'target_refs':n.get('target_refs',[]),'scope_quote':''} for n in ctx['needs']], 'conflicts':[]}}
    from scope_review_fixture import scope_rows
    scope_rows(value,ctx,value[final.FIELD])
    return inv,data,ctx,opts,value


def test_need_survives_answerable_and_serialized_resume_without_duplicate():
    inv,data,ctx,opts,value=fixture()
    before=deepcopy(su.state_for(inv,data)['material_needs'])
    next_value=declaration();next_value['answer_progress']['goals'][0].update(
        status='ANSWERABLE',material_need='',next_answer_change='')
    su.record(inv,data,next_value,'d2')
    inv.p=json.loads(json.dumps(inv.p))
    su.record(inv,data,next_value,'d2')
    after=su.state_for(inv,data)
    assert after['material_needs']==before and after['calls']==2
    ctx2=final.context(inv.p,inv.question,ISSUES,opts,inv.s.scope)
    assert ctx2['needs']==ctx['needs']
    assert ctx2['need_continuity']['latest_goals'][0]['status']=='ANSWERABLE'
    assert 'BOUNDED_HANDOFF' in ctx2['need_continuity']['stop_reason']


def test_changed_need_is_additive_not_silent_replacement():
    inv,data,ctx,opts,value=fixture()
    su.record(inv,data,declaration('별도의 위임 기준 확인'),'d2')
    assert len(su.state_for(inv,data)['material_needs'])==2


def test_changed_accepted_proposal_and_tampered_state_rejected():
    inv,data,ctx,opts,value=fixture()
    with pytest.raises(ContractError,match='changed'):su.record(inv,data,declaration('다른 부족'),'d1')
    next(iter(su.state_for(inv,data)['material_needs'].values()))['text']='변조'
    with pytest.raises(ContractError,match='hash'):final.context(inv.p,inv.question,ISSUES,opts,inv.s.scope)


@pytest.mark.parametrize('fault',['omitted','duplicate','fake_id','fake_claim','foreign_issue','no_basis',
    'open_covered','open_no_gap','open_nonmaterial','bad_gap','excluded_no_basis','fake_quote','fake_target'])
def test_disappearing_or_unbound_need_rejected(fault):
    inv,data,ctx,opts,value=fixture()
    row=value[final.FIELD]['needs'][0]
    if fault=='omitted':value[final.FIELD]['needs']=[]
    if fault=='duplicate':value[final.FIELD]['needs']*=2
    if fault=='fake_id':row['id']='fake'
    if fault=='fake_claim':row['claim_refs']=['fake']
    if fault=='foreign_issue':value['claims'][0]['issue_refs']=['Q2']
    if fault=='no_basis':row['basis_refs']=[]
    if fault.startswith('open') or fault=='bad_gap':
        row.update(status='OPEN',claim_refs=[],basis_refs=[],gap_indices=[1])
        value['gaps']=[{'material':True,'issue_id':'Q1'}]
        value['issue_assessments'][0]['status']='PARTIAL'
        if fault=='open_covered':value['issue_assessments'][0]['status']='COVERED'
        if fault=='open_no_gap':value['gaps']=[]
        if fault=='open_nonmaterial':row['material']=False
        if fault=='bad_gap':value['gaps'][0]['issue_id']='Q2'
    if fault=='excluded_no_basis':row.update(status='NOT_NEEDED',claim_refs=[],basis_refs=[])
    if fault=='fake_quote':row.update(status='NOT_NEEDED',claim_refs=[],scope_quote='사용자가 하지 않은 제한')
    if fault=='fake_target':row['target_refs']=['unknown']
    before=deepcopy(inv.p)
    with pytest.raises((ProposalError,ValidationError)):final.validate_review(value,ctx,opts)
    assert inv.p==before


def test_resolved_requires_actual_claim_and_retains_full_chain():
    inv,data,ctx,opts,value=fixture(target=True)
    material=next(r for r in value[final.FIELD]['needs'] if r['id'].startswith('MN'))
    material['target_refs']=[ctx['need_continuity']['targets'][0]['id']]
    final.validate_review(value,ctx,opts)
    result={};final.retain(result,value,ctx,inv.p,opts)
    receipt=result[final.FIELD]
    assert receipt['need_continuity']['targets'][0]['arrivals']==['a']
    assert receipt['prior_needs'][0]['declarations'][0]['decision_key']=='d1'
    assert receipt['review']['needs'][0]['claim_refs']==['C1']
    saved=json.loads(json.dumps(inv.p));again={}
    final.retain(again,value,ctx,saved,opts)
    assert again==result and saved==inv.p


def test_partial_child_originals_cannot_close_selected_target():
    inv,data,ctx,opts,value=fixture(target=True,complete=False)
    assert not ctx['need_continuity']['targets'][0]['available_complete']
    with pytest.raises(ProposalError) as error:final.validate_review(value,ctx,opts)
    assert 'SCOPE_ACQUISITION_INCOMPLETE' in {r['code'] for r in error.value.issues}


@pytest.mark.parametrize('basis',['scope','source'])
def test_explicit_exclusion_is_not_fake_acquisition(basis):
    inv,data,ctx,opts,value=fixture(target=True,complete=False)
    value['claims']=[]
    from need_continuity_fixture import change_review
    for judgment,head in zip(value[final.FIELD]['judgments'],ctx['judgments']):
        judgment.update(disposition='NOT_USED',claim_refs=[],change_review=change_review(head))
    for scope in value[final.FIELD]['scope_reviews']:
        for group in scope['groups']:group.update(disposition='EXCLUDE',claim_refs=[])
    for row in value[final.FIELD]['needs']:
        row.update(status='NOT_NEEDED',claim_refs=[],basis_refs=[] if basis=='scope' else [opts[0]['id']],
            scope_quote=inv.question if basis=='scope' else '')
    final.validate_review(value,ctx,opts)
    result={};final.retain(result,value,ctx,inv.p,opts)
    assert not result[final.FIELD]['need_continuity']['targets'][0]['available_complete']
    assert nc.pending_goals(result,[{'goal_id':'SG1'}])==[]


def test_open_need_keeps_gap_and_limited_answer():
    inv,data,ctx,opts,value=fixture()
    value[final.FIELD]['needs'][0].update(status='OPEN',basis_refs=[],claim_refs=[],gap_indices=[1])
    value['gaps']=[{'material':True,'issue_id':'Q1'}]
    value['issue_assessments'][0]['status']='PARTIAL'
    final.validate_review(value,ctx,opts)
    result={'disposition':'ANSWER','limitation_items':[]};final.retain(result,value,ctx,inv.p,opts)
    assert final.limitations(result)
    assert result['disposition']=='LIMITED_ANSWER' and result['limitations']


def test_stale_final_context_and_cross_request_do_not_merge():
    inv,data,ctx,opts,value=fixture()
    su.record(inv,data,declaration('추가 필요'),'d2')
    with pytest.raises(ContractError,match='stale'):final.retain({},value,ctx,inv.p,opts)
    other=final.context(inv.p,'다른 질문',ISSUES,opts,inv.s.scope)
    assert not other.get('need_continuity') and not other['needs']


def test_incomplete_generation_retains_concrete_need():
    inv,data,ctx,opts,value=fixture()
    result={'disposition':'ANSWER','limitation_items':[]};final.incomplete(result,ctx)
    assert final.limitations(result)
    assert '필수 예외 기준 확인' in ''.join(result['limitations'])


def test_change_review_is_required_on_wire_only_for_applicable_exclusion():
    inv,data,ctx,opts,value=fixture()
    row=value[final.FIELD]['judgments'][0]
    schema=final.review_schema(ctx,opts,enforce_claim_shape=True)
    validate(value[final.FIELD],schema)
    row.update(disposition='NOT_USED',claim_refs=[])
    with pytest.raises(ValidationError):validate(value[final.FIELD],schema)
    head=ctx['judgments'][0]
    row['change_review']={'prior_version':head['change_from']['version'],
        'prior_finding_quote':head['change_from']['finding'],
        'purpose_reviews':[{'purpose_id':p['id'],'source_quote':p['source_quote'],'status':'ROLE_ONLY',
            'basis_refs':head['available_evidence_refs'],'claim_refs':[],'gap_indices':[],
            'reason':'이전 해석은 유지하고 이번 답변의 사용 역할만 제외'} for p in head['review_purposes']]}
    for need in value[final.FIELD]['needs']:
        need.update(status='NOT_NEEDED',claim_refs=[],scope_quote=inv.question)
    validate(value[final.FIELD],schema)
    final.validate_review(value,ctx,opts)


def test_acl_and_range_state_tampering_are_hard_failures():
    inv,data,ctx,opts,value=fixture(target=True)
    with pytest.raises(ContractError,match='authorized'):final.context(inv.p,inv.question,ISSUES,opts,set())
    inv.p['structure_selections']={'fake':{'hash':'fake'}}
    with pytest.raises(ContractError,match='structure hash'):final.context(inv.p,inv.question,ISSUES,opts,inv.s.scope)


@pytest.mark.parametrize('coordinate',['제2조','body:제2조'])
def test_model_target_links_existing_need_without_auto_selecting_sibling(monkeypatch,coordinate):
    from semantic_runtime.legal_agent import source_goal_control as sg, reference_bundles
    inv,data,ctx,opts,value=fixture()
    data['presentation_id']='p2';data['laws']=[{'document_id':'d','name':'모의규정'}]
    inv.policy['reference_bundle_review']=True
    actions={'T1':{'action':'SEARCH_STRUCTURE','identity':{'document_id':'d'}}}
    need_id=ctx['needs'][0]['id']
    proposal={'source_targets':[{'document_ref':'d','coordinate':coordinate,'coordinate_scope':'body',
        'issue_id':'Q1','reason':'앞서 선언한 필요 확인','need_refs':[need_id]}],'source_goal_exclusions':[]}
    monkeypatch.setattr(sg,'refresh',lambda *args:None)
    monkeypatch.setattr(reference_bundles,'expand',lambda *args:pytest.fail('automatic reference selection forbidden'))
    st=su.state_for(inv,data)
    sg.record(proposal,inv,data,actions,st)
    assert len(st['source_goals'])==1 and st['source_goals'][0]['need_refs']==[need_id]
    assert st['source_goals'][0]['coordinate']=='제2조'
    ctx2=final.context(inv.p,inv.question,ISSUES,opts,inv.s.scope)
    assert ctx2['needs'][0]['target_refs']==[ctx2['need_continuity']['targets'][0]['id']]
    proposal['source_targets'][0]['need_refs']=['unknown']
    with pytest.raises(ProposalError,match='known needs'):sg.validate(proposal,inv,data,actions)


@pytest.mark.parametrize('complete',[False,True])
def test_selected_range_requires_each_child_original_at_final_review(complete):
    import sqlite3
    from types import SimpleNamespace as NS
    from semantic_runtime.legal_agent import structure_selection as ss
    from test_model_structure_selection import matcher,choose,single
    inv,data,*_=setup()
    m=matcher();selected=ss.resolve(choose([single(1),single(2)]),m,'d',{'d'})
    inv.p['structure_selections']={selected['hash']:selected}
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE source_block(document_id,block_id,unit_id)')
        db.executemany('INSERT INTO source_block VALUES(?,?,?)',[('d','2','1'),('d','3','2')])
        session=NS(matcher=m,store=NS(db=db,source=lambda did,bid:{'text':'범위 본문'+bid}))
        opts=[{'id':'E'+bid,'source_id':'s'+bid,'document_id':'d','block_id':bid,
            'start_cp':0,'end_cp':len('범위 본문'+bid),'text':'범위 본문'+bid,
            'text_hash':digest('범위 본문'+bid)} for bid in (('2','3') if complete else ('2',))]
        ctx=final.context(inv.p,inv.question,ISSUES,opts,inv.s.scope,session=session)
    target=ctx['need_continuity']['targets'][0]
    assert target['available_complete'] is complete
    refs=[o['id'] for o in opts]
    value={'claims':[{'claim_id':'C1','issue_refs':['Q1'],'evidence_refs':refs}], 'gaps':[],
        'issue_assessments':[{'issue_id':'Q1','status':'COVERED'}],final.FIELD:{
        'judgments':[{'id':h['id'],'disposition':'USE','claim_refs':['C1'],
            'basis_refs':h['available_evidence_refs'],'reason':'각 하위 원문을 검토'} for h in ctx['judgments']],
        'needs':[{'id':ctx['needs'][0]['id'],'status':'RESOLVED','material':True,
            'reason':'선택 범위 전체 설명','basis_refs':refs,'claim_refs':['C1'],
            'gap_indices':[],'target_refs':[target['id']],'scope_quote':''}],'conflicts':[]}}
    from scope_review_fixture import scope_rows
    scope_rows(value,ctx,value[final.FIELD])
    if complete:final.validate_review(value,ctx,opts)
    else:
        with pytest.raises(ProposalError):final.validate_review(value,ctx,opts)


def test_same_issue_claim_cannot_resolve_target_using_uncited_child():
    inv,data,ctx,opts,value=fixture(target=True)
    other={**opts[0],'id':'Eother','block_id':'other'}
    opts.append(other)
    ctx['need_continuity']['scope_input_hash']=digest([ctx['need_continuity']['targets'],opts])
    # Keep a valid claim/judgment, but remove the target original from that claim.
    value['claims'][0]['evidence_refs']=['Eother']
    ctx['judgments'][0]['available_evidence_refs'].append('Eother')
    value[final.FIELD]['judgments'][0]['basis_refs']=[opts[0]['id'],'Eother']
    for row in value[final.FIELD]['needs']:row['basis_refs']=[opts[0]['id'],'Eother']
    with pytest.raises(ProposalError) as error:final.validate_review(value,ctx,opts)
    assert {'NEED_CLAIM_LINK','SCOPE_CLAIM_EVIDENCE','SCOPE_USE_UNSUPPORTED_RANGE'} & {r['code'] for r in error.value.issues}


def test_range_issue_binding_survives_resume_and_cannot_be_reassigned():
    from semantic_runtime.legal_agent import structure_selection as ss
    from test_model_structure_selection import matcher,choose,single
    inv,data,*_=setup()
    data['issues']=[*ISSUES,{'id':'Q2','question':'다른 기준은?'}]
    selected=ss.resolve(choose([single(1)]),matcher(),'d',{'d'})
    inv.p['structure_selections']={selected['hash']:selected}
    nc.bind_structure(inv,data,{'issue_refs':['Q1']},selected)
    inv.p=json.loads(json.dumps(inv.p))
    nc.bind_structure(inv,data,{'issue_refs':['Q1']},selected)
    assert len(inv.p['structure_need_bindings'][selected['hash']])==1
    ctx=final.context(inv.p,inv.question,data['issues'],[],inv.s.scope)
    assert ctx['needs'][0]['issue_refs']==['Q1']
    value={'claims':[],'gaps':[{'issue_id':'Q1','material':True}],
        'issue_assessments':[{'issue_id':'Q1','status':'INSUFFICIENT'},{'issue_id':'Q2','status':'COVERED'}],
        final.FIELD:{'judgments':[],'needs':[{'id':ctx['needs'][0]['id'],'status':'OPEN',
            'material':True,'reason':'선택 범위 미확보','basis_refs':[],'claim_refs':[],
            'target_refs':[],'gap_indices':[1],'scope_quote':''}],'conflicts':[]}}
    from scope_review_fixture import scope_rows
    scope_rows(value,ctx,value[final.FIELD])
    final.validate_review(value,ctx,[])
    inv.p['structure_need_bindings'][selected['hash']][0]['issue_refs']=['Q2']
    with pytest.raises(ContractError,match='issue binding hash'):
        final.context(inv.p,inv.question,data['issues'],[],inv.s.scope)
