from copy import deepcopy
from pathlib import Path
import gzip, json, importlib.util
import pytest
from jsonschema import Draft202012Validator
from semantic_runtime.legal_agent import need_continuity as nc, read_judgment_final as final
from semantic_runtime.legal_agent import assessment_links as links, memory_methods as mm
from semantic_runtime.legal_agent import output_contract as oc
from test_memory_runtime_v2 import memory, start, command
from conftest import term_glossary

ROOT=Path(__file__).resolve().parents[3]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
fixture=module('scope_recovery_fixture','05_TESTS/CONTRACTS/test_scope_review.py').fixture
previous=module('direct_review_fixture','06_TOOLS/EXPERIMENTS/adr_1324/test_direct_links.py')

def singles(value):
    result=deepcopy(value)
    for scope in result.get('read_judgment_review',{}).get('scope_reviews',[]):
        scope['groups']=[{**deepcopy(group),'basis_refs':[ref]} for group in scope['groups'] for ref in group['basis_refs']]
    return result

def shape():
    ctx,opts,value=fixture()
    base={'type':'object','properties':{k:{} for k in ('claims','gaps','issue_assessments')},'required':['claims','gaps','issue_assessments'],'additionalProperties':False}
    schema=links.attach(final.attach(base,ctx,opts),opts,direct=True)
    wire,expand=links.projection(schema)
    return ctx,opts,value,schema,nc.generation_schema(wire,ctx),expand

def test_per_original_wire_and_canonical_legacy_groups_preserve_decisions():
    ctx,opts,value,schema,wire,expand=shape()
    # Legacy grouped EXCLUDE remains a valid stored/decoded canonical record.
    final.validate_review(expand(value),ctx,opts)
    assert not Draft202012Validator(wire).is_valid(value)
    current=singles(value);before=deepcopy(current)
    oc.validate_shape(current,wire);final.validate_review(expand(current),ctx,opts)
    assert current==before and current['claims']==value['claims'] and current['gaps']==value['gaps']
    assert all(len(g['basis_refs'])==1 for row in current['read_judgment_review']['scope_reviews'] for g in row['groups'])

@pytest.mark.parametrize('fault',['all_used','missing','duplicate_target','foreign','zero_refs','two_refs'])
def test_generation_rejects_ambiguous_or_incomplete_scope_rows(fault):
    c,o,v,s,w,expand=shape();v=singles(v);rows=v['read_judgment_review']['scope_reviews'];g=rows[0]['groups']
    if fault=='all_used':g[:]=[{**g[1],'basis_refs':['S1','S2','S3']}]
    if fault=='missing':g.pop()
    if fault=='duplicate_target':rows[1]['target_id']='GNa'
    if fault=='foreign':g[1]['basis_refs']=['S5']
    if fault=='zero_refs':g[1]['basis_refs']=[]
    if fault=='two_refs':g[1]['basis_refs']=['S2','S3']
    assert not Draft202012Validator(w).is_valid(v)

@pytest.mark.parametrize('disposition',['USE','EXCLUDE','OPEN'])
def test_provider_numbered_refs_and_constant_projection_preserve_scope_shape(disposition):
    from semantic_runtime.legal_agent.navigation_input import NavigationReferences
    from semantic_runtime.legal_agent.minimal_output import Projection
    c,o,v,s,w,expand=shape();v=singles(v);g=v['read_judgment_review']['scope_reviews'][0]['groups'][1]
    g.update(disposition=disposition,claim_refs=['C1'] if disposition=='USE' else [],gap_indices=[1] if disposition=='OPEN' else [])
    data={'read_judgments':c,'evidence_options':o,'source_stage':'memory-assess'}
    refs=NavigationReferences(data);provider_schema=refs.schema(w);encoded=refs.view(v)
    projection=Projection(provider_schema);actual=projection.project(encoded)
    oc.validate_shape(actual,projection.wire)
    decoded=refs.decode(projection.expand(actual),provider_schema)
    assert decoded==v

def test_recorded_rejection_explains_exact_uncited_original_without_mutation():
    base=ROOT/'04_EXPERIMENTS/ADR/ADR-1325-assessment-direct-links-live-multiturn/artifacts/public-live/repeat-integrated/canonical'
    with gzip.open(base/'006-output.json.gz','rt') as f:value=json.load(f)
    with gzip.open(base/'007.json.gz','rt') as f:feedback=json.load(f)['view']['repair_feedback']
    diag=feedback['validation'];error=oc.OutputContractError('recorded',diag['issues'],category=diag['category'])
    before=deepcopy(value);rows=final.repair_choices(value,error)
    exact=next(r for r in rows if r['cause']=='SCOPE_GROUP_CONTAINS_UNUSED_ORIGINAL')
    assert exact['unsupported_evidence_refs']==['S62fdc2ff6f5fc20b228b2790920d']
    assert all('S62fdc2ff6f5fc20b228b2790920d' not in c['evidence_refs'] for c in exact['linked_claim_evidence'])
    assert len(exact['alternatives'])==2 and value==before

def incomplete():
    return {'claims':[],'source_excerpt_reply':{'verified':True},'answer_coverage':'INSUFFICIENT',
      'model_proposal':{'review_status':'INCOMPLETE','failure_code':'ASSESSMENT_CONTRACT_UNRESOLVED',
        'failure':{'category':'FINAL_READ_REVIEW_INVALID','repairable':True,'issues':[oc.issue('SCOPE_USE_UNSUPPORTED_RANGE','/read_judgment_review/scope_reviews/0/groups/0/basis_refs',expected={'missing_evidence_refs':['S3']})]}},
      'stop_reason':'ASSESSMENT_CONTRACT_UNRESOLVED'}

@pytest.mark.parametrize('fault',[None,'unknown','nonrepairable','no_original','success','no_diagnostic'])
def test_only_known_incomplete_review_exposes_recovery(fault):
    value=incomplete()
    if fault=='unknown':value['model_proposal']['failure_code']='MODEL_DEADLINE_EXCEEDED'
    if fault=='nonrepairable':value['model_proposal']['failure']['repairable']=False
    if fault=='no_original':value.pop('source_excerpt_reply')
    if fault=='success':value['model_proposal']['review_status']='REVIEWED'
    if fault=='no_diagnostic':value['model_proposal'].pop('failure')
    before=deepcopy(value);result=mm.review_recovery(value)
    assert bool(result and result['available'])==(fault is None)
    if result:assert result['automatic_retry'] is False and result['legal_conclusion_confirmed'] is False
    assert value==before

def test_real_memory_context_keeps_failure_and_reenters_assess_without_search(memory):
    mem,f,w,send,p=memory;original=f.stage
    f.stage=lambda stage,*args:incomplete() if stage=='ASSESS' else original(stage,*args)
    first=start(send);gid=first['goal_id'];before=mem.parts(gid)
    context=mem.context('s',p,'같은 요청');recovery=context['goals'][0]['previous_response']['review_recovery']
    assert recovery['available'] and recovery['failure']['issues'][0]['code']=='SCOPE_USE_UNSUPPORTED_RANGE'
    seen=[]
    def invoke(system,data,schema,phase):
        seen.append(phase)
        assert 'review_recovery' in system
        if phase=='memory-resolve':
            assert data['goals'][0]['previous_response']['review_recovery']==recovery
            return command('RESEARCH_REENTER',target=gid,stage='ASSESS')
        return {'valid':True,'reason':'같은 원문의 최종 검토를 다시 실행'}
    mem.invoke=invoke;f.stage=original
    body={'question':'같은 요청','session_id':'s','request_id':'review-again'}
    result=mem.execute(body,p)
    assert result['goal_id']==gid and result['executed']==['ASSESS','COMPOSE']
    assert mem.parts(gid)['SELECT']==before['SELECT'] and mem.parts(gid)['READ']==before['READ']
    assert mem.execute(body,p)==result and len(seen)==2

@pytest.fixture
def per_original_wire(monkeypatch):
    observed=previous.direct_wire.__wrapped__(monkeypatch)
    import test_legal_agent_double_harness as harness
    old=harness.wire
    monkeypatch.setattr(harness,'wire',lambda value:old(singles(value) if isinstance(value,dict) else value))
    return observed

@pytest.mark.parametrize('fault',[None,'scope_first','scope_twice','need_first','need_twice','open'])
def test_actual_api_scope_decision_repair_persistence_and_duplicate(tmp_path,term_glossary,monkeypatch,per_original_wire,fault):
    from need_continuity_fixture import run_api
    result=run_api(tmp_path,term_glossary,'goal_control',monkeypatch,coverage_fault=fault)
    assert per_original_wire
    if fault in ('scope_twice','need_twice'):
        assert result is None;return
    response,calls,reviews=result
    assert len([p for p in calls if p.startswith('memory-assess')])==(2 if fault in ('scope_first','need_first') else 1)
    assert all(len(g['basis_refs'])==1 for value in per_original_wire for row in value.get('read_judgment_review',{}).get('scope_reviews',[]) for g in row['groups'])
