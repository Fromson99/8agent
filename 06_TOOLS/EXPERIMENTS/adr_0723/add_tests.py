from pathlib import Path
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0723/integrated/snapshot';L=C/'02_BACKEND/semantic_runtime/legal_agent'
p=L/'request_repair.py';s=p.read_text().replace("s['start'] < w['end'] and w['start'] < s['end']","s['start_cp'] < w['end_cp'] and w['start_cp'] < s['end_cp']");p.write_text(s)
p=C/'05_TESTS/CONTRACTS/test_main50_request_repair.py';p.write_text(p.read_text()+'''


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
        if len(calls)==1:return decision(d,'READ_PARENT',d['articles'][0]['read_parent_action'])
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
''')
# Reuse the established pin refresh/freezing and contract runner with exact new identity.
for name in ['freeze.py','run_contracts.py']:
 s=(R/'06_TOOLS/EXPERIMENTS/adr_0720'/name).read_text().replace('adr_0720','adr_0723').replace('ADR-0720-immutable-decision-retry-resume','ADR-0723-source-target-recovery-complete').replace("'resumed'","'integrated'")
 (R/'06_TOOLS/EXPERIMENTS/adr_0723'/name).write_text(s)
print('Added native recovery invariants and registered existing contract runner')
