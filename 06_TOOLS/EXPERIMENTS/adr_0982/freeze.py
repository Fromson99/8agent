"""Freeze new sample, actual code and critical contracts before model execution."""
from common import *
import sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
s=read(ART/'stage.json');D=ROOT/s['candidate_dir'];C=D/'snapshot'
assert not (ART/'trials').exists() and not (ART/'known-query').exists()
ac.freeze(D);assert not ac.validate(D)
record=read(D/'candidate.json');revision=record['revisions'][-1]
tests=['test_unified_scope_semantic_authority','test_structural_scope_output_recovery',
 'test_source_span_norm','test_assessment_gap_action','test_law_name_recovery','test_assessment_source_reply',
 'test_multiturn_research_refresh','test_hierarchical_coordinate_integrity','test_legacy_division_api',
 'test_required_structure_selection','test_model_structure_selection','test_multiturn_structured_scope',
 'test_memory_runtime_v2','test_public_display_boundary','test_reference_decision_continuity','test_reference_context_continuity','test_scoped_multiturn_api','test_scoped_content_context','test_read_choice_input_preservation']
paths=[(C if (C/f'05_TESTS/CONTRACTS/{n}.py').is_file() else ROOT)/f'05_TESTS/CONTRACTS/{n}.py' for n in tests]
s['files']={'candidate':{n:sha(C/n) for n in s['base_release']['files']}}
save(ART/'stage.json',s)
m=read(ADR/'실험/manifest.json')
binding={'candidate_id':'candidate','arm_id':'candidate','experiment_id':m['experiment_id'],'run_ids':['run-001'],
 'manifest_path':str((D/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(D/'candidate.json'),
 'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256'],
 'runner_path':'06_TOOLS/EXPERIMENTS/adr_0982/run_case.py','runner_sha256':sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_0982/run_case.py')}
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[binding])
m['design'].update(test_bindings={str(p.relative_to(ROOT)):sha(p) for p in paths},
 script_bindings={str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py') if p.name in ('run_case.py','full_query.py','matcher.py','common.py','run_contracts.py','assessment_case.py')},
 known_query_diagnostic={'question':'상법에서 주주총회 특별결의요건에 대해서 알려줘','role':'in_sample_diagnostic','pass_condition':'Verified article434 and both ratios in a source-bound explanatory claim delivered to the user; an INSUFFICIENT original-excerpt-only reply is not success.','max_calls':40},
 call_order='Known query candidate diagnostic first, then h02..h17 alternating baseline/candidate order, then a1..a4 synthetic assessment decisions per arm. All sequential, one physical call and no retry per fresh case. Known service retains its native bounded repair owner.',
 retrieval_stage_plan={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{arm:[{'stage_id':'corpus','kind':'source','parent_stage_ids':[]},{'stage_id':'headings','kind':'filter','parent_stage_ids':['corpus']},{'stage_id':'metadata-output','kind':'present','parent_stage_ids':['headings']}] for arm in ('baseline','candidate')}})
m['dataset']={'name':'Fresh scope expressions and independent metadata retention fixtures','version':'unified-scope-holdout-v1','frozen_source':str((ART/'cases.json').relative_to(ROOT)),'sha256':sha(ART/'cases.json'),
 'grading_only':{'path':str((ART/'grading-only.json').relative_to(ROOT)),'sha256':sha(ART/'grading-only.json')},'documents':{'path':str((ART/'documents.json').relative_to(ROOT)),'sha256':sha(ART/'documents.json')},'legal_version_checked':True,'reference_version_checked':True,'version_scope':'same public generation; synthetic coordinates are not legal facts'}
m['in_sample']=False;m['decision_eligible']=False
m['retrieval_accounting'].update(changed=True,corpus_total=8,not_applicable_reason=None,stage_ledger={'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str((ART/'retrieval-ledger.json').relative_to(ROOT)),'sha256':'PENDING','not_applicable_reason':None})
m['llm_policy']['llm_calls']=[{'role':'request-entry','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0},{'role':'known-query-service','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0},{'role':'synthetic-assessment','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0}]
save(ADR/'실험/manifest.json',m)
save(ART/'design-freeze.json',{'manifest_sha256':sha(ADR/'실험/manifest.json'),'design':m['design'],'dataset':m['dataset'],'policy_sha256':sha(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),'assessment_data':{'cases_sha256':sha(ART/'assessment-cases.json'),'gold_sha256':sha(ART/'assessment-gold.json'),'minimum_correct':3,'total_per_arm':4,'physical_calls':8}})
print('Frozen',len(paths),'test files and 16 previously unexecuted cases; no calls yet')
