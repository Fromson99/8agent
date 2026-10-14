"""Synthetic native contracts for MAIN50 failures; no legal quality claims."""
from copy import deepcopy
from types import SimpleNamespace as S
import json
import pytest
from jsonschema import validate
from semantic_runtime.legal_agent import request_repair as rr,completion_v5 as v5,completion_contracts as cc
from semantic_runtime.legal_agent import law_navigation as ln,unit_reading as ur,evidence_inventory as inv
from semantic_runtime.legal_agent.errors import ProposalError,ContractError
from test_unit_fulltext_adaptive_read import tree as legacy_tree,session,hit
from lawrag.pipeline.term_generation import build_generation
from lawrag.core.legal_coordinate import find_coordinates
from semantic_runtime.unit_fulltext import build,UnitFulltextIndex
import sqlite3
from test_law_grouped_navigation import prepared,enable
from test_investigation_completion_adr0678 import decision,apply,CompletionTransport
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT,wire
from test_unified_legal_agent import ok


@pytest.fixture
def tree(tmp_path,term_glossary):
    legacy_tree.__wrapped__(tmp_path,term_glossary)
    raw=tmp_path/'raw.sqlite'
    with sqlite3.connect(raw) as db:
        for did,uid,text in db.execute('SELECT document_id,unit_id,json FROM source_unit').fetchall():
            u=json.loads(text)
            if u['family']=='kr_article':
                coordinate=find_coordinates(u['surface'])[0].coordinate
                u.update(legal_coordinate=coordinate.as_dict(),coordinate_scope='body',coordinate_key='body:'+coordinate.canonical_surface())
                db.execute('UPDATE source_unit SET json=? WHERE document_id=? AND unit_id=?',(json.dumps(u,ensure_ascii=False),did,uid))
    build_generation(raw,term_glossary,tmp_path/'bound',serving=True)
    gen=tmp_path/'bound/generation';idx=tmp_path/'bound-index'
    build(gen,gen/'navigation',idx,workers=1)
    return gen,UnitFulltextIndex(idx,json.loads((gen/'navigation/manifest.json').read_text()))


def modern(native, checkpoint=None):
    s=native.sources;record=prepared(s)
    enable(s,investigation_control=True,completion_contract=True,completion_policy_version=cc.V5)
    s.profile['max_read_chars']=10000
    record['unit_reads']=ur.acquire_batch(s,[hit(native,'0')],record['read_state'])
    record['unit_hits']=[hit(native,'0')]
    return ln.Investigation(s,'모의승인규정 제1조 승인 기준',record,None,120,checkpoint,None)

GAP={'issue_id':'Q1','kind':'MISSING_SOURCE','reason':'요청한 규칙 원문 부족','material_id':None,
     'material':True,'missing_target':'모의승인규정 제1조','suggested_action':'READ_SCOPE'}


def test_explicit_epoch_retires_retry_keeps_budget_and_recovery():
    p={'investigation_epoch':3,'no_progress':2,'read_state':{'acquired':7},'reentry_counters':{'CONTRACT_REPAIR':1},
       'decision_retry':{'input_hash':'old','phase':'nav','attempt':1}}
    out=rr.new_epoch(p,reason='ASSESS_GAP_REENTRY')
    assert out['investigation_epoch']==4 and 'decision_retry' not in out
    assert out['no_progress']==2 and out['read_state']==p['read_state'] and out['reentry_counters']==p['reentry_counters']
    assert out['decision_retry_history'][0]['input_hash']=='old' and 'decision_retry' in p
    with pytest.raises(ContractError):rr.new_epoch({**p,'accepted':{'action':'read'}},reason='bad')


def test_exact_duplicates_only_leave_conflicts_for_validation():
    row={'branch_id':'b','status':'ADOPT','basis_refs':['r'],'issue_refs':['Q1'],'reason':'확인'}
    value={'branch_decisions':[row,deepcopy(row),{**row,'status':'EXCLUDE'}]}
    clean,changes=rr.deduplicate_decision(value)
    assert len(changes)==1 and [x['status'] for x in clean['branch_decisions']]==['ADOPT','EXCLUDE']
    assert len(value['branch_decisions'])==3


def test_gap_identity_excludes_optional_material_and_wording_but_preserves_scope(session):
    native,_=session;a=rr.bind_gap(GAP,native.sources)
    b=rr.bind_gap({**GAP,'missing_target':'모의승인규정  제 1 조','reason':'다른 표현','material_id':'optional'},native.sources)
    assert a['target_binding']['status']=='EXACT' and a['identity_key']==b['identity_key']
    assert rr.bind_gap({**GAP,'issue_id':'Q2'},native.sources)['identity_key']!=a['identity_key']
    assert rr.bind_gap({**GAP,'missing_target':'모의승인규정 제2조'},native.sources)['identity_key']!=a['identity_key']
    for target in ['모의승인규정 제1조 부칙','비공개모의 제1조','이름없음 제1조']:
        assert rr.bind_gap({**GAP,'missing_target':target},native.sources)['target_binding']['absence_proven'] is False


def test_exact_absence_and_ambiguous_target_are_different(session):
    native,_=session
    absent=rr.bind_gap({**GAP,'missing_target':'모의승인규정 제99조'},native.sources)
    assert absent['target_binding']['absence_proven'] is True
    unknown=rr.bind_gap({**GAP,'missing_target':'제99조'},native.sources)
    assert unknown['target_binding']['absence_proven'] is False


def test_reentry_retains_request_no_progress_and_exposes_exact_read(session):
    native,_=session;i=modern(native);p=rr.new_epoch(i.p,reason='ASSESS_GAP_REENTRY')
    p['no_progress']=1;p['assessment_gaps']=[rr.bind_gap(GAP,native.sources)]
    again=modern(native,p);data,actions=again.view()
    assert again.p['no_progress']==1 and data['completion_contract']==cc.V5
    assert data['gap_targets'][0]['resolution']=='EXACT'
    assert all(actions[t]['identity']['unit_id']=='0' for t in data['gap_targets'][0]['read_actions'])
    assert data['gap_action_receipts'][0]['action']=='TARGET_STRUCTURE_LOOKUP'


def test_same_presentation_repair_reused_and_changed_presentation_not_retried(session):
    native,_=session;i=modern(native);data,actions=i.view();v=decision(data,'PENDING')
    i.p['decision_retry']={**rr.decision_identity(i.p,data,'phase'),'repaired':v,'attempt':1}
    i.invoke=lambda *args:pytest.fail('retry must not call provider again')
    assert i.request_decision(data,actions,'phase')==v
    with pytest.raises(ContractError,match='presentation'):i.request_decision({**data,'extra':True},actions,'phase')


def test_exact_duplicate_decision_costs_no_repair(session):
    native,_=session;i=modern(native);d,a=i.view();card=d['articles'][0]
    apply(i,decision(d,'READ_PARENT',card['read_parent_action']),d,a)
    d,a=i.view();v=decision(d,'FINISH');assert v['branch_decisions']
    v['branch_decisions'].append(deepcopy(v['branch_decisions'][0]));calls=[]
    i.invoke=lambda *args:(calls.append(args[3]) or deepcopy(v))
    accepted=i.request_decision(d,a,'test-nav')
    assert len(calls)==1 and len(accepted['branch_decisions'])==1


def test_already_delivered_range_is_decided_without_another_read(session):
    native,_=session;i=modern(native);d,a=i.view();card=d['articles'][0]
    apply(i,decision(d,'READ_PARENT',card['read_parent_action']),d,a)
    d,a=i.view()
    assert d['sources'] and d.get('already_presented_reads')
    assert not any(row['action_id'] in a for row in d['already_presented_reads'])
    assert any('ADOPT' in b['allowed_decisions'] for b in d['branches'])
    apply(i,decision(d,'FINISH'),d,a)
    assert inv.originals_for(i.s,i.p) and i.p['groups'][card['id']]['status']=='ACTIVE'


def test_wrong_target_cannot_be_resolved_or_declared_absent(session):
    native,_=session;i=modern(native)
    gap=rr.bind_gap(GAP,i.s);gap.update(gap_id=ln.gap_id(gap),gap_key=cc.gap_key(gap))
    i.p['assessment_gaps']=[gap];i.open_gap_round();d,a=i.view()
    row={'gap_id':gap['gap_id'],'status':'NOT_AVAILABLE','reason':'다른 조문 읽음','action_refs':['wrong'],'basis_refs':[]}
    i.current_gap_round()['action_receipts'].append({'id':'wrong','gap_ids':[gap['gap_id']],'status':'COMPLETED',
        'action':'READ_ARTICLES','outcome':{'target_key':'other','absence_proven':True}})
    with pytest.raises(ProposalError):rr.validate_resolutions(i,{'gap_resolutions':[row]},d)
    row.update(status='RESOLVED',action_refs=[],basis_refs=[])
    with pytest.raises(ProposalError):rr.validate_resolutions(i,{'gap_resolutions':[row]},d)
    row.update(status='UNRESOLVED');rr.validate_resolutions(i,{'gap_resolutions':[row]},d)


def test_same_closed_target_requires_new_target_evidence(session):
    native,_=session;i=modern(native);g=rr.bind_gap(GAP,i.s)
    g.update(gap_id=ln.gap_id(g),gap_key=cc.gap_key(g));i.p['assessment_gaps']=[g];i.open_gap_round()
    i.close_gap_round([{'gap_id':g['gap_id'],'status':'NOT_NEEDED','reason':'조사 판단'}],'FINISH')
    assert not rr.may_reopen(rr.bind_gap({**GAP,'reason':'다시 필요','material_id':'different'},i.s),i.p)


def test_request_quotes_reject_background_only_without_dropping_parenthetical_request():
    question='(검토 배경) 승인 조건과 예외를 설명해줘. (보고 의무도 설명해줘)'
    value={'background_quotes':['검토 배경'],'issues':[{'request_quote':'승인 조건과 예외를 설명해줘.'},
        {'request_quote':'보고 의무도 설명해줘'}]}
    v5.verify_intent(value,question)
    value['issues'].append({'request_quote':'검토 배경'})
    with pytest.raises(ProposalError,match='background-only'):v5.verify_intent(value,question)


def raw_claim(ids=('S1',)):
    leaf=lambda text:{'mode':'LEAF','text':text,'evidence_refs':list(ids)}
    return {'claim_id':'C1','issue_refs':['Q1'],'evidence_refs':list(ids),'conclusion':'허용 요건을 구분합니다.',
        'details':[{'text':'A형과 B형의 적용 대상은 다릅니다.','evidence_refs':list(ids)}],
        'rule':{'kind':'GENERAL_RULE','subject':'신청자','action':'승인','scope':'모의 규정',
            'condition_tree':{'mode':'ALL','children':[leaf('신청'),{'mode':'ANY','children':[leaf('A 자격'),leaf('B 자격')]}]},
            'obligations':[{'text':'승인 후 보고한다.','evidence_refs':list(ids)}],
            'exceptions':[{'target':'신청 요건','text':'긴급 승인 예외','evidence_refs':list(ids)}],'fact_refs':[]}}


def proposal(ids=('S1',)):
    return {'claims':[raw_claim(ids)],'disposition':'ANSWER',
        'issue_assessments':[{'issue_id':'Q1','status':'COVERED','reason':'확인'}],'gaps':[]}


def test_nested_rule_compiles_reachability_and_preserves_all_accepted_content():
    issues=[{'id':'Q1','question':'비교와 요건'}];options=[{'id':'S1','source_id':'s','text':'모의 원문'}]
    schema=v5.assessment_schema(issues,[],options,[])
    accepted,model=v5.prepare(proposal(),schema,issues,options,[])
    a=v5.materialize(accepted,options,issues,model);out=cc.compose(a,cc.default_plan(a))
    cc.verify_composition(a,out);v5.verify_content(out['claims'][0])
    assert not cc.rule_errors(out['claims'][0])
    for fragment in ['A형과 B형','모두 충족','하나 이상 충족','의무: 승인 후 보고한다.','예외 (신청 요건)']:
        assert fragment in out['text']
    assert out['text'].count('허용 요건을 구분합니다.')==1 and '예외 적용 여부는' not in out['text']
    bad=deepcopy(out['claims'][0]);bad['text']=bad['text'].replace('A형과 B형의 적용 대상은 다릅니다.','')
    with pytest.raises(ContractError):v5.verify_content(bad)


def test_coverage_is_derived_from_gap_without_repair_call():
    issues=[{'id':'Q1'}];options=[{'id':'S1'}];raw=proposal();raw['gaps']=[{**GAP,'material':False}]
    accepted,model=v5.prepare(raw,v5.assessment_schema(issues,[],options,[]),issues,options,[])
    assert model['disposition']=='ANSWER' and model['issue_assessments'][0]['status']=='COVERED'
    assert accepted['disposition']=='NEEDS_INVESTIGATION' and accepted['issue_assessments'][0]['status']=='PARTIAL'
    assert accepted['gaps'][0]['material']


def test_unknown_nested_evidence_and_fabricated_user_fact_rejected():
    issues=[{'id':'Q1'}];options=[{'id':'S1'}];facts=[{'id':'U0','text':'일반 승인 기준 질문'}]
    raw=proposal();raw['claims'][0]['rule'].update(kind='CASE_APPLICATION',fact_refs=[{'id':'U0','quote':'승인 받았다'}])
    with pytest.raises(ProposalError):v5.prepare(raw,v5.assessment_schema(issues,[],options,facts),issues,options,facts)


class ModernTransport(CompletionTransport):
    def send_once(self,*,body,ticket):
        v=json.loads(body['messages'][1]['content'])['view'];phase=v.get('source_stage',v['phase'])
        if phase=='memory-intent':
            self.phases.append(phase)
            return wire({'purpose':'승인 기준 확인','concepts':['승인'],'background_quotes':[],
                'issues':[{'id':'Q1','question':'승인 기준은?','request_quote':'승인 기준은?', 'subject':'승인','kind':'OTHER'}]})
        if phase.startswith('memory-assess'):
            self.phases.append(phase)
            assert all('text' not in s for s in v['sources'])
            return wire(proposal([o['id'] for o in v['evidence_options']]))
        return super().send_once(body=body,ticket=ticket)


def test_v5_full_native_publication_and_same_request_reuse(tmp_path,tree):
    from semantic_runtime.app import create_app
    from fastapi.testclient import TestClient
    gen,idx=tree;t=ModernTransport()
    profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,
        'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'completion_contract':True,
                                'completion_policy_version':cc.V5}}
    principal={'user_id':'u','team_id':'t','document_ids':['d']}
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile=profile,legal_agent_transport=t,memory_identity=lambda _:principal)
    app.state.pipeline.term_agent.unit_fulltext=idx
    with TestClient(app) as api:
        body={'question':'모의승인규정 제1조 승인 기준은?','session_id':'v5','request_id':'r1'}
        result=ok(api.post('/v1/rag/ask',json=body));calls=len(t.phases)
        assert result['assembly']['term_agent']['completion_contract']==cc.V5
        assert result['assembly']['term_agent']['accepted_outcome']['answer_coverage']=='COVERED'
        assert 'A형과 B형' in result['answer']['text'] and '승인 후 보고한다.' in result['answer']['text']
        assert len(result['assembly']['term_agent']['case']['judgment_refs'])==7
        again=ok(api.post('/v1/rag/ask',json=body))
        assert again['answer']==result['answer'] and len(t.phases)==calls
        assert not any('compose' in p for p in t.phases)


def test_partial_coordinate_index_cannot_prove_absence(session):
    native,_=session;m=native.sources.matcher
    key=next(k for k,u in m.units.items() if k[0]=='d' and u.get('family')=='kr_article')
    old=m.units[key];m.units={**m.units,key:{**old,'coordinate_scope':None}}
    target=rr.bind_gap({**GAP,'missing_target':'모의승인규정 제99조'},native.sources)
    assert target['target_binding']['absence_proven'] is False


def test_memory_peak_is_observed_within_request_not_final_rss(monkeypatch):
    from semantic_runtime import execution_metrics as em
    values=iter([100,700,200,150]);monkeypatch.setattr(em,'resident_bytes',lambda:next(values))
    m=em.Metrics();m.sample_memory();m.sample_memory();v=m.snapshot()['memory']
    assert v['start_bytes']==100 and v['peak_observed_bytes']==700 and v['latest_bytes']==150
    assert v['exclusive_request_allocation'] is False


def test_resolved_gap_accepts_previously_adopted_exact_span_without_fake_read(session):
    native,_=session;i=modern(native);d,a=i.view();card=d['articles'][0]
    apply(i,decision(d,'READ_PARENT',card['read_parent_action']),d,a)
    d,a=i.view();apply(i,decision(d,'FINISH'),d,a)
    g=rr.bind_gap(GAP,i.s);g.update(gap_id=ln.gap_id(g),gap_key=cc.gap_key(g))
    i.p['assessment_gaps']=[g];i.open_gap_round();d,a=i.view()
    refs=list(i.adopted_basis())
    rr.validate_resolutions(i,{'gap_resolutions':[{'gap_id':g['gap_id'],'status':'RESOLVED',
        'basis_refs':refs,'action_refs':[],'reason':'현재 요청에 이미 전달·채택한 해당 조문 전체'}]},d)
    i.p['basis_history'][refs[0]]['spans']=[]
    with pytest.raises(ProposalError):rr.validate_resolutions(i,{'gap_resolutions':[{'gap_id':g['gap_id'],
        'status':'RESOLVED','basis_refs':refs,'action_refs':[],'reason':'손상된 근거'}]},d)


def test_fused_entry_has_one_background_source_and_quote_provenance():
    from semantic_runtime.legal_agent import request_entry as e
    schema=e.schema(scoped=True)
    intent=schema['properties']['intent']['anyOf'][0]
    assert 'background_quotes' not in intent['properties']
    assert 'request_quote' in intent['properties']['issues']['items']['required']
    # The public v4 input contract remains unchanged.
    assert 'request_quote' not in e.schema()['properties']['intent']['anyOf'][0]['properties']['issues']['items']['properties']


class ReentryTransport(ModernTransport):
    def send_once(self,*,body,ticket):
        v=json.loads(body['messages'][1]['content'])['view'];phase=v.get('source_stage',v['phase'])
        if phase.startswith('memory-assess'):
            self.phases.append(phase);out=proposal([o['id'] for o in v['evidence_options']])
            if not v['gap_history']:out['gaps']=[deepcopy(GAP)]
            return wire(out)
        if phase.startswith('source-law-navigation-') and v.get('assessment_gaps'):
            self.phases.append(phase);out=decision(v,'FINISH');out['branch_decisions']=[]
            gap=v['assessment_gaps'][0]
            out['gap_resolutions']=[{'gap_id':gap['gap_id'],'status':'RESOLVED','reason':'이미 채택한 정확한 조문 원문',
                'basis_refs':[b['id'] for b in v['basis'] if b.get('branch_id')],'action_refs':[]}]
            return wire(out)
        return super().send_once(body=body,ticket=ticket)


def test_native_assessment_reentry_compiles_gap_and_finishes_same_request(tmp_path,tree):
    from semantic_runtime.app import create_app
    from fastapi.testclient import TestClient
    gen,idx=tree;t=ReentryTransport()
    profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,
        'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'completion_contract':True,
                                'completion_policy_version':cc.V5}}
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile=profile,legal_agent_transport=t,
        memory_identity=lambda _:{'user_id':'u','team_id':'t','document_ids':['d']})
    app.state.pipeline.term_agent.unit_fulltext=idx
    with TestClient(app) as api:
        result=ok(api.post('/v1/rag/ask',json={'question':'모의승인규정 제1조 승인 기준은?',
            'session_id':'reentry','request_id':'r'}))
    assert t.phases.count('memory-assess')==2 and not any('repair' in p for p in t.phases)
    assert result['assembly']['term_agent']['accepted_outcome']['answer_coverage']=='COVERED'
    assert result['executed'].count('SELECT')==2



def test_interrupted_corrective_transport_resumes_original_view_without_third_call(session):
    native,_=session;i=modern(native);calls=[]
    def invoke(system,data,schema,phase,timeout):
        calls.append(phase)
        if len(calls)==1:return {'presentation_id':'stale-invalid'}
        raise RuntimeError('synthetic interruption during corrective transport')
    i.invoke=invoke
    with pytest.raises(RuntimeError,match='synthetic interruption'):i.run()
    retry=deepcopy(i.p['decision_retry']);assert len(calls)==2
    assert retry['input_hash']!=__import__('semantic_runtime.contracts',fromlist=['digest']).digest(i.view()[0])
    reopened=modern(native,deepcopy(i.p))
    reopened.invoke=lambda *args:pytest.fail('unknown corrective outcome must not trigger a third attempt')
    reopened.bounded_result=lambda reason:{'bounded':reason}
    assert reopened.run()=={'bounded':'MODEL_DECISION_UNRESOLVED'}
    assert reopened.p['decision_retry']['input_hash']==retry['input_hash']


def test_retry_menu_tamper_is_rejected_before_execution(session):
    native,_=session;i=modern(native);d,a=i.view()
    i.p['decision_retry']={**rr.decision_identity(i.p,d,'test'), 'data':d,'actions':a,'actions_hash':'changed','attempt':1}
    with pytest.raises(ContractError,match='snapshot'):i.run()


def test_new_user_request_preserves_old_gap_audit_but_can_reconsider(session):
    native,_=session;i=modern(native);g=rr.bind_gap(GAP,i.s);g.update(gap_id=ln.gap_id(g),gap_key=cc.gap_key(g))
    i.p['assessment_gaps']=[g];i.open_gap_round();i.close_gap_round([],'previous request stop')
    assert not rr.may_reopen(g,i.p)
    i.s.investigation_prior_route=True
    try:again=modern(native,deepcopy(i.p))
    finally:i.s.investigation_prior_route=False
    assert again.p['prior_request_gap_rounds'] and not again.p.get('gap_rounds')
    assert rr.may_reopen(g,again.p) and again.p['investigation_epoch']==1 and again.p['no_progress']==0



def test_unknown_coordinate_keeps_scoped_tools_and_unresolved_status(session):
    native,_=session;i=modern(native)
    g=rr.bind_gap({**GAP,'missing_target':'모의승인규정의 알 수 없는 조건'},i.s)
    g.update(gap_id=ln.gap_id(g),gap_key=cc.gap_key(g));i.p['assessment_gaps']=[g];i.open_gap_round()
    d,a=i.view();target=d['gap_targets'][0]
    assert g['target_binding']['document_candidates']==['d']
    assert not g['target_binding']['absence_proven']
    assert {a[t]['action'] for t in target['navigation_actions']}=={'SEARCH_STRUCTURE','OPEN_STRUCTURE','SEARCH_BODY'}
    assert all(a[t]['identity']['document_id']=='d' for t in target['navigation_actions'])
    assert 'UNRESOLVED' in d['gap_rule']


def test_current_saved_view_is_suppressed_but_missing_body_can_be_represented(session):
    native,_=session;i=modern(native);d,a=i.view();card=d['articles'][0]
    apply(i,decision(d,'READ_PARENT',card['read_parent_action']),d,a);d,a=i.view()
    assert any(x['action_id'] for x in d['already_presented_reads'])
    assert not any(x['action']=='VIEW_SAVED_SOURCE' and x['identity']['branch_id']==card['id'] for x in a.values())
    # The menu must not discard a saved source when it is absent from this input.
    action={'id':'saved','action':'VIEW_SAVED_SOURCE','identity':{'branch_id':card['id']},'label':'saved'}
    view={'sources':[]};actions={'saved':action};rr.annotate_reused_reads(i,view,actions)
    assert 'saved' in actions


def test_native_transient_read_failure_offers_different_route_without_false_adoption(session):
    native,_=session;i=modern(native);original=i.execute_tool;calls=[];failed=[]
    def execute(v,d,a):
        if v['next_action']=='READ_PARENT':
            failed.append(v['targets'][0]);raise TimeoutError('synthetic source read timeout')
        return original(v,d,a)
    def invoke(system,d,schema,phase,timeout):
        calls.append(phase)
        if len(calls)==1:return decision(d,'READ_PARENT',next(a['id'] for a in d['actions'] if a['action']=='READ_PARENT'))
        assert d['tool_recovery'][0]['code']=='SOURCE_TEMPORARILY_UNAVAILABLE'
        assert not d['tool_recovery'][0]['absence_proven']
        assert failed[0] not in {a['id'] for a in d['actions']}
        assert any(a['action']=='SEARCH_STRUCTURE' for a in d['actions'])
        return decision(d,'PENDING')
    i.execute_tool=execute;i.invoke=invoke;i.bounded_result=lambda reason:{'bounded':reason}
    assert i.run()=={'bounded':'MODEL_PENDING'}
    assert len(calls)==2 and not inv.originals_for(i.s,i.p)
    assert i.p['tool_failures'][0]['status']=='UNRESOLVED'
    assert not i.p.get('accepted')


def test_exact_failed_search_is_blocked_but_new_expression_can_execute(session):
    native,_=session;i=modern(native);d,a=i.view()
    target=next(t for t,v in a.items() if v['action']=='SEARCH_STRUCTURE')
    v=decision(d,'SEARCH_STRUCTURE',target);v['queries']=['제1조']
    i.p['tool_failures']=[{'operation_key':rr.operation_key(v,a)}]
    with pytest.raises(ProposalError,match='same failed'):rr.validate_failed_operation(i,v,a)
    rr.validate_failed_operation(i,{**v,'queries':['제2조']},a)


@pytest.mark.parametrize('error',[ContractError('source hash'),PermissionError('ACL'),ValueError('unexpected bug')])
def test_integrity_permission_and_unclassified_tool_errors_still_fail_closed(session,error):
    native,_=session;i=modern(native);d,a=i.view();v=decision(d,'READ_PARENT',d['articles'][0]['read_parent_action'])
    def fail(*args):raise error
    i.execute_tool=fail
    with pytest.raises(type(error)):i.execute(v,d,a)
    assert not i.p.get('tool_failures')


def test_wrapped_integrity_and_unknown_model_outcomes_are_not_source_recovery():
    from semantic_runtime.legal_agent.errors import ToolExecutionError,TransportError,DeadlineExceeded
    for cause in [ContractError('hash'),TransportError('unknown',unknown=True),DeadlineExceeded('limit')]:
        outer=ToolExecutionError('wrapped');outer.__cause__=cause
        assert rr.recoverable_tool_failure(outer) is None
    outer=ToolExecutionError('wrapped');outer.__cause__=TimeoutError('source')
    assert rr.recoverable_tool_failure(outer)=='SOURCE_TEMPORARILY_UNAVAILABLE'


def test_failed_tool_receipt_never_satisfies_missing_target(session):
    native,_=session;i=modern(native);g=rr.bind_gap(GAP,i.s);g.update(gap_id=ln.gap_id(g),gap_key=cc.gap_key(g))
    i.p['assessment_gaps']=[g];i.open_gap_round();d,a=i.view();t=d['gap_targets'][0]['read_actions'][0]
    v=decision(d,'READ_ARTICLES',t)
    def fail(*args):raise TimeoutError('source timeout')
    i.execute_tool=fail;assert i.execute(v,d,a) is False
    receipt=i.current_gap_round()['action_receipts'][-1];assert receipt['status']=='FAILED'
    row={'gap_id':g['gap_id'],'status':'NOT_AVAILABLE','reason':'failed source call','action_refs':[receipt['id']],'basis_refs':[]}
    with pytest.raises(ProposalError):rr.validate_resolutions(i,{'gap_resolutions':[row]},d)


def test_fresh_user_request_retires_tool_failure_only_at_new_request_boundary(session):
    native,_=session;i=modern(native);i.p['tool_failures']=[{'code':'SOURCE_TEMPORARILY_UNAVAILABLE','operation_key':'x'}]
    same=modern(native,rr.new_epoch(i.p,reason='ASSESS_GAP_REENTRY'))
    assert same.p['tool_failures']==i.p['tool_failures']
    i.s.investigation_prior_route=True
    try:fresh=modern(native,deepcopy(i.p))
    finally:i.s.investigation_prior_route=False
    assert not fresh.p.get('tool_failures') and fresh.p['prior_tool_failures']


def test_structure_miss_returns_typed_available_recovery_without_forced_fulltext(session):
    native,_=session;i=modern(native);d,a=i.view()
    from semantic_runtime.legal_agent import structure_query as sq
    i.p['structure_page']['failure']=sq.failure('MISSING_COORDINATE')
    rr.recovery_menu(i,d,a)
    assert d['lookup_recovery']['failure_code']=='MISSING_COORDINATE'
    assert not d['lookup_recovery']['automatic_fulltext_fallback']
    assert d['lookup_recovery']['action_ids'] and all(t in a for t in d['lookup_recovery']['action_ids'])



def test_exact_gap_outside_current_catalogue_executes_original_read(session):
    native, _ = session
    investigation = modern(native)
    gap = rr.bind_gap(GAP, investigation.s)
    gap.update(gap_id=ln.gap_id(gap), gap_key=cc.gap_key(gap))
    investigation.p.update(laws={}, groups={}, selected={}, direct_laws=[], window_groups=[])
    investigation.p['law_page']['items'] = []
    investigation.p['structure_page']['items'] = []
    investigation.p['assessment_gaps'] = [gap]
    investigation.open_gap_round()
    data, actions = investigation.view()
    target = data['gap_targets'][0]['read_actions'][0]
    value = decision(data, 'READ_ARTICLES', target)
    investigation.validate(value, data, actions)
    investigation.execute(value, data, actions)
    assert investigation.p['selected']
    assert not inv.originals_for(investigation.s, investigation.p)


def test_accepted_batch_resume_keeps_completed_target_receipts(session, monkeypatch):
    native, _ = session
    investigation = modern(native)
    gap = rr.bind_gap(GAP, investigation.s)
    gap.update(gap_id=ln.gap_id(gap), gap_key=cc.gap_key(gap))
    investigation.p['assessment_gaps'] = [gap]
    investigation.open_gap_round()
    data, actions = investigation.view()
    first = data['gap_targets'][0]['read_actions'][0]
    actions['second'] = {**deepcopy(actions[first]), 'id': 'second'}
    actions['second']['identity']['unit_id'] = '1'
    value = decision(data, 'READ_ARTICLES', first)
    value['targets'] = [first, 'second']
    from semantic_runtime.contracts import digest
    investigation.p['accepted'] = {'input_hash': digest(data), 'decision': value,
        'phase': 'test-batch', 'data': data, 'actions': actions,
        'before': deepcopy(investigation.p)}
    acquired = []
    original = ur.acquire_batch
    def acquire(source, hits, state):
        acquired.append(hits[0]['unit_id'])
        if len(acquired) == 2:
            raise RuntimeError('synthetic interruption after first target checkpoint')
        return original(source, hits, state)
    monkeypatch.setattr(ur, 'acquire_batch', acquire)
    investigation.invoke = lambda *args: pytest.fail('already accepted decision must not call model')
    with pytest.raises(RuntimeError, match='synthetic interruption'):
        investigation.run()
    plan = next(iter(investigation.p['read_plans'].values()))
    assert first in plan['completed']
    again = modern(native, deepcopy(investigation.p))
    reopen_offset = len(acquired)
    again.request_decision = lambda data, actions, phase: decision(data, 'PENDING')
    again.bounded_result = lambda reason: {'bounded': reason}
    assert again.run() == {'bounded': 'MODEL_PENDING'}
    assert acquired[:2] == ['0', '1']
    assert acquired[reopen_offset:] == ['1']
    assert next(iter(again.p['read_plans'].values()))['status'] == 'ACQUIRED'


def test_equivalent_failed_search_is_not_an_alternate_route(session):
    native, _ = session
    investigation = modern(native)
    data, actions = investigation.view()
    target = next(k for k, action in actions.items() if action['action'] == 'SEARCH_STRUCTURE')
    value = decision(data, 'SEARCH_STRUCTURE', target)
    value['queries'] = ['제1조']
    investigation.p['tool_failures'] = [{'operation_key': rr.operation_key(value, actions)}]
    with pytest.raises(ProposalError, match='same failed'):
        rr.validate_failed_operation(investigation, {**value, 'queries': [' 제 1 조 ']}, actions)


def test_recoverable_failure_invalidates_pre_failure_state_version(session):
    native, _ = session
    investigation = modern(native)
    data, actions = investigation.view()
    value = decision(data, 'READ_PARENT', data['articles'][0]['read_parent_action'])
    version = investigation.p['state_version']
    def fail(*args):
        raise TimeoutError('synthetic source timeout')
    investigation.execute_tool = fail
    assert investigation.execute(value, data, actions) is False
    assert investigation.p['state_version'] == version + 1


def test_gap_target_outside_authorized_scope_never_becomes_action(session):
    native, _ = session
    investigation = modern(native)
    gap = rr.bind_gap(GAP, investigation.s)
    gap['target_binding']['document_candidates'] = ['other']
    investigation.p['assessment_gaps'] = [gap]
    with pytest.raises(ContractError, match='scope'):
        rr.add_target_actions(investigation, {})


def test_transient_partial_batch_retains_completed_original_without_adoption(session, monkeypatch):
    native, _ = session
    investigation = modern(native)
    gap = rr.bind_gap(GAP, investigation.s)
    gap.update(gap_id=ln.gap_id(gap), gap_key=cc.gap_key(gap))
    investigation.p['assessment_gaps'] = [gap]
    investigation.open_gap_round()
    data, actions = investigation.view()
    first = data['gap_targets'][0]['read_actions'][0]
    actions['second'] = {**deepcopy(actions[first]), 'id': 'second'}
    actions['second']['identity']['unit_id'] = '1'
    value = decision(data, 'READ_ARTICLES', first)
    value['targets'] = [first, 'second']
    original = ur.acquire_batch
    calls = []
    def acquire(source, hits, state):
        calls.append(hits[0]['unit_id'])
        if len(calls) == 2:raise TimeoutError('synthetic partial read timeout')
        return original(source, hits, state)
    monkeypatch.setattr(ur, 'acquire_batch', acquire)
    assert investigation.execute(value, data, actions) is False
    plan = next(iter(investigation.p['read_plans'].values()))
    assert plan['status'] == 'INTERRUPTED' and plan['remaining_target'] == 'second'
    assert first in plan['completed'] and investigation.p['selected']
    assert not inv.originals_for(investigation.s, investigation.p)
    shown, offered = investigation.view()
    assert shown['sources'] and shown['tool_recovery'][0]['absence_proven'] is False
    assert investigation.current_gap_round()['action_receipts'][-1]['status'] == 'FAILED'
