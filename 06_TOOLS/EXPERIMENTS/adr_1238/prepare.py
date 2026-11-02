from common import *
import shutil
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');manifest=read(ROOT/active['manifest_path'])
assert active['generation']==123 and active['release_id']=='source-semantics-20261030-r1'
assert all(sha(ROOT/n)==h and sha(ROOT/manifest['code_root']/n)==h for n,h in manifest['files'].items())
gold={str(p.relative_to(ROOT)):sha(p) for p in GOLD.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
put(DES/'baseline.json',{'active':active,'manifest':manifest,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_files':manifest['files'],'gold_files':gold,'gold_binding':read(GOLD/'binding.json'),'mapping':read(GOLD/'ACTIVE_MAPPING.json')})
criteria={'hypothesis':'Preserve incomplete conflict/opinion visibility and unknown supervisor stop; integrate verified Gold source rebind/claim namespace repairs into the selected MAIN123 successor and bind Gold to that same qualified engine.',
'success':['Incomplete final review exposes prior needs, conflicts and judgments without inventing resolutions; limitation projection is idempotent','UNKNOWN supervisor propagates typed failure, preserves pending and prevents subsequent/final calls, including resume; valid directives and known validation handoff remain supported','Gold two repairs pass positive and negative exact source/namespace tests on the unpatched candidate','All current MAIN123 files preserved except four scoped product modules and exact inventory pins; data/model/profile default unchanged','Gold connector imports the qualified selected release directly, verifies all hashes before import, rejects stale selection/dirty process, and applies no runtime patches','Actual read-only Gold mapping/preflight/source/terms/vector/ontology with current VCTR_SCTN_ID and DTLS pass; no content changes','Candidate and actual selected service health/contracts match; no new existing regression'],
'failure':'New regression, hidden retry, conflated semantic resolution, ACL/source/anchor/hash weakening, selected engine mismatch or baseline clobber',
'external_model_calls':0,'quality_certified':False,'real_e2e':False,'boundaries':'No legal correctness or provider blank output cure claimed. Repeated NEED_TARGET_INCOMPLETE remains rejected; no source-only success substitution.'}
put(DES/'criteria.json',criteria)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
m=read(ADR/'실험/manifest.json')
ac.snapshot(ADR,'integrated',list(manifest['files']),experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'])
paths=[str(GOLD.relative_to(ROOT)/n) for n in ('connect.py','physical_mapping.py')]
ac.snapshot(ADR,'gold-port',paths,experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'])
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Deterministic contract preservation and exact selected engine/Gold port binding',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms'][0].update(changes='MAIN123 plus separately patched MAIN120 Gold port; current R18 mapping',controls='Source/data/model/ACL/validators fixed; no live model calls')
m['design']['arms'][1].update(changes=criteria['hypothesis'],controls='Same source/data/model/ACL, four product modules and connector binding only')
m['lineage']['hypothesis_delta']=criteria['hypothesis']
i=m['integration'];i.update(result_arm='integrated',rationale=criteria['hypothesis'],common_invariants='Exact source bytes/ACL/versions; retained judgments and need targets; fixed budgets and model; no database content changes',no_conflict_reason='Gold patch bases are byte identical to MAIN123 for both modified modules; supervisor and incomplete-review projection are independent scoped changes.')
i['parent_contributions'][0].update(adopted='Full MAIN123 serving inventory including source semantics and need continuity',excluded='No earlier failed live result adopted as success')
i['parent_contributions'][1].update(adopted='Two deterministic source-reference and output-claim namespace repairs',excluded='Runtime exec overlays and MAIN120 engine pin; failed live inference retained as failure')
put(ADR/'실험/manifest.json',m)
print('Baseline489 verified; criteria frozen; integrated and Gold connector candidates created')
