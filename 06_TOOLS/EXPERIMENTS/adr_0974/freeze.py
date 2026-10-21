"""Freeze comparison, code, cases, tests, and criteria before the first model call."""
from common import *
import sys,copy
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
s=read(ART/'stage.json');assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['base_pointer']
assert all(sha(ROOT/n)==h for n,h in s['working_baseline'].items())
assert read(ART/'fixture-preflight.json')['passed']
for cid in ('set-20','set-28'):
    for arm in ('baseline','candidate'):
        r=read(ART/'harness-preflight'/cid/arm/'result.json')
        assert r['error'] is None and r['model_calls']==0 and len(r['blocks'])==5,(cid,arm,r['error'])
m=read(ADR/'실험/manifest.json');m['decision_eligible']=True
m['lineage']['hypothesis_delta']='Preserve explicit scope/bounds and clarify original-reading versus applicability assumptions after the single semantic miss in completed ADR0973.'
m['design'].update(hypothesis='The existing typed set contract expresses novel ranges, unions and exclusions at entry and compact navigation, preserving exact original blocks.',
 primary_metric='Exact requested original block set after one native structured decision plus its bounded repair and actual READ; not complete legal-answer quality.',
 success_criteria='Candidate >=29/32 exact block sets or safe negative outcomes, and >=baseline. All four exclusion cases, two single-node controls, two fact-not-exclusion cases and multi-document case must pass. No extra blocks in any successful nonempty candidate response; missing endpoints and empty selections must never return originals. All source-byte/ACL/hash/state checks hold; all frozen applicable contracts pass; same staged/working/selected files and native service consumer pass. No quality override.',
 failure_criteria='Any excluded/extra original accepted, candidate below threshold, single/fact/multidocument regression, source/ACL/hash/state violation, new contract failure or unqualified selected-service binding blocks promotion.',
 criteria_frozen_before_run=True,
 native_consumer_scope='Actual service HEALTH and exact selected helper/code/profile/data manifest binding under2GiB address space. Original READ/ACL/state/duplicate paths use exact candidate synthetic API and model trials. No full local corpus loaded concurrently with existing embedding job.',
 sampling='32 fresh developer-authored expressions over two synthetic documents. Different numbers and parents from development fixtures. One planning decision plus existing bounded repair, followed by exact tool READ. Compact cases start in an open-document metadata window. No answer generation or adaptive model retry.',
 exposure='Developer-authored holdout is separated from prior fixtures, not statistically independent user traffic. No actual internal document is sent. Tests of the structure contract are not end-to-end legal quality certification.',
 preexisting_work='Previously implemented natural-language routing cleanup and set selection are both candidate changes. Baseline is byte-identical selected MAIN98. No unrelated serving differences.',
 call_order='Odd baseline then candidate; even candidate then baseline. One run, no repeat or majority vote.',
 budget={'physical_calls_per_trial':2,'total_physical_calls':128,'trial_seconds':180,'process_seconds':240,'experiment_seconds':7200,'peak_rss_bytes':1024**3,'minimum_available_ram_bytes':3*1024**3,'parallel_trial_processes':1},
 recovery={'owner':'native output_contract.bounded_decision','attempts':2,'transport_retries':0,'schema_failures':'one bounded repair with same view and specific error','scope_resolution_failures':'explicit unresolved, no fabricated READ','repeated_conflict':'preserve error, no extra trial','partial_output':'never counted as successful read','source_acl_hash':'hard failure, not model-repairable'})
m['design']['arms'][0].update(changes='Control restored to exact selected MAIN98/ADR0967 integrated, the ancestor of parent ADR0973; it does not inherit the parent candidate changes',controls='Same corpus, model, profile, call budget and read consumer')
m['design']['arms'][1].update(changes='Parent ADR0973 candidate plus separate reading/applicability instructions, paired examples and field descriptions;419 exact serving files',controls='No product change after freeze; no question regex added')
stages=[{'stage_id':'corpus','kind':'source','parent_stage_ids':[]},{'stage_id':'selected','kind':'select','parent_stage_ids':['corpus']},{'stage_id':'read','kind':'present','parent_stage_ids':['selected']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:copy.deepcopy(stages) for a in ('baseline','candidate')}
m['llm_policy']['llm_calls']=[{'role':'request-entry-or-compact-navigation','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0}]
def bound(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
m['dataset']={'name':'Fresh read-scope and fact separation holdout','version':'fact-separated-set-selection-v1','frozen_source':str((ART/'cases.json').relative_to(ROOT)),'sha256':sha(ART/'cases.json'),'legal_version_checked':True,'reference_version_checked':True,'version_scope':'Synthetic stored coordinates only, not actual law','documents':bound(ART/'documents.json'),'grading_only':bound(ART/'grading-only.json')}
m['runs'][0].update(selection_rule=m['design']['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['retrieval_accounting'].update(changed=True,corpus_total=8,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
isolation=m['design']['code_isolation'];isolation.update(mode='candidate_snapshot',reason=None,candidates=[])
save(ADR/'실험/manifest.json',m)
paths=read(ART/'integration-delta.json')['against_main98'];c=ac.snapshot(ADR,'candidate',paths,experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
import shutil
for n in paths:shutil.copyfile(ROOT/s['roots']['candidate']/n,c/'snapshot'/n)
ac.freeze(c);assert not ac.validate(c)
cm=read(c/'candidate.json');rev=cm['revisions'][-1];runner=Path(__file__).with_name('run_case.py')
isolation['candidates']=[{'candidate_id':'candidate','arm_id':'candidate','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((c/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(c/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(ROOT)),'runner_sha256':sha(runner)}]
m['design']['script_bindings']={str(p.relative_to(ROOT)):sha(p) for p in runner.parent.glob('*.py')}
names=['test_structural_scope_output_recovery','test_required_structure_selection','test_memory_runtime_v2','test_model_structure_selection','test_natural_language_routing','test_law_name_recovery','test_multiturn_structured_scope','test_scoped_multiturn_api','test_unattempted_gap_finish','test_assessment_source_reply','test_public_display_boundary']
m['design']['test_bindings']={f'05_TESTS/CONTRACTS/{n}.py':sha(ROOT/f'05_TESTS/CONTRACTS/{n}.py') for n in names}
m['design']['allowed_existing_failures']=read(ROOT/'04_EXPERIMENTS/ADR/ADR-0967-law-name-main-integration/실험/manifest.json')['design']['allowed_existing_failures']
m['design']['observed_prior_failure']={'path':'04_EXPERIMENTS/ADR/ADR-0973-required-structural-selection/artifacts/result.json','sha256':sha(ROOT/'04_EXPERIMENTS/ADR/ADR-0973-required-structural-selection/artifacts/result.json')}
m['design']['script_bindings']['06_TOOLS/EXPERIMENTS/adr_0972/dataset.py']=sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_0972/dataset.py')
m['questions']=[{'number':i,'case_id':c['id'],'file':f'질문-{i:03d}-{c["id"]}.md','sha256':'PENDING'} for i,c in enumerate(read(ART/'cases.json'),1)]
save(ADR/'실험/manifest.json',m);save(ART/'design-freeze.json',{'manifest_sha256':sha(ADR/'실험/manifest.json'),'design':m['design'],'dataset':m['dataset'],'stage_sha256':sha(ART/'stage.json'),'model_calls_before_freeze':0})
p=ADR/'README.md';p.write_text(p.read_text().replace('decision_eligible: false','decision_eligible: true'))
print('Frozen 32 cases, exact MAIN98 vs419 files, max128 calls; no calls yet')
