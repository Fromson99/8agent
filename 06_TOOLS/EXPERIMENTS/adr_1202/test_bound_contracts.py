from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from jsonschema import ValidationError
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import reference_bundles as rb,read_judgment_final as final,requirement_coverage as rc
from semantic_runtime.legal_agent.errors import ContractError,ProposalError
from lawrag.core.legal_coordinate import find_coordinates


def change_review(head):
    def refs(v):return [v] if isinstance(v,str) else (v or [])
    old=head.get('change_from',{'version':0,'finding':''})
    return {'prior_version':old['version'],'prior_finding_quote':old['finding'],
        'purpose_reviews':[{'purpose_id':p['id'],'source_quote':p['source_quote'],'status':'REINTERPRETED',
            'basis_refs':list(dict.fromkeys(refs(head.get('available_evidence_refs',[]))+refs(p.get('origin_evidence_refs',[]))+refs(p.get('target_evidence_refs',[])))),
            'claim_refs':[],'gap_indices':[],'reason':'원래의 예외 확인 목적과 현재 원문을 대조한 결과 적용 범위가 달라 제외한다.'} for p in head['review_purposes']]}


def expansion(text='제21조제2항제3호가목 또는 나목에 따른 기업은 제외한다.'):
    from test_read_judgment import setup
    inv,data,page,*_=setup();data['sources']=[page('a',text)];inv.policy['reference_bundle_review']=True
    coords={('d',str(i)):find_coordinates('제21조제2항제3호'+letter+'목')[0].coordinate for i,letter in enumerate('가나다')}
    inv.s.matcher=NS(stored_coordinates=coords,units={k:{'coordinate_scope':'body'} for k in coords},_unit_sources=lambda did,uid:['target'])
    g={'goal_id':'SG1','identity':digest(['Q1','d','제21조제2항제3호가목','body']),'issue_id':'Q1','document_id':'d','document_name':'합성규정','coordinate':'제21조제2항제3호가목','coordinate_scope':'body','status':'REQUIRED','reason':'정의 확인','routes':[],'arrivals':[]}
    return inv,data,[g]

@pytest.mark.parametrize('join',['또는','및','와',',','·'])
def test_lists_expand_every_member_and_preserve_origin(join):
    inv,d,goals=expansion('제21조제2항제3호가목 '+join+' 나목에 따른 기업은 제외한다.')
    out=rb.expand(inv,d,goals)
    assert len(goals)==2 and len(out)==2
    assert goals[1]['coordinate'].endswith('나목') and goals[0]['reason']=='정의 확인'
    assert all(g['reference_purposes'][0]['source_quote']==d['sources'][0]['text'] for g in goals)
    assert rb.expand(inv,d,goals)==[]


def test_literal_range_enumerates_stored_middle():
    inv,d,goals=expansion('제21조제2항제3호가목부터 다목까지 적용한다.')
    rb.expand(inv,d,goals)
    assert {g['coordinate'][-2:] for g in goals}=={'가목','나목','다목'}

@pytest.mark.parametrize('text',['제21조제2항제3호가목에 따른다. 다른 쟁점은 제21조제2항제3호나목이다.', '「다른규정」 제21조제2항제3호가목 또는 나목이다.'])
def test_unrelated_or_qualified_reference_never_guessed(text):
    inv,d,goals=expansion(text);rb.expand(inv,d,goals);assert len(goals)==1

@pytest.mark.parametrize('fault',['text','acl','branch'])
def test_expansion_verifies_current_original(fault):
    inv,d,goals=expansion()
    if fault=='text':d['sources'][0]['spans'][0]['text']+='변조'
    if fault=='acl':inv.s.scope=set()
    if fault=='branch':d['sources'][0]['branch_id']='unknown'
    with pytest.raises(ContractError):rb.expand(inv,d,goals)


def test_overflow_is_retained_as_unresolved():
    inv,d,goals=expansion();goals.extend({**deepcopy(goals[0]),'goal_id':'SG'+str(i),'identity':str(i),'coordinate':'제99조'} for i in range(2,17))
    out=rb.expand(inv,d,goals);assert len(goals)==16
    assert any(r.get('overflow') and r['status']=='BLOCKED' and r['coordinate'].endswith('나목') for r in out)


def final_case(revised=False):
    from test_read_judgment import setup,commit,options,ISSUES
    inv,d,*_=setup();commit(inv,d,'one')
    if revised:commit(inv,d,'two',op='WITHDRAW',use='EXCLUDE')
    opts=options(d);ctx=final.context(inv.p,inv.question,ISSUES,opts,inv.s.scope,review_changes=True)
    head=ctx['judgments'][0]
    value={'claims':[],'gaps':[],final.FIELD:{'judgments':[{'id':head['id'],'disposition':'NOT_USED','reason':'정의가 아니므로 제외','basis_refs':[],'claim_refs':[]}],'needs':[],'conflicts':[]}}
    return value,ctx,opts,inv

@pytest.mark.parametrize('revised',[False,True])
def test_positive_to_unused_is_detected_even_after_withdrawal(revised):
    v,c,o,_=final_case(revised)
    with pytest.raises(ProposalError) as exc:final.validate_review(v,c,o)
    assert any(e['code']=='FINAL_REVIEW_PURPOSE_CHANGE' for e in exc.value.issues)


def test_legitimate_reinterpretation_has_receipt_without_erasing_prior():
    v,c,o,inv=final_case();v[final.FIELD]['judgments'][0]['change_review']=change_review(c['judgments'][0])
    before=deepcopy(inv.p);final.validate_review(v,c,o);result={};final.retain(result,v,c,inv.p,o)
    assert result[final.FIELD]['prior_judgments'][0]['change_from']['use']=='SUPPORT'
    assert inv.p['read_judgments'][c['request_key']]['heads']==before['read_judgments'][c['request_key']]['heads']

@pytest.mark.parametrize('fault',['version','quote','purpose','reason','basis','claim','gap','unknown'])
def test_changed_opinion_cannot_drop_purpose_or_invent_evidence(fault):
    v,c,o,_=final_case();h=c['judgments'][0];x=change_review(h);v[final.FIELD]['judgments'][0]['change_review']=x;p=x['purpose_reviews'][0]
    if fault=='version':x['prior_version']+=1
    if fault=='quote':x['prior_finding_quote']='다른 의견'
    if fault=='purpose':x['purpose_reviews']=[]
    if fault=='reason':p['reason']=' '
    if fault=='basis':p['basis_refs']=[]
    if fault=='claim':p.update(status='COVERED_ELSEWHERE',claim_refs=['fake'])
    if fault=='gap':p.update(status='UNRESOLVED',gap_indices=[1])
    if fault=='unknown':p['basis_refs']=['fake']
    with pytest.raises((ProposalError,ValidationError)):final.validate_review(v,c,o)


def test_genuinely_unresolved_purpose_keeps_material_gap():
    v,c,o,_=final_case();x=change_review(c['judgments'][0]);v[final.FIELD]['judgments'][0]['change_review']=x
    x['purpose_reviews'][0].update(status='UNRESOLVED',gap_indices=[1],basis_refs=[])
    v['gaps']=[{'material':True,'issue_id':'Q1'}];final.validate_review(v,c,o)
    v['gaps'][0]['material']=False
    with pytest.raises(ProposalError):final.validate_review(v,c,o)


def test_requirement_conflict_retains_claim_gap_and_proposal():
    from test_requirements import fixture
    v,c,o=fixture();v['gaps'].append({**v['gaps'][0],'reason':'추가 원문 미확인'})
    before=deepcopy(v);out,receipt=rc.reconcile_material_gaps(v,c,o)
    assert v==before and out['claims']==v['claims'] and out['gaps']==v['gaps']
    assert out[rc.FIELD][-1]['status']=='UNRESOLVED' and out[rc.FIELD][-1]['gap_indices']==[2]
    assert receipt['original_hash']==digest(v) and receipt['original_proposal']==v
    assert rc.reconcile_material_gaps(out,c,o)==(out,None)

@pytest.mark.parametrize('fault',['claim','gap','ambiguous'])
def test_gap_reconciliation_does_not_bypass_other_failures(fault):
    from test_requirements import fixture
    v,c,o=fixture();v['gaps'].append({**v['gaps'][0]})
    if fault=='claim':v[rc.FIELD][0]['claim_refs']=['C99']
    if fault=='gap':v[rc.FIELD][1]['gap_indices']=[10]
    if fault=='ambiguous':v[rc.FIELD].append({**v[rc.FIELD][1],'request_refs':['R1']})
    with pytest.raises(ProposalError):rc.reconcile_material_gaps(v,c,o)


def test_subrange_coverage_rejects_article_presence_and_wrong_content():
    spans=[{'document_id':'d','block_id':str(i),'start_cp':0,'end_cp':3,'text_hash':digest(str(i))} for i in range(5)]
    assert rb.coverage(spans,spans)['complete']
    assert not rb.coverage(spans,spans[:1])['complete']
    assert not rb.coverage(spans,[{**s,'document_id':'other'} for s in spans])['complete']
    with pytest.raises(ContractError):rb.coverage(spans,[{**s,'text_hash':'bad'} for s in spans])


def test_derived_member_does_not_recursively_activate_other_groups():
    inv,d,goals=expansion('제21조제2항제3호가목 또는 나목이다. 제21조제2항제3호나목 또는 다목은 별도 기준이다.')
    rb.expand(inv,d,goals);assert len(goals)==2
    assert rb.expand(inv,d,goals)==[] and len(goals)==2


@pytest.mark.parametrize('status',['REINTERPRETED','COVERED_ELSEWHERE'])
def test_missing_sibling_body_cannot_be_closed_with_article_root(status):
    v,c,o,_=final_case();h=c['judgments'][0]
    h['review_purposes'][0].update(target_coordinate='제21조제2항제3호나목',target_present=False,target_evidence_refs=[])
    x=change_review(h);v[final.FIELD]['judgments'][0]['change_review']=x
    x['purpose_reviews'][0]['status']=status
    if status=='COVERED_ELSEWHERE':
        v['claims']=[{'claim_id':'C1','issue_refs':['Q1'],'evidence_refs':[o[0]['id']]}];x['purpose_reviews'][0]['claim_refs']=['C1']
    with pytest.raises(ProposalError) as exc:final.validate_review(v,c,o)
    assert any(r['code']=='FINAL_REVIEW_TARGET_RANGE' for r in exc.value.issues)

def test_reconciled_unlocated_gap_enters_existing_research_route():
    from test_requirements import fixture
    from semantic_runtime.legal_agent import completion_execution as ce
    from semantic_runtime.legal_agent.corrected_memory import Reenter
    v,c,o=fixture();v['gaps'].append({**v['gaps'][0],'reason':'별도 기준 원문 확인'})
    v,receipt=rc.reconcile_material_gaps(v,c,o)
    host=NS(s=NS(sources=NS(profile={'candidate_navigation':{'assessment_reentry_limit':2},'selection_time_reserve_seconds':3}),
        work=NS(budget=lambda:{'model_limit':40,'finalization_reserve':3,'model_reserved':5},event=lambda *a:None),context=NS(remaining=lambda:100)),issues=c['issues'],reentry_counters={})
    with pytest.raises(Reenter) as exc:ce.CompletionExecution.finish_assessment(host,v,{'investigation_state':{}},[],o,False,False,set(),{}, {},'test',{},[],'signature')
    assert len(exc.value.payload['gaps'])==2 and all(g['suggested_action']=='RESEARCH' for g in exc.value.payload['gaps'])
