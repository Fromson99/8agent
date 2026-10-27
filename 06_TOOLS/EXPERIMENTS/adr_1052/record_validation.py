"""Bind the synthetic-only audit to its verified frozen candidate."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1052-law-overview-twenty-articles'
ART=ADR/'artifacts'
CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1052/law-overview-r1'
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def rel(p):return str(p.relative_to(ROOT))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

summary=read(ART/'frozen-final-summary.json')
assert summary['passed']==51 and summary['failed']==0
assert not summary['candidate_changed_during_tests'] and not summary['production_import_leaks']
candidate=read(CAND/'candidate.json');rev=candidate['revisions'][-1]
baseline=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1051/paged-clause-r1/revisions/rev-001/snapshot'
snapshot=CAND/'revisions/rev-002/snapshot'
changed=[n for n,h in summary['files'].items() if not (baseline/n).exists() or sha(baseline/n)!=h]
result={'status':'complete','scope':'synthetic implementation/API contracts only',
    'passed':51,'failed':0,'new_contracts_passed':12,'prior_progressive_contracts_passed':10,
    'external_model_calls':0,'answer_accuracy':None,'token_reduction':None,
    'candidate_revision_sha256':rev['revision_sha256'],'changed_files':changed,
    'runtime_import_leaks':{},'tested_files_unchanged':True,
    'law_directory':'all authorized matching laws with separately verified single-term matches; no body',
    'article_page':'up to20 globally, existing law rank then within-law article rank; more via existing NEXT_LAWS action',
    'observed_synthetic_case':{'matching_laws':4,'article_pages':[20,4],'missing_or_duplicate_articles':0},
    'existing_experiment':'not modified or resumed; previous cell44 whitespace stall remains',
    'main_unchanged':True,'genos_unchanged':True}
save(ART/'result.json',result)
m=read(ADR/'실험/manifest.json');plan=read(ART/'implementation-plan.json')
m['lineage']['hypothesis_delta']=plan['hypothesis']
d=m['design'];d.update(hypothesis=plan['hypothesis'],primary_metric='Scoped law overview, article pagination, source/state/permission and native API contracts',
    success_criteria='; '.join(plan['success_criteria']),failure_criteria='Missing matching law, fabricated hit term, over20 search article cards, lost page, unauthorized original or state/budget bypass',
    criteria_frozen_before_run=True,criteria_record={'path':rel(ART/'implementation-plan.json'),'sha256':sha(ART/'implementation-plan.json')},failure_recovery=plan['failure_contract'])
d['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{
    'candidate_id':'law-overview-r1','arm_id':'overview','experiment_id':m['experiment_id'],
    'run_ids':['run-001'],'manifest_path':rel(CAND/'candidate.json'),'manifest_sha256':sha(CAND/'candidate.json'),
    'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],
    'runner_path':'06_TOOLS/EXPERIMENTS/adr_1052/validate_candidate.py',
    'runner_sha256':sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_1052/validate_candidate.py')}])
d['arms'][0].update(changes='ADR1051 frozen implementation reference only; previous contract tests retained',controls='No paired live evaluation, no baseline mutation')
d['arms'][1].update(changes='All matching laws with true term hits; separate article pages20 and selected clause reading',controls='Same source/ACL/hash/state and total budgets; no model calls')
m['runs'][0].update(arm_ids=['overview'],selection_rule='Small sequential synthetic fixtures and API; criteria saved before implementation; no live corpus comparison',status='complete',artifact_path=rel(ART/'result.json'),sha256=sha(ART/'result.json'),executed_arm_ids=['overview'])
m['llm_policy']['llm_calls']=[]
test=snapshot/'05_TESTS/CONTRACTS/test_law_overview_adr1052.py'
m['dataset'].update(name='Synthetic law and article navigation fixtures',version='law-overview-twenty-v1',frozen_source=rel(test),sha256=sha(test))
reason='Implementation/API tests only. Candidate changes presentation and pagination, but no real corpus/model recall, quality or cost comparison was run.'
m['retrieval_accounting']['not_applicable_reason']=reason
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
m['results'].update(status='complete',by_arm={
    'baseline':{'status':'complete','correct':None,'total':0,'accuracy':None,'reason':'Frozen implementation reference only; not a paired evaluation arm'},
    'overview':{'status':'complete','correct':None,'total':0,'accuracy':None,'contract_passed':51,'contract_failed':0}},
    comparisons=[],judge_disagreements=None,usage={'physical_calls':0,'input_tokens':0,'output_tokens':0},latency={'model_latency':None},
    error_taxonomy=['Initial new page cursor rejected by old tool availability; wired to bound global article page.',
        'Synthetic fused entry fixture used obsolete intent fields; corrected fixture without loosening runtime validation.',
        'Term discrimination fixture initially searched only approval; corrected input to approval/exception.'])
save(ADR/'실험/manifest.json',m)
art=read(ART/'manifest.json');art['files']=[]
for p in sorted(ART.iterdir()):
    if p.is_file() and p.name!='manifest.json':art['files'].append({'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Preserved synthetic validation artifact','contains_raw_prompts_and_outputs':False})
save(ART/'manifest.json',art)
print(json.dumps({'passed':51,'failed':0,'revision_sha256':rev['revision_sha256'],'changed_files':changed},ensure_ascii=False))
