from common import *
import shutil
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');base=read(ROOT/active['manifest_path']);assert active['generation']==113
criteria={'scope':'Item4 only; requirement coverage in existing ASSESS, no extra model stage or legal truth claim',
 'requirements':['Every server-bound request part and original issue appears in explicit requirement rows; full request preserved independent of early issue selection',
 'SATISFIED references actual same-issue claims and current verified evidence; EXCLUDED binds current originals or literal current-user scope quote; prose alone insufficient',
 'UNRESOLVED references material gaps; existing reentry handles unknown locators and concrete targets; failed judgment never blocks independent valid original investigation',
 'One existing ASSESS repair only; errors specific; resume and duplicates retain journal, budget and deadline; stale cached reviews rejected',
 'Existing source goals, limited publication, ontology inputs and claim validation remain; ontology shortcut cannot bypass requirement review',
 'No article/document hardcoding; no resource guard/memory/cancellation changes; no new live model calls',
 'Synthetic contracts incl native API, existing regression comparison; preserve concurrent storage changes during narrow working integration'],
 'failure':'New evidence/ACL/state/budget/recovery regressions, hidden missing requirement, or unexpected model call blocks adoption',
 'resources':{'heavy_processes':1,'start_free_GiB':5,'rss_limit_GiB':4,'address_space_GiB':6,'disk_min_GiB':20},
 'quality_certified':False,'external_model_calls':0}
put(DES/'criteria.json',criteria)
put(DES/'baseline.json',{'active':active,'manifest':base,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
 'working_files':{n:sha(ROOT/n) if (ROOT/n).is_file() else None for n in base['files']}})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']='Request coverage with evidence/gap links prevents structurally unsupported sufficiency without hardcoded sources or extra planning calls.'
m['design'].update(hypothesis=m['lineage']['hypothesis_delta'],primary_metric='Prospective technical requirement/evidence/state contracts',success_criteria=criteria['requirements'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence=bind(DES/'criteria.json'),execution=criteria,arms=[{'id':'reviewed','role':'candidate','derived_from':['ADR-1186-experiment-v1/integrated'],'changes':'Structured requirement review in existing assessment and bounded recovery','controls':'Same MAIN113 data/model/budgets; synthetic fixtures only'}])
m['dataset'].update(name='Independent synthetic requirement and native API contracts',version='v1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'))
m['llm_policy']['llm_calls']=[];m['runs'][0].update(arm_ids=['reviewed'],selection_rule='Prospective synthetic technical contracts; no CM live rerun or legal quality scoring',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Synthetic state and API contracts, no real-corpus retrieval effectiveness measurement',stage_ledger={'mode':'not_applicable','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','artifact_path':None,'sha256':None,'not_applicable_reason':'No legal retrieval benchmark'})
m['design']['retrieval_stage_plan']={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{}}
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(ADR,'reviewed',list(base['files']),experiment_id=m['experiment_id'],arm_id='reviewed',run_ids=['run-001'])
S=C/'snapshot'
for n,h in base['files'].items():
 assert sha(ROOT/base['code_root']/n)==h,n
 shutil.copyfile(ROOT/base['code_root']/n,S/n)
put(DES/'candidate.json',{'root':str(C.relative_to(ROOT)),'snapshot':str(S.relative_to(ROOT))})
print(S)
