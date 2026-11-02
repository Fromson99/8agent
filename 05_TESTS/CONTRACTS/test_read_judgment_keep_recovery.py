from copy import deepcopy
from pathlib import Path
import json
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import read_judgment as rj, output_contract as oc
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from test_read_judgment import setup, commit, proposal
from test_output_contract_recovery import Journal, SCHEMA


@pytest.mark.parametrize('index',[0,1])
def test_exact_live_failure_is_reconstructed_without_changing_meaning(index):
    rows=json.loads((Path(__file__).parents[1]/'FIXTURES/read_judgment_keep_1034.json').read_text())
    fixture=rows[index];raw=fixture['proposal'];before=deepcopy(raw);ctx=fixture['ctx']
    result,changes=rj.normalize_review(raw,ctx)
    current={ref:{} for b in ctx['current_originals'] for ref in b['source_refs']}
    rj.validate_review(result,ctx,current,['Q1'])
    assert raw==before and result['selections']==raw['selections']
    assert len(changes)==4 and all(x['rule']=='EXACT_PRIOR_FINDING_REPEATED' for x in changes)
    assert all(not r['finding'] for r in result['read_review']['judgments'])
    assert rj.normalize_review(result,ctx)==(result,[])


@pytest.mark.parametrize('index',[2,3])
def test_changed_live_keep_finding_is_not_silently_accepted(index):
    rows=json.loads((Path(__file__).parents[1]/'FIXTURES/read_judgment_keep_1034.json').read_text())
    with pytest.raises(oc.OutputContractError,match='unapproved change'):
        rj.normalize_review(rows[index]['proposal'],rows[index]['ctx'])


@pytest.mark.parametrize('op',['KEEP','WITHDRAW'])
def test_delta_retains_history_needs_and_exact_prior_content(op):
    inv,data,*_=setup();commit(inv,data,'1',missing=['원문 미확인'])
    prior=deepcopy(rj.state_for(inv,data));ctx=rj.context(inv,data,'2');head=ctx['judgments'][0]
    raw=proposal(ctx,op=op,use='SUPPORT' if op=='KEEP' else 'EXCLUDE')
    row=raw['read_review']['judgments'][0]
    for name in ('use','finding','issue_refs','missing','conflicts_with'):row.pop(name)
    normalized,changes=rj.normalize_review(raw,ctx)
    rj.record(inv,data,normalized,'2',ctx,{},wire_value=raw,normalizations=changes)
    state=rj.state_for(inv,data);after=state['heads'][head['id']]
    assert state['needs']==prior['needs']
    assert state['receipts']['1']==prior['receipts']['1']
    assert after['finding']==head['finding'] and after['version']==2
    assert after['use']==('SUPPORT' if op=='KEEP' else 'EXCLUDE')
    assert state['receipts']['2']['wire_proposal_hash']==digest(raw)
    assert state['receipts']['2']['normalizations']==changes


@pytest.mark.parametrize('field,value',[('finding','반대 판단'),('use','CORE'),('issue_refs',[]),('missing',['새 부족']),('conflicts_with',['Jother'])])
def test_legacy_host_field_cannot_change_prior_meaning(field,value):
    inv,data,*_=setup();commit(inv,data,'1');ctx=rj.context(inv,data,'2');raw=proposal(ctx,op='KEEP')
    raw['read_review']['judgments'][0][field]=value
    with pytest.raises(ProposalError):rj.normalize_review(raw,ctx)


def test_delta_normalization_does_not_bypass_original_proof():
    inv,data,*_=setup();commit(inv,data,'1');ctx=rj.context(inv,data,'2');raw=proposal(ctx,op='KEEP')
    raw['read_review']['judgments'][0]['basis_refs']=['UNKNOWN']
    normalized,_=rj.normalize_review(raw,ctx)
    with pytest.raises(oc.OutputContractError) as rejected:rj.record(inv,data,normalized,'2',ctx,{})
    assert 'READ_JUDGMENT_WRONG_ORIGINAL' in {i['code'] for i in rejected.value.issues}
    assert len(rj.state_for(inv,data)['history'])==1


def test_wire_projection_omits_retained_fields_but_keeps_required_source_reason():
    from semantic_runtime.legal_agent.minimal_output import Projection
    inv,data,*_=setup();commit(inv,data,'1');ctx=rj.context(inv,data,'2')
    schema=rj.wire_review_schema(ctx,{'Ba':{}},['Q1'])
    projection=Projection(schema)
    wire=projection.wire
    # ReadOnly values are ingestion-compatible only, not fields to regenerate.
    variants=wire['properties']['judgments']['items']['anyOf']
    keep=next(x for x in variants if x['properties']['operation'].get('const')=='KEEP' or x['properties']['operation'].get('enum')==['KEEP'])
    assert not {'finding','use','issue_refs','missing','conflicts_with'} & keep['properties'].keys()
    assert 'reason' in keep['required'] and 'basis_refs' in keep['properties']


def run(repo,scope,invoke,identity='page1',schema=SCHEMA,can_repair=None):
    return oc.bounded_decision(repo,'read-choice',{'page':identity},schema,invoke,
        lambda v:oc.validate_shape(v,schema),identity={'page':identity},correction_scope=scope,can_repair=can_repair)


def test_retry_limit_survives_reentry_schema_aliases_and_restart(tmp_path):
    path=tmp_path/'retry.sqlite';repo=Journal(path);calls=[];scope={'request':'Q','material':['same'],'heads':[1]}
    def bad(*_):calls.append(1);return {'ok':False}
    with pytest.raises(ProposalError):run(repo,scope,bad)
    repo.db.close();repo=Journal(path)
    with pytest.raises(ProposalError,match='same-evidence'):
        run(repo,scope,bad,identity='ASSESS-return-new-menu',schema={**SCHEMA,'title':'new-menu'})
    assert len(calls)==2
    events=[json.loads(x[0]) for x in repo.db.execute("select payload_json from event where kind='OUTPUT_CORRECTION_SCOPE'")]
    assert len(events)==4 and len(events[-1]['failures'])==2
    assert events[-1]['status']=='REJECTED'


def test_successful_correction_reuses_accepted_response(tmp_path):
    repo=Journal(tmp_path/'retry.sqlite');calls=[]
    def invoke(*_):calls.append(1);return {'ok':len(calls)==2}
    assert run(repo,{'material':'same'},invoke)=={'ok':True}
    assert run(repo,{'material':'same'},invoke)=={'ok':True}
    assert len(calls)==2


def test_new_original_has_own_budget_without_resetting_old_failures(tmp_path):
    repo=Journal(tmp_path/'retry.sqlite');calls=[]
    def bad(*_):calls.append(1);return {'ok':False}
    with pytest.raises(ProposalError):run(repo,{'material':'old'},bad)
    assert run(repo,{'material':'new'},lambda *_:{'ok':True},identity='new')=={'ok':True}
    with pytest.raises(ProposalError):run(repo,{'material':'old'},bad,identity='back')
    assert len(calls)==2


def test_unknown_scope_reservation_blocks_changed_presentation_after_restart(tmp_path):
    path=tmp_path/'retry.sqlite';repo=Journal(path);scope={'original':'same'}
    def lost(*_):raise RuntimeError('simulated process interruption')
    with pytest.raises(RuntimeError):run(repo,scope,lost)
    repo.db.close();repo=Journal(path)
    with pytest.raises(ContractError,match='unknown'):
        run(repo,scope,lambda *_:pytest.fail('must not send'),identity='new-menu')


def test_scope_hash_failure_is_not_a_model_repair(tmp_path):
    repo=Journal(tmp_path/'retry.sqlite');scope={'original':'same'}
    run(repo,scope,lambda *_:{'ok':True})
    with repo.transaction():repo.db.execute("update event set payload_hash='bad' where kind='OUTPUT_CORRECTION_SCOPE' and seq=(select max(seq) from event where kind='OUTPUT_CORRECTION_SCOPE')")
    with pytest.raises(ContractError,match='hash'):
        run(repo,scope,lambda *_:pytest.fail('must not send'),identity='next')


def test_nonretryable_owner_stop_cannot_be_reset_by_reentry(tmp_path):
    repo=Journal(tmp_path/'retry.sqlite');scope={'material':'same'};calls=[]
    def bad(*_):calls.append(1);return {'ok':False}
    with pytest.raises(ProposalError):run(repo,scope,bad,can_repair=lambda:False)
    with pytest.raises(ProposalError):run(repo,scope,bad,identity='next')
    assert len(calls)==1


def test_scope_ignores_presentation_and_final_text_but_binds_original_and_revision():
    inv,data,page,*_=setup();commit(inv,data,'1');ctx=rj.context(inv,data,'2');scope=rj.correction_scope(ctx)
    changed=deepcopy(ctx);changed['state_hash']='new';changed['needs']=[{'reason':'different words'}];changed['previous_final_review']=[{'review':'new'}]
    assert rj.correction_scope(changed)==scope
    changed['judgments'][0]['version']+=1
    assert rj.correction_scope(changed)!=scope
    data['sources'].append(page('new'));assert rj.correction_scope(rj.context(inv,data,'3'))!=scope
