from copy import deepcopy
from types import SimpleNamespace
import pytest
from jsonschema import ValidationError
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import read_judgment as rj, read_judgment_final as final
from semantic_runtime.legal_agent.errors import ContractError, ProposalError

ISSUES=[{'id':'Q1','question':'허용 범위는?'}]


def setup():
    events=[];saved=[]
    inv=SimpleNamespace(p={'binding':'b','selected':{}},policy={'read_judgment':True},question='허용 범위는?')
    raw={}
    inv.s=SimpleNamespace(scope={'d'},repo=SimpleNamespace(event=lambda kind,value:events.append((kind,deepcopy(value)))),
        store=SimpleNamespace(source=lambda did,block: {'text':raw[block]}))
    inv.save=lambda:saved.append(deepcopy(inv.p))
    def page(sid='a',text='연결 원문에서 확인한다.',start=0):
        raw[sid]=text
        inv.p['selected'][sid]={'source_id':sid,'document_id':'d','offer':{}}
        return {'id':'B'+sid,'source_id':sid,'document_id':'d','branch_id':sid,'heading':sid,'text':text[start:],
            'spans':[{'block_id':sid,'start_cp':start,'end_cp':len(text),'text':text[start:]}]}
    data={'issues':ISSUES,'sources':[page()]}
    return inv,data,page,events,saved


def proposal(ctx, *, missing=(), op='SET', use='SUPPORT', others=()):
    rows=[{'judgment_id':r['id'],'operation':op,'use':use,'finding':'' if op in ('KEEP','WITHDRAW') else '조건 확인 필요',
        'reason':'이 원문의 내용과 질문의 적용 범위를 대조했다.','issue_refs':['Q1'],'basis_refs':r['source_refs'],
        'missing':list(missing),'conflicts_with':list(others)} for r in ctx['current_originals']]
    return {'choice':'FINISH','read_review':{'judgments':rows,'need_updates':[],'conflict_updates':[]}}


def commit(inv,data,key,**kw):
    ctx=rj.context(inv,data,key);value=proposal(ctx,**kw)
    rj.record(inv,data,value,key,ctx,{})
    return ctx,value


def test_omitted_old_judgment_and_need_survive_new_bundle():
    inv,data,page,events,saved=setup()
    ctx,value=commit(inv,data,'1',missing=['예외 확인'])
    before=deepcopy(rj.state_for(inv,data)); old=next(iter(before['heads']))
    data['sources']=[page('b','허용 조건 원문')]
    ctx2,value2=commit(inv,data,'2')
    state=rj.state_for(inv,data)
    assert state['heads'][old]==before['heads'][old]
    assert state['needs']==before['needs'] and len(state['heads'])==2
    assert state['receipts']['1']==before['receipts']['1']
    assert ctx2['needs'] and len(events)==2


@pytest.mark.parametrize('op,use', [('SET','CORE'),('KEEP','SUPPORT'),('WITHDRAW','EXCLUDE')])
def test_explicit_revision_retains_previous_versions_and_needs(op,use):
    inv,data,*_=setup();commit(inv,data,'1',missing=['예외 확인'])
    prior=deepcopy(rj.state_for(inv,data));ctx,value=commit(inv,data,'2',op=op,use=use)
    state=rj.state_for(inv,data);change=state['receipts']['2']['changes'][0]
    assert change['previous']==next(iter(prior['heads'].values()))
    assert change['current']['version']==2 and state['needs']==prior['needs']
    assert state['receipts']['1']==prior['receipts']['1']


def test_required_review_missing_does_not_change_previous_state():
    inv,data,page,events,saved=setup();commit(inv,data,'1')
    data['sources']=[page('b')];ctx=rj.context(inv,data,'2');value=proposal(ctx)
    value['read_review']['judgments']=[];before=deepcopy(inv.p)
    with pytest.raises(ProposalError,match='omitted'):rj.record(inv,data,value,'2',ctx,{})
    assert inv.p==before and len(events)==1


@pytest.mark.parametrize('mutation', ['reason','reference','duplicate','keep_change','conflict_unbound','issue'])
def test_invalid_proposal_does_not_clobber_state(mutation):
    inv,data,*_=setup();commit(inv,data,'1')
    ctx=rj.context(inv,data,'2');value=proposal(ctx);row=value['read_review']['judgments'][0]
    if mutation=='reason':row['reason']=' '
    if mutation=='reference':row['basis_refs']=['invented']
    if mutation=='duplicate':value['read_review']['judgments']*=2
    if mutation=='keep_change':row['operation']='KEEP'
    if mutation=='conflict_unbound':row.update(operation='CONFLICT',use='DEFER',conflicts_with=['invented'])
    if mutation=='issue':row['issue_refs']=['Q2']
    before=deepcopy(inv.p)
    with pytest.raises((ProposalError,ValidationError)):rj.record(inv,data,value,'2',ctx,{})
    assert inv.p==before


def test_replay_exact_once_and_changed_replay_rejected():
    inv,data,page,events,saved=setup();ctx,value=commit(inv,data,'1')
    before=deepcopy(inv.p)
    assert rj.context(inv,data,'1')==ctx
    rj.record(inv,data,value,'1',ctx,{})
    assert inv.p==before and len(events)==1
    value['read_review']['judgments'][0]['reason']='다른 이유'
    with pytest.raises(ContractError,match='changed'):rj.record(inv,data,value,'1',ctx,{})


def test_stale_revision_hash_and_acl_are_hard_failures():
    inv,data,*_=setup();stale=rj.context(inv,data,'1');commit(inv,data,'1')
    with pytest.raises(ContractError,match='stale'):rj.record(inv,data,proposal(stale),'2',stale,{})
    ns=rj.state_for(inv,data);ns['heads'][next(iter(ns['heads']))]['reason']='변조'
    with pytest.raises(ContractError,match='hash'):rj.context(inv,data,'3')
    inv,data,*_=setup();data['sources'][0]['document_id']='forbidden'
    with pytest.raises(ContractError,match='authorized'):rj.context(inv,data,'1')


def test_original_bytes_change_cannot_be_recorded():
    inv,data,*_=setup();ctx=rj.context(inv,data,'1');value=proposal(ctx)
    data['sources'][0]['spans'][0]['text']='변조'
    with pytest.raises(ContractError,match='range'):rj.record(inv,data,value,'1',ctx,{})
    assert not inv.p.get('read_judgments')


def test_need_requires_explicit_resolution_and_can_reopen():
    inv,data,*_=setup();commit(inv,data,'1',missing=['예외 확인']);ctx=rj.context(inv,data,'2')
    nid=ctx['needs'][0]['id'];value=proposal(ctx)
    value['read_review']['need_updates']=[{'id':nid,'status':'RESOLVED','reason':'원문 예외 확인','basis_refs':[]}]
    with pytest.raises(ProposalError,match='resolution'):rj.record(inv,data,value,'2',ctx,{})
    value['read_review']['need_updates'][0]['basis_refs']=['Ba']
    rj.record(inv,data,value,'2',ctx,{})
    assert rj.state_for(inv,data)['needs'][nid]['status']=='RESOLVED'
    commit(inv,data,'3',missing=['예외 확인'])
    assert rj.state_for(inv,data)['needs'][nid]['status']=='OPEN'
    ctx=rj.context(inv,data,'4');value=proposal(ctx,missing=['예외 확인'])
    value['read_review']['need_updates']=[{'id':nid,'status':'NOT_NEEDED','reason':'불필요','basis_refs':[]}]
    with pytest.raises(ProposalError,match='reopen and close'):rj.record(inv,data,value,'4',ctx,{})


def conflict_setup():
    inv,data,page,*_=setup();commit(inv,data,'1')
    first=next(iter(rj.state_for(inv,data)['heads']))
    data['sources']=[page('b','다른 적용 조건')]
    commit(inv,data,'2',op='CONFLICT',use='DEFER',others=[first])
    return inv,data,page


def test_conflict_retains_both_original_opinions_after_later_revision():
    inv,data,page=conflict_setup();state=rj.state_for(inv,data)
    conflict=deepcopy(next(iter(state['conflicts'].values())))
    commit(inv,data,'3',use='CORE')
    assert next(iter(rj.state_for(inv,data)['conflicts'].values()))==conflict
    ctx=rj.context(inv,data,'4');value=proposal(ctx)
    value['read_review']['conflict_updates']=[{'id':conflict['id'],'status':'RESOLVED','reason':'한쪽만 읽음','basis_refs':['Bb']}]
    with pytest.raises(ProposalError,match='both sides'):rj.record(inv,data,value,'4',ctx,{})


def options(data):
    return [{'id':s['id'],'source_id':s['source_id'],'document_id':s['document_id'],
        **p,'text_hash':digest(p['text'])} for s in data['sources'] for p in s['spans']]


def final_proposal(ctx, opts):
    return {'claims':[{'claim_id':'K1','evidence_refs':[o['id'] for o in opts]}],final.FIELD:{
        'judgments':[{'id':h['id'],'disposition':'USE' if h['available_evidence_refs'] else 'NOT_USED',
            'reason':'현재 질문과 원문 대조','basis_refs':h['available_evidence_refs'],
            'claim_refs':['K1'] if h['available_evidence_refs'] else []} for h in ctx['judgments']],
        'needs':[{'id':n['id'],'status':'OPEN','material':True,'reason':'예외 조건 미확인','basis_refs':[]} for n in ctx['needs']],
        'conflicts':[{'id':c['id'],'status':'OPEN','material':True,'reason':'충돌 미해결','basis_refs':[]} for c in ctx['conflicts']]}}


@pytest.mark.parametrize('field', ['judgments','needs','conflicts'])
def test_final_review_cannot_omit_retained_entries(field):
    inv,data,page=conflict_setup();commit(inv,data,'3',missing=['예외 확인'])
    opts=options(data);ctx=final.context(inv.p,inv.question,ISSUES,opts,inv.s.scope)
    value=final_proposal(ctx,opts);value[final.FIELD][field]=[]
    with pytest.raises((ProposalError,ValidationError)):final.validate_review(value,ctx,opts)


def test_final_used_judgment_must_bind_actual_claim_and_original():
    inv,data,page=conflict_setup();opts=options(data);ctx=final.context(inv.p,inv.question,ISSUES,opts,inv.s.scope)
    value=final_proposal(ctx,opts);value[final.FIELD]['judgments'][0].update(disposition='USE',claim_refs=['K1'],basis_refs=['Bb'])
    with pytest.raises(ProposalError,match='current original'):final.validate_review(value,ctx,opts)


def test_final_conflict_resolution_requires_both_exact_originals():
    inv,data,page=conflict_setup();opts=options(data);ctx=final.context(inv.p,inv.question,ISSUES,opts,inv.s.scope)
    value=final_proposal(ctx,opts);row=value[final.FIELD]['conflicts'][0]
    row.update(status='RESOLVED',basis_refs=['Bb'])
    with pytest.raises(ProposalError,match='both opinions'):final.validate_review(value,ctx,opts)
    data['sources'].append(page());opts=options(data);ctx=final.context(inv.p,inv.question,ISSUES,opts,inv.s.scope)
    value=final_proposal(ctx,opts);value[final.FIELD]['conflicts'][0].update(status='RESOLVED',basis_refs=['Ba','Bb'])
    final.validate_review(value,ctx,opts)


def test_open_need_survives_final_reentry_without_erasing_previous_opinion():
    inv,data,*_=setup();commit(inv,data,'1',missing=['예외 확인'])
    opts=options(data);ctx=final.context(inv.p,inv.question,ISSUES,opts,inv.s.scope);value=final_proposal(ctx,opts)
    final.validate_review(value,ctx,opts);before=deepcopy(rj.state_for(inv,data))
    result={'disposition':'ANSWER','limitation_items':[]}
    final.retain(result,value,ctx,inv.p,opts);final.retain(result,value,ctx,inv.p,opts)
    assert final.limitations(result) and result['disposition']=='LIMITED_ANSWER'
    after=rj.state_for(inv,data)
    assert after['heads']==before['heads']
    assert next(iter(after['needs'].values()))['status']=='OPEN'
    assert after['final_reviews'][0]['prior_needs']==list(before['needs'].values())
    assert len(after['final_reviews'])==1 and rj.context(inv,data,'2')['previous_final_review']
    assert '예외 조건 미확인' in result['limitations'][0]


def test_unreviewed_acquired_source_is_visible_at_final_budget_handoff():
    inv,data,*_=setup();opts=options(data);ctx=final.context(inv.p,inv.question,ISSUES,opts,inv.s.scope)
    assert ctx['judgments'][0]['version']==0
    result={};final.incomplete(result,ctx)
    assert result[final.FIELD]['status']=='INCOMPLETE' and result[final.FIELD]['prior_judgments']


def test_policy_rejects_competing_automatic_handoff():
    from semantic_runtime.legal_agent.law_candidates import validate_policy
    with pytest.raises(ContractError,match='read judgment'):
        validate_policy({'read_judgment':True,'answer_progress_control':True})


@pytest.mark.parametrize('action', ['READ_ARTICLES','FOLLOW_CONNECTION','FINISH'])
def test_actual_resume_keeps_newer_judgments_before_executing_accepted_action(monkeypatch,action):
    from test_final_connection_selection import setup as navigation_setup
    from semantic_runtime.legal_agent import law_navigation as nav, comparison_research, source_investigation, definition_entry
    from semantic_runtime.basis_links import resolver
    inv,data=navigation_setup(monkeypatch)
    inv.p.update(decisions=[],turn=0,no_progress=2)
    before=deepcopy(inv.p)
    other,original,*_=setup();commit(other,original,'accepted',missing=['남은 조건'])
    ledger=deepcopy(other.p['read_judgments']);inv.p['read_judgments']=ledger
    inv.p['accepted']={'before':before,'decision':{'next_action':action},'data':data,'actions':{},
        'phase':'resume','input_hash':digest(data)}
    inv.control=False;inv.completion=False;inv.left=lambda:100;inv.assessment_handoff=lambda:None
    inv.question='모의 질문'
    for module,name in ((resolver,'acquire'),(comparison_research,'acquire'),
                        (source_investigation,'acquire_preferred'),(definition_entry,'acquire_initial')):
        monkeypatch.setattr(module,name,lambda *a:None)
    class ToolInterrupted(Exception):pass
    def execute(*args):
        assert inv.p['read_judgments']==ledger
        raise ToolInterrupted('synthetic tool interruption after review')
    inv.execute=execute
    with pytest.raises(ToolInterrupted):nav.Investigation.run(inv)
    assert inv.p['read_judgments']==ledger


def test_newly_read_additional_span_requires_review_even_in_same_source():
    inv,data,page,*_=setup();data['sources']=[page(text='앞 문장. 추가 예외.',start=6)];commit(inv,data,'1')
    data['sources']=[page(text='앞 문장. 추가 예외.')]
    assert len(rj.context(inv,data,'2')['required'])==1


def test_final_resolution_updates_reentry_but_preserves_old_status_and_reason():
    inv,data,*_=setup();commit(inv,data,'1',missing=['예외 확인']);opts=options(data)
    ctx=final.context(inv.p,inv.question,ISSUES,opts,inv.s.scope);value=final_proposal(ctx,opts)
    value[final.FIELD]['needs'][0].update(status='RESOLVED',basis_refs=['Ba'],reason='원문에서 조건 확인')
    final.validate_review(value,ctx,opts);result={};final.retain(result,value,ctx,inv.p,opts)
    next_ctx=rj.context(inv,data,'next')
    assert next_ctx['needs'][0]['status']=='RESOLVED'
    assert next_ctx['previous_final_review'][0]['prior_needs'][0]['status']=='OPEN'


def test_claim_namespace_does_not_collide_with_conflict_handle():
    from semantic_runtime.legal_agent.navigation_input import NavigationReferences
    inv,data,*_=conflict_setup();ctx=final.context(inv.p,inv.question,ISSUES,options(data),inv.s.scope)
    refs=NavigationReferences({'read_judgments':ctx})
    assert 'C1' not in refs.reverse


def test_composition_carries_and_checks_review_receipt():
    from semantic_runtime.legal_agent import completion_contracts as cc
    from test_source_span_norm import accepted, proposal as source_proposal
    assessment=accepted(source_proposal(),[{'id':'S1','source_id':'s','text':'신고할 수 있다.'}])
    assessment[final.FIELD]={'status':'REVIEWED','review':{'judgments':[],'needs':[],'conflicts':[]}}
    out=cc.compose(assessment,cc.default_plan(assessment));cc.verify_composition(assessment,out)
    out[final.FIELD]['status']='INCOMPLETE'
    with pytest.raises(ContractError):cc.verify_composition(assessment,out)
