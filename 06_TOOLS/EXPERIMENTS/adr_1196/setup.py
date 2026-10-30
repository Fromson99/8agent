from common import *
import shutil
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');base=read(ROOT/active['manifest_path'])
assert active['generation']==116
criteria={'scope':'Preserve accepted answer content through final display; no new legal semantic certification',
 'success':['New accepted-content-v1 profile renders accepted claim text without another model rewrite',
 'All subject/scope/condition tree/norms/numeric bases/exceptions preserved by existing verified content compiler',
 'Paragraphs, requested table and bullets use deterministic complete content; no arbitrary replacement text',
 'Existing narrative-v1 stored publications and explicit legacy profiles retain exact compatibility',
 'Native API exercises no COMPOSE call, duplicate publication, complete final streaming and failure before publication',
 'Existing regression outcomes unchanged; ACL/source/claim/hash/state/limits/provider contracts retained',
 'Working targeted changes and selected local release verify identical products with preserved unrelated changes'],
 'failure':'New regression, missing accepted content, stale receipt or early unverified output blocks qualification',
 'external_model_calls':0,'quality_certified':False,'performance_certified':False,
 'resources':{'max_parallel_heavy_processes':1,'min_available_GiB':5,'address_space_GiB':6},
 'failure_contract':{'cause':'Free prose rewrite can omit content while retaining claim IDs',
 'owner':'COMPOSE deterministic rendering', 'correction':'No semantic rewrite or retry; use validated ASSESS compiled claims and hash-bound rendering',
 'invalid':'Stale or mutated assessment/plan/source fails before publishing; no fallback to an unverified draft',
 'preserved':'ASSESS repair/research/limited-answer policy, raw failures, budgets, gaps, originals and previous stored publications'},
 'known_case_replay':'ADR1195 saved ASSESS/COMPOSE render only; in-sample diagnostic excluded from qualification',
 'regression':'Same existing 211-node suite on MAIN116 and candidate; exact outcomes compared'}
put(DES/'criteria.json',criteria)
put(DES/'baseline.json',{'active':active,'manifest':base,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_files':{n:sha(ROOT/n) if (ROOT/n).is_file() else None for n in base['files']}})
put(DES/'preparation-notes.json',{'reservation_first_attempt':'Unsupported relationship diagnoses rejected before creation; informed_by accepted. No product change or call before reservation.'})
m=read(ADR/'실험/manifest.json');h='Server assembly preserves every accepted claim without a lossy free-form COMPOSE rewrite.'
m['lineage']['hypothesis_delta']=h
m['design'].update(hypothesis=h,primary_metric='Deterministic preservation and native consumer contracts',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence=bind(DES/'criteria.json'),execution=criteria,arms=[{'id':'preserved','role':'candidate','derived_from':['ADR-1194-experiment-v1/integrated'],'changes':'Versioned accepted-content rendering and selected profile','controls':'MAIN116 data/model/retrieval/provider/budgets/assessment unchanged'}])
m['dataset'].update(name='Prospective content preservation and native API contracts',version='v1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'))
m['llm_policy']['llm_calls']=[]
m['runs'][0].update(arm_ids=['preserved'],selection_rule='Prospective synthetic contracts and same existing regression; saved CM007 excluded from eligibility',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['retrieval_accounting']['not_applicable_reason']='Rendering contract only; no retrieval benchmark'
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']='Synthetic native API; no retrieval effect claim'
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(ADR,'preserved',list(base['files']),experiment_id=m['experiment_id'],arm_id='preserved',run_ids=['run-001']);S=C/'snapshot'
for n,h in base['files'].items():
 assert sha(ROOT/base['code_root']/n)==h,n
 shutil.copyfile(ROOT/base['code_root']/n,S/n)
put(DES/'candidate.json',{'root':str(C.relative_to(ROOT)),'snapshot':str(S.relative_to(ROOT))})
print(S)
