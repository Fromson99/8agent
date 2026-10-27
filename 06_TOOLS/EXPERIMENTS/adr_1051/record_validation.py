"""Record the isolated implementation audit, without running a model or selecting it."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-1051-paged-clause-navigation'
ART = ADR/'artifacts'
CAND = ROOT/'02_BACKEND/lawrag/research/candidates/adr_1051/paged-clause-r1'
def read(p): return json.loads(p.read_text())
def save(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def rel(p): return str(p.relative_to(ROOT))

candidate=read(CAND/'candidate.json');rev=candidate['revisions'][-1]
current=read(ART/'contracts-r8-summary.json')
baseline=read(ART/'baseline-regression-summary.json')
frozen=read(ART/'frozen-contracts-summary.json')
fail=lambda d: sorted(r['nodeid'] for r in d['rows'] if r['outcome']=='failed')
assert fail(current)==fail(baseline) and len(fail(current))==10
assert (current['passed'],frozen['passed'],frozen['failed'])==(76,10,0)
assert current['files']==frozen['files']
for d in (current,baseline,frozen):
    assert not d['production_import_leaks'] and not d['candidate_changed_during_tests']
result={'status':'complete','scope':'synthetic implementation/API contracts only',
        'candidate_passed':76,'candidate_failed':10,'new_contracts_passed':10,
        'baseline_subset_passed':baseline['passed'],'baseline_failed':10,
        'same_preexisting_failures':fail(current),'frozen_contracts_passed':10,
        'tested_files_equal_frozen_files':True,'production_import_leaks':{},
        'external_model_calls':0,'answer_accuracy':None,'token_reduction':None,
        'candidate_revision_sha256':rev['revision_sha256'],
        'existing_experiment':'Untouched; independently stopped at cell44 OUTPUT_WHITESPACE_STALL; user decision requested.',
        'main_unchanged':True,'genos_unchanged':True}
save(ART/'result.json',result)
m=read(ADR/'실험/manifest.json');plan=read(ART/'implementation-plan.json')
m['lineage']['hypothesis_delta']=plan['hypothesis']
design=m['design'];design.update(hypothesis=plan['hypothesis'],
    primary_metric='Deterministic navigation, source, state, scope and API contracts',
    success_criteria='; '.join(plan['success_criteria']),
    failure_criteria='Unselected sibling original read, candidate loss on continuation, retained source loss, ACL/hash/state bypass or added retry layer',
    criteria_frozen_before_run=True,
    criteria_record={'path':rel(ART/'implementation-plan.json'),'sha256':sha(ART/'implementation-plan.json')},
    failure_recovery=plan['failure_contract'])
design['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{
    'candidate_id':'paged-clause-r1','arm_id':'paged-clause','experiment_id':m['experiment_id'],
    'run_ids':['run-001'],'manifest_path':rel(CAND/'candidate.json'),
    'manifest_sha256':sha(CAND/'candidate.json'),'revision_id':rev['revision_id'],
    'revision_sha256':rev['revision_sha256'],
    'runner_path':'06_TOOLS/EXPERIMENTS/adr_1051/validate_candidate.py',
    'runner_sha256':sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_1051/validate_candidate.py')}])
design['arms'][0].update(changes='Read-only ADR1049 frozen code; regression failures reproduced, no live result treated as parent',controls='Same synthetic fixture source, no model calls')
design['arms'][1].update(changes='First search page3laws x2article cards; non-leaf article outline then selected paragraph/item read',controls='Same source/state/permission/hash checks and call/tool/time/input budgets')
m['runs'][0].update(selection_rule='Small deterministic synthetic contracts and API fixture; criteria recorded before implementation, no live quality comparison',status='complete',artifact_path=rel(ART/'result.json'),sha256=sha(ART/'result.json'),executed_arm_ids=['baseline','paged-clause'])
m['llm_policy']['llm_calls']=[]
test=CAND/'revisions/rev-001/snapshot/05_TESTS/CONTRACTS/test_progressive_clauses_adr1051.py'
m['dataset'].update(name='Synthetic navigation and API fixtures',version='paged-clause-navigation-v1',frozen_source=rel(test),sha256=sha(test))
reason='Implementation contracts only; candidate changes presentation/read scope, but this run does not measure real-corpus retrieval, gold recall, token cost or model quality.'
m['retrieval_accounting']['not_applicable_reason']=reason
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
m['results'].update(status='complete',by_arm={
    'baseline':{'status':'complete','correct':None,'total':0,'accuracy':None,'contract_subset_passed':baseline['passed'],'contract_failed':10},
    'paged-clause':{'status':'complete','correct':None,'total':0,'accuracy':None,'contract_passed':76,'contract_failed':10,'new_contracts_passed':10}},
    comparisons=[],judge_disagreements=None,usage={'physical_calls':0,'input_tokens':0,'output_tokens':0},
    latency={'model_latency':None},error_taxonomy=fail(current))
save(ADR/'실험/manifest.json',m)
art=read(ART/'manifest.json');art['files']=[]
for p in sorted(ART.iterdir()):
    if p.is_file() and p.name!='manifest.json':
        art['files'].append({'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Preserved implementation validation artifact','contains_raw_prompts_and_outputs':False})
save(ART/'manifest.json',art)
print(json.dumps(result,ensure_ascii=False))
