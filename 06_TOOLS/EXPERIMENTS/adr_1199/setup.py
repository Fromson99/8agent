from common import *
import shutil
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');base=read(ROOT/active['manifest_path'])
assert active['generation']==117
criteria={'scope':'Supervisor routing-contract recovery and ontology domain documentation',
 'success':['A CONTINUE_TARGETED/action mismatch remains rejected and audited; an independently validated new investigative route may execute once',
 'Same-route REDIRECT, terminal proposals, malformed or unauthorized targets cannot use recovery',
 'Current presentation/source/ACL/hash/native validation and existing tool/time limits remain enforced',
 'Resume reuses bound receipt, repeated route and exhausted recovery budget cannot restart tools',
 'Actual native API reads the newly requested original, preserves prior originals and rejection history, and publishes/stores consistently',
 'Stored1198 supervisor proposal demonstrates recovery without inventing source_targets or interpreting prose',
 'Working hunk integration retains unrelated edits; MAIN117 pointer/code unchanged'],
 'failure':'Any new regression or integrity/permission/deadline bypass blocks acceptance',
 'external_model_calls':0,'quality_certified':False,'performance_certified':False,
 'resources':{'max_parallel_heavy_processes':1,'min_available_GiB':5,'address_space_GiB':6},
 'failure_contract':{'cause':'CONTINUE_TARGETED with a different valid research action',
 'owner':'investigation_supervisor.gate','correction':'Reject directive; independently validate and authorize only the concrete new nonterminal I/O route, never legal sufficiency',
 'budget':'At most two distinct recovery routes per request inside existing two supervisor calls; no extra model retry, time/tool budget or finalization reserve',
 'invalid':'Malformed, stale, unauthorized, terminal or repeated proposals use existing unresolved handoff',
 'preserved':'Original response, rejection reason, remaining_scope, originals, prior judgments, used budget and source-goal receipts'},
 'known_case':'Saved1198 response is diagnostic only; no new live CM007/009 or model comparison',
 'main':'Working integration only; no active release promotion or GENOS deployment'}
put(DES/'criteria.json',criteria)
put(DES/'baseline.json',{'active':active,'manifest':base,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_files':{n:sha(ROOT/n) if (ROOT/n).is_file() else None for n in base['files']}})
m=read(ADR/'실험/manifest.json');h='Reject inconsistent supervisor directives while independently executing a verified new source-investigation route.'
m['lineage']['hypothesis_delta']=h
m['design'].update(hypothesis=h,primary_metric='Recovery, integrity and native API contracts',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence=bind(DES/'criteria.json'),execution=criteria,arms=[{'id':'recovered','role':'candidate','derived_from':['ADR-1197-experiment-v1/verified'],'changes':'Supervisor independent routing recovery','controls':'MAIN117 model/data/prompts/source goals/budgets/final rendering unchanged'}])
m['dataset'].update(name='Prospective recovery contracts and saved1198 diagnostic',version='v1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'))
m['llm_policy']['llm_calls']=[]
m['runs'][0].update(arm_ids=['recovered'],selection_rule='Synthetic contracts plus saved1198 diagnostic; no legal scoring',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['retrieval_accounting']['not_applicable_reason']='Control-flow recovery contracts, not a retrieval benchmark'
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']='Synthetic originals acquired through native API; saved proposal replay has no full corpus execution'
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(ADR,'recovered',list(base['files']),experiment_id=m['experiment_id'],arm_id='recovered',run_ids=['run-001']);S=C/'snapshot'
for n,h in base['files'].items():
 assert sha(ROOT/base['code_root']/n)==h,n
 shutil.copyfile(ROOT/base['code_root']/n,S/n)
put(DES/'candidate.json',{'root':str(C.relative_to(ROOT)),'snapshot':str(S.relative_to(ROOT))})
print(S)
