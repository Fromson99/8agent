from common import *
import subprocess
DES.mkdir();OUT.mkdir()
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1271-source-goal-coordinate-recovery/artifacts'
last=read(prior/'design/freeze.json');assert all(sha(ROOT/n)==h for n,h in last['files'].items())
pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';p=read(pointer);release=read(ROOT/p['manifest_path'])
assert p['generation']==130
put(DES/'baseline.json',{'pointer':p,'pointer_sha256':sha(pointer),'release':release,
 'working_files':{n:sha(ROOT/n) for n in last['files']},'gold_binding':read(GOLD/'binding.json'),
 'gold_files':{str(x.relative_to(ROOT)):sha(x) for x in GOLD.iterdir() if x.is_file()}})
criteria={'hypothesis':'The complete current serving implementation can be selected as one immutable MAIN release without dropping loop recovery, source review, workspace publication/retraction, or MAIN130 persistence compatibility.',
 'success':['Every served byte equals the frozen current working candidate','Current 641 loop checks and 3 actual Qwen recovery cases bind to identical code','Workspace existing contracts and native publication/retraction/UI checks pass','Official preview and prepare inventory includes all current serving modules and exact delta','Selected default service HEALTH and native loop API tests pass after cutover','Gold connector points to the same MAIN engine while query release, mappings and source data remain unchanged'],
 'failure':['Changed source/schema/permissions/underlying data','Missing candidate dependency or stale release hash','New contract or selected consumer failure'],
 'authorization':'지금까지 된거 메인에 싹다 반영해',
 'decision':'Explicit user-directed local MAIN cutover. Preserve in-sample/failed live results; no independent legal-quality or Oracle workspace end-to-end claim.',
 'new_model_calls':0,'oracle_writes':0,'data_generation_changes':0,'genos_deploy':False,'git_push':False,
 'rollback':'Restore preserved MAIN130 pointer through official rollback; keep layout4 reader and new historical records; restore prior Gold engine binding. Workspace consumers revert to prior release behavior, no data deleted.'}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['integration'].update(result_arm='integrated',rationale='User requested all completed working serving changes after the verified agent-loop work.',common_invariants=['Originals, ACL, source/claim checks, request budgets, UNKNOWN no-replay','MAIN130 Oracle layout4 and NFS diagnostics boundary','Existing data generation and Gold query release unchanged'],no_conflict_reason='The current 518-file closure already contains the merged source-review and loop/workspace bytes. No parent snapshot is copied over the workspace; exact current hashes are selected.',rollback_ref='ADR-1271-experiment-v1/repaired')
for item in m['integration']['parent_contributions']:
 item.update(adopted='Current byte-identical implementation and its preserved verification receipts',excluded='Historical failures, missing quality claims, experiment-only adapters and discarded candidate-only changes are not promoted as successful results')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact serving closure and consumer contract preservation',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence=bind(DES/'criteria.json'))
m['design']['arms'][0].update(changes='Current MAIN130 release and completed parent receipts, no new baseline model',controls='Same production generation, Gold query release, profile flags and storage policy')
m['design']['arms'][1].update(changes='Select all current serving work including loop/source review/workspace',controls='No new implementation, prompt, data or model policy changes; quality not certified')
m['runs'][0].update(arm_ids=['integrated'],selection_rule='Exact current serving closure; inherited 641 and actual Qwen3 with hash match; fresh workspace and selected API consumers',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[]
m['dataset'].update(name='Current source generation and synthetic consumer contract fixtures',version='20261102-main131',frozen_source=str((DES/'baseline.json').relative_to(ROOT)),sha256=sha(DES/'baseline.json'),legal_version_checked=False,reference_version_checked=False)
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Release selection and contract audit, no retrieval effect measurement',stage_ledger={'mode':'not_applicable','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':None,'artifact_path':None,'sha256':None,'not_applicable_reason':'No retrieval benchmark; inherited actual results remain separate'})
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(ADR,'integrated',list(last['files']),experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'])
ac.freeze(C);assert not ac.validate(C),ac.validate(C)
revision=read(C/'candidate.json')['revisions'][-1];S=C/'revisions'/revision['revision_id']/'snapshot'
files={n:sha(S/n) for n in last['files']};assert files==last['files']
pin={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256']}
put(DES/'freeze.json',{'code_root':str(S.relative_to(ROOT)),'files':files,'candidate_revision':pin,'pointer_sha256':sha(pointer),'prior_verified':bind(prior/'design/freeze.json'),'criteria':bind(DES/'criteria.json')})
tests=read(prior/'working-full-recovery-002/result.json');actual=read(prior/'run-001/result.json')
assert tests['passed']==641 and tests['failed']==0 and tests['code_unchanged'] and actual['fault_cases_passed']==3
put(DES/'inherited-verification.json',{'code_identity_all518':True,'tests':bind(prior/'working-full-recovery-002/result.json'),'passed':641,'live':bind(prior/'run-001/result.json'),'actual_qwen_fault_cases_passed':3,'new_model_calls':0,'no_legal_quality_claim':True})
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(pin,candidate_id='integrated',experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'],runner_path=str((Path(__file__).parent/'prepare.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).parent/'prepare.py'))]);put(ADR/'실험/manifest.json',m)
put(DES/'preview-authorization.json',{'purpose':'integration_preview'})
put(DES/'preview-validation.json',{'structural_checks_passed':True,'basis':'Inherited fixed-code641 and actual Qwen3; final workspace/consumer checks still pending'})
with (ART/'preview.log').open('x') as log:
 subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(S),'--generation',release['data_path'],'--release-id',RELEASE+'-preview','--authorization',str(DES/'preview-authorization.json'),'--validation',str(DES/'preview-validation.json'),'--integration-preview',str(DES/'integration-preview.json')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
declaration=read(DES/'integration-preview.json');stage=dict(release['files'])
for row in declaration['changes']:
 if row['after'] is None:stage.pop(row['path'])
 else:stage[row['path']]=row['after']
 for_pattern=row['path']
 row['reason']='Current complete serving work authorized by user: '+('engine dependency binding' if '/ENGINES/' in for_pattern or for_pattern=='00_SYSTEM/PIPELINE.json' else 'workspace authoring/publication/revocation' if '/ontology_work/' in for_pattern or 'ontology_' in for_pattern else 'agent loop/source review recovery')
assert all(files.get(n)==h for n,h in stage.items())
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':p['release_manifest_sha256'],'candidate':pin,'staged_files':stage,'excluded_candidate_paths':{n:'Unregistered auxiliary engine or research-only adapter/tool; outside official serving closure, retained in working code' for n in set(files)-set(stage)}})
declaration.update(candidate=pin,rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',declaration)
put(DES/'stage.json',{'files':stage,'count':len(stage),'changed':len(declaration['changes']),'added':[x['path'] for x in declaration['changes'] if x['before'] is None],'removed':[x['path'] for x in declaration['changes'] if x['after'] is None]})
print('Frozen',len(files),'candidate files; serving',len(stage),'changed',len(declaration['changes']))
