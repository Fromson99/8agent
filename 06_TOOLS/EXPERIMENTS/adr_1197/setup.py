from common import *
import shutil
old=read(SOURCE/'design/freeze-rev-002.json');base=read(SOURCE/'design/baseline.json')
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256']
criteria={'scope':'Technical receipt correction only; unchanged1196 rev002 code and working integration; local MAIN117',
 'success':['All466 frozen bytes identical to1196 rev002','Existing116 candidate/116 working outcomes and211 regression exact receipts remain unchanged','Working integration file hashes still match, unrelated changes preserved','Previous MAIN116 reader verifies12 new-format compositions','Official release preview/rebase exactly466 tested files','No external model calls, no CM regrade or new trial','Native selected service checks after qualification'],
 'failure':'Any source evidence drift, product mismatch, failed reader compatibility or qualification blocks promotion',
 'external_model_calls':0,'quality_certified':False,
 'failure_recovery':'1196 reservation marked completed after qualifier failed due missing rollback record; final validation failed. Immutable original remains. New1197 is not a legal regrade nor a child of incomplete1196 arm. Parent is completed1194/integrated;1196 is evidence only.',
 'inherited_criteria':bind(SOURCE/'design/criteria.json'),
 'resources':{'max_parallel_heavy_processes':1,'min_available_GiB':5,'address_space_GiB':6}}
put(DES/'criteria.json',criteria);put(DES/'baseline.json',base);put(DES/'source-freeze.json',old)
evidence=[SOURCE/'check-qualified.json',SOURCE/'check-working.json',SOURCE/'regression-comparison.json',SOURCE/'working-integration.json',SOURCE/'design/integration.json',SOURCE/'design/release-rebase.json',SOURCE/'saved-render-diagnostic.json']
put(DES/'inherited-evidence.json',{str(p.relative_to(ROOT)):bind(p) for p in evidence})
m=read(ADR/'실험/manifest.json');h='Exact immutable code/test receipts can qualify deterministic accepted-content rendering despite a failed administrative completion script.'
m['lineage']['hypothesis_delta']=h
m['design'].update(hypothesis=h,primary_metric='Exact source/consumer/rollback technical receipts; no model quality metric',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence=bind(DES/'criteria.json'),execution=criteria,
 arms=[{'id':'verified','role':'candidate','derived_from':['ADR-1194-experiment-v1/integrated'],'changes':'Same six product/profile changes as1196 rev002; no additional product changes','controls':'All466 hashes exact1196, sameMAIN116 data and model policies'}])
m['dataset'].update(name='Exact existing contract evidence and previous-reader synthetic compatibility',version='v1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'))
m['llm_policy']['llm_calls']=[]
m['runs'][0].update(arm_ids=['verified'],selection_rule='Fixed technical receipts; known CM007 kept as diagnostic only',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['retrieval_accounting']['not_applicable_reason']='No retrieval change or experiment'
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']='Technical code/receipt verification only'
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(ADR,'verified',list(old['files']),experiment_id=m['experiment_id'],arm_id='verified',run_ids=['run-001']);S=C/'snapshot'
for n,h in old['files'].items():
 assert sha(ROOT/old['code_root']/n)==h,n
 shutil.copyfile(ROOT/old['code_root']/n,S/n)
put(DES/'candidate.json',{'root':str(C.relative_to(ROOT)),'snapshot':str(S.relative_to(ROOT))})
print('Frozen criteria and identical1196 candidate staged')
