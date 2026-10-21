"""Failure injection against native tool receipts and the closed policy catalogue.

Synthetic sources only. These contracts do not certify legal/model quality.
"""
from copy import deepcopy
from dataclasses import replace
import json
import sqlite3
import pytest
from semantic_runtime.legal_agent import tool_outcome as out, tool_policy as policy
from semantic_runtime.legal_agent import unit_reading as ur, request_repair as repair
from semantic_runtime.legal_agent.errors import (ContractError, ToolExecutionError,
    ProposalError, StaleProposal, BudgetExhausted, DeadlineExceeded, TransportError)
from semantic_runtime.legal_agent.investigation_diagnostics import exception_diagnostics
from test_unit_fulltext_adaptive_read import tree, session, hit


def action(s):
    h=hit(type('Native',(),{'sources':s})())
    target=s.handle('P',{'document_id':'d','unit_id':h['unit_id'],'source_id':h['source_id'],
                         'block_ids':['3']})
    return {'tool':'read','args':{'target':target,'extent':'exact','cursor':None},
            'reason':'합성 원문 확인','question_refs':[],'expected_information':'원문'}


def outcome(**kw):
    values=dict(surface='navigation',name='READ_PARENT',operation_key='operation',
        action_id='action',binding_hash='binding',status='FAILED',execution='COMPLETED',
        effects='NONE',failure_kind='TRANSIENT',cause_code='SOURCE_TIMEOUT')
    values.update(kw)
    return out.ToolOutcome(**values)


@pytest.mark.parametrize('spec',list(policy.REGISTRY.values()),ids=lambda s:s.surface+'.'+s.name)
@pytest.mark.parametrize('failure', ['AUTH','INTEGRITY','STATE','UNKNOWN','INTERNAL','DEADLINE'])
def test_all_choices_hard_failure_never_retries(spec,failure):
    original=outcome(failure_kind=failure,cause_code=failure)
    result=policy.choose_recovery(spec,original,policy.RecoveryState(distinct_alternative=True,
        verified_remainder=True,verified_originals=True,pre_execution_rejection=True),
        policy.RecoveryBudget(finalization_available=True))
    assert result.action=='STOP' and spec.same_operation_automatic_retries==0
    assert original.failure_kind==failure


@pytest.mark.parametrize('key',list(policy.REGISTRY),ids=lambda k:'.'.join(k))
def test_all_choices_availability_and_binding(key):
    allowed=policy.assess_availability(*key,binding={'revision':1})
    blocked=policy.assess_availability(*key,binding={'revision':2},reason='NO_VALID_TARGET')
    assert allowed.offered and not blocked.offered
    assert blocked.reason_code=='NO_VALID_TARGET'
    assert blocked.current_binding_hash!=allowed.current_binding_hash
    spec=policy.REGISTRY[key]
    success=outcome(status='SUCCESS',failure_kind=None,cause_code=None)
    assert policy.choose_recovery(spec,success,policy.RecoveryState(),policy.RecoveryBudget()).action=='CONTINUE'
    assert policy.choose_recovery(spec,success,policy.RecoveryState(same_binding=False),policy.RecoveryBudget()).action=='STOP'
    assert policy.choose_recovery(spec,success,policy.RecoveryState(),policy.RecoveryBudget(deadline_expired=True)).action=='STOP'


@pytest.mark.parametrize('status,kind,execution',[
    ('ERROR','UNKNOWN','UNKNOWN'),('NOT_EXECUTED','UNKNOWN','NOT_STARTED'),
    ('DENIED','AUTH','NOT_STARTED'),('UNKNOWN','UNKNOWN','UNKNOWN')])
def test_f05_legacy_result_does_not_invent_execution(status,kind,execution):
    raw={'status':status};before=deepcopy(raw)
    normalized=out.normalize_result(raw,action={'tool':'read','args':{}},binding_hash='b')
    assert (normalized.failure_kind,normalized.execution)==(kind,execution)
    assert raw==before and normalized.status not in ('SUCCESS','EMPTY')


@pytest.mark.parametrize('cause,kind',[(PermissionError('private'),'AUTH'),(ContractError('hash'),'INTEGRITY'),
    (StaleProposal('revision'),'STATE'),(TransportError('unknown',unknown=True),'UNKNOWN'),
    (TypeError('bug'),'INTERNAL'),(DeadlineExceeded('deadline'),'DEADLINE'),(BudgetExhausted('budget'),'BUDGET')])
def test_f06_hard_nested_cause_overrides_transient(cause,kind):
    transient=TimeoutError('timeout');transient.__cause__=cause
    outer=ToolExecutionError('wrapper');outer.__cause__=transient
    assert out.classify_exception(outer)[0]==kind
    assert repair.recoverable_tool_failure(outer) is None


@pytest.mark.parametrize('code,kind',[(sqlite3.SQLITE_BUSY,'TRANSIENT'),(sqlite3.SQLITE_LOCKED,'TRANSIENT'),
                                     (sqlite3.SQLITE_CORRUPT,'INTERNAL')])
def test_f06_sql_codes_are_structured(code,kind):
    error=sqlite3.OperationalError('no string classification');error.sqlite_errorcode=code
    details=out.failure_details(error)
    assert details['kind']==kind and details['sqlite_errorcode']==code


@pytest.mark.parametrize('error,kind',[(TimeoutError('synthetic timeout'),'TRANSIENT'),
    (PermissionError('synthetic ACL'),'AUTH'),(ContractError('synthetic hash'),'INTEGRITY'),
    (TypeError('synthetic bug'),'INTERNAL')])
def test_f05_native_failure_receipt_replay_and_budget(session,monkeypatch,error,kind):
    native,_=session;s=native.sources;calls=[];a=action(s);before=s.repo.budget()['tool_used']
    def fail(*args):calls.append(1);raise error
    monkeypatch.setitem(s.handlers,'read',fail)
    with pytest.raises(ToolExecutionError) as caught:s.execute(a,'matrix-failure',actor='SYSTEM_POLICY')
    normalized=caught.value.tool_outcome
    assert normalized.failure_kind==kind and normalized.effects=='NONE'
    saved=json.loads(s.repo.db.execute("SELECT result_json FROM action_context WHERE action_id='matrix-failure'").fetchone()[0])
    assert saved['tool_outcome']['cause_code']==normalized.cause_code
    assert not saved['evidence_ids'] and not s.repo.evidence()
    with pytest.raises(ToolExecutionError) as replay:s.execute(a,'matrix-failure',actor='SYSTEM_POLICY')
    assert replay.value.tool_outcome==normalized and len(calls)==1
    assert s.repo.budget()['tool_used']==before+1
    assert exception_diagnostics(caught.value)['tool_outcome']['failure_kind']==kind
    assert 'synthetic' not in str(s.action_summaries()[-1]['server_reason'])
    with pytest.raises(ProposalError) as conflict:s.execute({**a,'reason':'different input'},'matrix-failure',actor='SYSTEM_POLICY')
    assert repair.recoverable_tool_failure(conflict.value) is None
    assert len(calls)==1


def test_f05_handler_result_cause_survives_wrappers(session,monkeypatch):
    native,_=session;s=native.sources;a=action(s)
    monkeypatch.setitem(s.handlers,'read',lambda *args:([],None,[],{'status':'ERROR',
        'failure':out.failure_details(TimeoutError('synthetic'))}))
    with pytest.raises(ToolExecutionError) as caught:s.execute(a,'matrix-returned-error',actor='SYSTEM_POLICY')
    assert caught.value.tool_outcome.failure_kind=='TRANSIENT'
    assert repair.recoverable_tool_failure(caught.value)=='SOURCE_TEMPORARILY_UNAVAILABLE'


def test_f05_rejected_before_execution_does_not_spend_or_run(session,monkeypatch):
    native,_=session;s=native.sources;a=action(s);before=s.repo.budget()['tool_used'];calls=[]
    def reject(*args):raise ProposalError('synthetic bad selection')
    monkeypatch.setattr(s,'validate_action',reject)
    monkeypatch.setitem(s.handlers,'read',lambda *args:calls.append(1))
    result=s.execute(a,'matrix-rejected',actor='SYSTEM_POLICY')
    assert result['status']=='NOT_EXECUTED' and not calls
    assert result['tool_outcome']['execution']=='NOT_STARTED'
    assert result['tool_outcome']['failure_kind']=='PROPOSAL'
    assert s.repo.budget()['tool_used']==before


def test_f13_missing_terminal_is_unknown_and_never_replayed(session,monkeypatch):
    native,_=session;s=native.sources;a=action(s);original=s.repo.record_observation;calls=[]
    handler=s.handlers['read']
    def read(*args):calls.append(1);return handler(*args)
    def fail(*args,**kw):raise OSError('synthetic disk full')
    monkeypatch.setitem(s.handlers,'read',read);monkeypatch.setattr(s.repo,'record_observation',fail)
    with pytest.raises(OSError) as caught:s.execute(a,'matrix-write',actor='SYSTEM_POLICY')
    assert caught.value.tool_outcome.execution=='UNKNOWN'
    assert repair.recoverable_tool_failure(caught.value) is None
    monkeypatch.setattr(s.repo,'record_observation',original)
    with pytest.raises(ToolExecutionError):s.execute(a,'matrix-write',actor='SYSTEM_POLICY')
    assert len(calls)==1 and not s.repo.evidence()


def test_f13_receipt_failure_preserves_unknown_and_original_cause(session,monkeypatch):
    native,_=session;s=native.sources;a=action(s);event=s.repo.event
    def fail(*args):raise TimeoutError('synthetic read timeout')
    def record(kind,*args,**kw):
        if kind=='TOOL_OUTCOME_RECORDED':raise OSError('synthetic receipt disk full')
        return event(kind,*args,**kw)
    monkeypatch.setitem(s.handlers,'read',fail);monkeypatch.setattr(s.repo,'event',record)
    with pytest.raises(ToolExecutionError) as caught:s.execute(a,'matrix-no-receipt',actor='SYSTEM_POLICY')
    assert caught.value.tool_outcome.failure_kind=='UNKNOWN'
    assert caught.value.tool_outcome.cause_code=='TOOL_RECEIPT_WRITE_FAILED'
    assert repair.recoverable_tool_failure(caught.value) is None
    assert 'synthetic read timeout' in str(caught.value.__cause__)


def test_f12_failed_read_reservation_stays_spent(session,monkeypatch):
    native,_=session;s=native.sources;h=hit(native);offer=ur.offers(s,h)[0]
    state=ur.read_state(s);before=deepcopy(state);budget=s.repo.budget()['tool_used']
    def fail(*args):raise TimeoutError('synthetic')
    monkeypatch.setitem(s.handlers,'read',fail)
    with pytest.raises(ToolExecutionError):ur.read(s,h,offer,action_state=state)
    assert state['count']==before['count']+1 and s.repo.budget()['tool_used']==budget+1
    assert not s.repo.evidence() and state['chars']==before['chars']


def test_f46_policy_checkpoint_preserves_legacy_and_rejects_drift():
    state={'accepted':{'unchanged':True},'usage':8,'deadline':123}
    policy.bind_checkpoint(state,'b',legacy=True)
    assert state['tool_policy']['version']==policy.LEGACY
    before=deepcopy(state);policy.bind_checkpoint(state,'b');assert state==before
    for corrupt in ({'binding':'other'},{'policy_hash':'other'},{'version':'future'}):
        changed=deepcopy(state);changed['tool_policy'].update(corrupt)
        with pytest.raises(ContractError):policy.bind_checkpoint(changed,'b')
    assert state['usage']==8 and state['deadline']==123


def test_f07_only_distinct_alternative_and_existing_budget():
    spec=policy.REGISTRY['navigation','READ_PARENT'];o=outcome()
    assert policy.choose_recovery(spec,o,policy.RecoveryState(),policy.RecoveryBudget()).action=='STOP'
    current=policy.RecoveryState(distinct_alternative=True)
    assert policy.choose_recovery(spec,o,current,policy.RecoveryBudget()).action=='OFFER_ALTERNATIVE'
    assert policy.choose_recovery(spec,o,current,policy.RecoveryBudget(investigation_available=False)).action=='STOP'
    assert policy.choose_recovery(spec,replace(o,execution='UNKNOWN'),current,policy.RecoveryBudget()).action=='STOP'


def test_f01_registry_matches_all_37_design_choices():
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]
    design=json.loads((root/'07_DOCS/REFERENCE/REPORTS/TOOL_FAILURE_RECOVERY_DESIGN_20261014/POLICY_DESIGN.json').read_text())
    assert set(policy.REGISTRY)=={(c['surface'],c['name']) for c in design['choices']}
    assert len(policy.REGISTRY)==37
    assert not policy.assess_availability('navigation','invented',binding='b').offered


def test_f05_v1_source_result_keeps_sql_cause(session,monkeypatch):
    native,_=session;source=native.sources.source
    error=sqlite3.OperationalError('synthetic busy');error.sqlite_errorcode=sqlite3.SQLITE_BUSY
    def fail(*args,**kwargs):raise error
    monkeypatch.setattr(source.navigator,'catalogue',fail)
    result=source.execute({'tool':'list_documents','args':{'query':'승인','cursor':None},'reason':'합성 조회'})
    assert result['status']=='ERROR' and result['error_code']=='SOURCE_QUERY_ERROR'
    assert result['failure']['kind']=='TRANSIENT' and result['failure']['sqlite_errorcode']==sqlite3.SQLITE_BUSY
    assert result['failure']['failure_ref'].startswith('event:') and 'synthetic busy' not in str(result)
    assert not result['coverage']['complete'] and not result['evidence_ids']


def test_f05_v2_relations_result_keeps_sql_cause(session,monkeypatch):
    from semantic_runtime.legal_agent.relations_tools import RelationsTools
    native,_=session;s=native.sources;a=action(s)
    error=sqlite3.OperationalError('synthetic busy');error.sqlite_errorcode=sqlite3.SQLITE_BUSY
    calls=[]
    def fail(*args):calls.append(1);raise error
    monkeypatch.setitem(s.handlers,'read',fail);s._draining=True
    result=RelationsTools.execute(s,a,'matrix-v2',actor='SYSTEM_POLICY')
    assert result['status']=='ERROR' and result['tool_outcome']['failure_kind']=='TRANSIENT'
    assert not result['evidence_ids'] and not s.repo.evidence() and not result['coverage']['complete']
    assert RelationsTools.execute(s,a,'matrix-v2',actor='SYSTEM_POLICY')==result
    assert len(calls)==1


@pytest.mark.parametrize('status',['DENIED','UNKNOWN','NOT_EXECUTED'])
def test_f05_unsuccessful_handler_never_commits_returned_evidence(session,monkeypatch,status):
    native,_=session;s=native.sources;a=action(s);handler=s.handlers['read']
    def bad(*args):
        items,cursor,evidence,extra=handler(*args)
        return items,cursor,evidence,{**extra,'status':status}
    monkeypatch.setitem(s.handlers,'read',bad)
    with pytest.raises(ToolExecutionError):s.execute(a,'matrix-unsuccessful',actor='SYSTEM_POLICY')
    assert not s.repo.evidence()
    assert not s.repo.db.execute("SELECT 1 FROM observation WHERE status IN ('OK','PARTIAL','REUSED')").fetchone()


def test_f13_intent_storage_failure_never_dispatches(session,monkeypatch):
    native,_=session;s=native.sources;a=action(s);event=s.repo.event;calls=[];before=s.repo.budget()['tool_used']
    def record(kind,*args,**kwargs):
        if kind=='ACTION_PROPOSED':raise OSError('synthetic intent write failure')
        return event(kind,*args,**kwargs)
    monkeypatch.setattr(s.repo,'event',record)
    monkeypatch.setitem(s.handlers,'read',lambda *args:calls.append(1))
    with pytest.raises(OSError):s.execute(a,'matrix-no-intent',actor='SYSTEM_POLICY')
    assert not calls and s.repo.budget()['tool_used']==before
    assert s.repo.db.execute("SELECT COUNT(*) FROM action_context WHERE action_id='matrix-no-intent'").fetchone()[0]==0


def test_f12_partial_read_retains_pages_and_exact_continuation(session,monkeypatch):
    native,_=session;s=native.sources;h=hit(native,'0')
    offer=next(o for o in ur.offers(s,h) if o['extent']=='subtree')
    s.profile['max_read_chars']=5;handler=s.handlers['read'];calls=[];state=ur.read_state(s)
    def fail_second(*args):
        calls.append(1)
        if len(calls)==2:raise TimeoutError('synthetic second page')
        return handler(*args)
    monkeypatch.setitem(s.handlers,'read',fail_second)
    with pytest.raises(ToolExecutionError) as caught:ur.read(s,h,offer,action_state=state)
    evidence=s.repo.evidence();assert evidence and len(calls)==2
    assert caught.value.read_progress['completed_receipt_refs']==[e['evidence_id'] for e in evidence]
    assert caught.value.read_progress['remaining_target']['cursor'] is not None
    assert state['count']==2 and state['chars']==5
    assert caught.value.tool_outcome.effects=='NONE'  # the failed page itself committed nothing
    assert exception_diagnostics(caught.value)['read_progress']==caught.value.read_progress


@pytest.mark.parametrize('status',['PARTIAL','TRUNCATED','UNRESOLVED'])
def test_f12_partial_result_needs_actual_receipt(status):
    args=dict(action={'tool':'read','args':{}},binding_hash='b')
    missing=out.normalize_result({'status':status},**args)
    assert missing.failure_kind=='UNKNOWN' and missing.status=='INTERRUPTED'
    committed=out.normalize_result({'status':status,'observation_id':'O1'},**args)
    assert committed.status=='PARTIAL' and committed.receipt_refs==('O1',)


def test_f06_schema_proposal_keeps_existing_repair_owner():
    from jsonschema import validate,ValidationError
    try:
        try:validate({'wrong':1},{'type':'object','required':['expected']})
        except ValidationError as cause:raise ProposalError('concrete field error') from cause
    except ProposalError as error:
        assert repair.recoverable_tool_failure(error)=='ACTION_REJECTED'


def test_f06_implicit_hard_cause_cannot_be_hidden_by_cleanup_timeout():
    try:
        try:raise PermissionError('synthetic access denial')
        except PermissionError:raise TimeoutError('cleanup timed out')
    except TimeoutError as error:
        assert repair.recoverable_tool_failure(error) is None


from test_batch_reference_navigation import connected,initial,decision as reference_decision


def test_f04_reference_budget_changed_after_menu_stays_budget_failure(connected,monkeypatch):
    from semantic_runtime.legal_agent import unit_relations as rel
    s,_=connected;rec,_=initial(s);state=rec['read_state'];selected={'U1':rec['unit_reads'][0]}
    ur.ensure_context(s,selected,state);before=s.repo.budget()['tool_used'];calls=[]
    def invoke(system,data,schema,phase,timeout):
        calls.append(1)
        monkeypatch.setitem(ur.POLICY,'initial_chars',state['chars'])
        value=reference_decision(data)
        chosen=next(g for g in data['groups'] if g['target']['document_id']=='detail')
        next(d for d in value['decisions'] if d['id']==chosen['id']).update(
            action='FOLLOW',applicability='APPLIES',scopes=['subtree:1'])
        return value
    with pytest.raises(BudgetExhausted):rel.navigate('승인',s,selected,invoke,
        read_state=state,seconds_left=lambda:120,max_context_chars=80000)
    assert len(calls)==1 and s.repo.budget()['tool_used']==before


@pytest.mark.parametrize('alternate',[False,True])
def test_f07_same_tool_different_target_is_distinct_operation(monkeypatch,alternate):
    import time
    from types import SimpleNamespace
    from semantic_runtime.legal_agent import tool_availability
    events=[]
    inv=SimpleNamespace(p={'binding':'b','no_progress':0,'groups':{}},control=False,
        s=SimpleNamespace(context=SimpleNamespace(deadline=time.monotonic()+30),
            repo=SimpleNamespace(budget=lambda:{'tool_used':1,'tool_limit':10},event=lambda *args:events.append(args))))
    actions={'T1':{'action':'READ_PARENT','identity':{'branch_id':'g1'}}}
    if alternate:actions['T2']={'action':'READ_PARENT','identity':{'branch_id':'g2'}}
    monkeypatch.setattr(tool_availability,'navigation_reason',lambda *args:None)
    choice={'next_action':'READ_PARENT','targets':['T1'],'queries':[]}
    result=repair.record_tool_failure(inv,choice,actions,{'id':'step'},TimeoutError('synthetic'))
    assert result is alternate
    if alternate:
        assert inv.p['tool_failures'][0]['recovery_policy']['action']=='OFFER_ALTERNATIVE'
        with pytest.raises(ProposalError):repair.validate_failed_operation(inv,choice,actions)
        repair.validate_failed_operation(inv,{**choice,'targets':['T2']},actions)
