from common import *
import shutil,subprocess
DES.mkdir();OUT.mkdir()
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1274-final-review-multiturn-recovery/artifacts'
f=read(prior/'design/freeze.json');C=ROOT/f['code_root'];before=read(prior/'design/working-before.json')
tech=read(prior/'run-001/result.json');assert tech['status']=='PASS' and tech['full_recovery_contracts']==641
live=ROOT/'04_EXPERIMENTS/ADR/ADR-1277-qwen-followup-derived-context/artifacts/run-001/result.json';actual=read(live)
assert all(sha(ROOT/n)==h for n,h in before.items()) and all(sha(C/n)==h for n,h in f['files'].items())
pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';p=read(pointer);release=read(ROOT/p['manifest_path']);assert p['generation']==131
put(DES/'baseline.json',{'pointer':p,'pointer_sha256':sha(pointer),'release':release,'working_files':before,
 'gold_binding':read(GOLD/'binding.json'),'gold_files':{str(x.relative_to(ROOT)):sha(x) for x in GOLD.iterdir() if x.is_file()}})
criteria={'hypothesis':'Exact verified final-review recovery and follow-up behavior can be selected without changing data, permissions, model policy or unrelated current work.',
 'success':['Exact518 code identity to ADR1274/1277','Existing641 and new17 contracts verified; source-only is not a legal conclusion','Official serving closure and prepared API pass','Root service and Gold select identical MAIN132; original generation/mapping retained'],
 'failure':['Unverified code or new consumer failure','Gold data/schema/mapping changes','Misrepresenting failed or UNKNOWN actual model results as successful answers'],
 'authorization':'지금까지 된거 메인에 싹다 반영해; 나머지 남은 문제 해결해봐',
 'quality_certified':False,'new_model_calls':0,'oracle_calls':0,'genos_deployed':False,
 'rollback':'Official MAIN131 rollback plus saved Gold binding; preserve records and layout4 reader'}
put(DES/'criteria.json',criteria)
delta=[n for n,h in f['files'].items() if before[n]!=h]
allowed={'02_BACKEND/semantic_runtime/legal_agent/'+n for n in ('need_continuity.py','completion_execution.py','completion_contracts.py','corrected_memory.py')}
allowed.add('08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
assert all(n in allowed or n.startswith('02_BACKEND/ENGINES/') or n=='00_SYSTEM/PIPELINE.json' for n in delta)
assert len(delta)==36
# Only the reviewed delta is integrated; unchanged files and concurrent work survive.
for n in delta:shutil.copyfile(C/n,ROOT/n)
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
put(DES/'integration-applied.json',{'changed':delta,'candidate':bind(prior/'design/freeze.json'),'working_equals_tested518':True,'other_changes_overwritten':False})
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
m=read(ADR/'실험/manifest.json')
S=ac.snapshot(ADR,'selected',sorted(f['files']),experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001']);ac.freeze(S);assert not ac.validate(S)
revision=read(S/'candidate.json')['revisions'][-1];snapshot=S/'revisions'/revision['revision_id']/'snapshot'
pin={'manifest_path':str((S/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(S/'candidate.json'),'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256']}
put(DES/'freeze.json',{'code_root':str(snapshot.relative_to(ROOT)),'files':f['files'],'candidate_revision':pin,'pointer_sha256':sha(pointer)})
put(DES/'inherited-verification.json',{'technical':bind(prior/'run-001/result.json'),'actual':bind(live),'code_identity_all518':True,'full_recovery_contracts':641,'new_contracts':17,'followup_display_checks':tech['followup_display_checks'],'actual_status':actual['status'],'preserved_failed_live':'04_EXPERIMENTS/ADR/ADR-1275-qwen-final-review-followup/artifacts/run-001/result.json','quality_certified':False})
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact selected-code and consumer integrity',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence=bind(DES/'criteria.json'))
m['design']['arms'][0].update(changes='Preserved MAIN131',controls='Same source generation, Gold mapping, model policy, storage')
m['design']['arms'][1].update(changes='Verified5 product files and31 pins only',controls='Exact ADR1274/1277 code; no additional behavior changes')
m['runs'][0].update(arm_ids=['selected'],selection_rule='Official complete serving closure, inherited exact code verification and fresh API consumers',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[];m['dataset'].update(name='Existing source generation and synthetic release-consumer fixtures',version='20261102-main132',frozen_source=str((DES/'baseline.json').relative_to(ROOT)),sha256=sha(DES/'baseline.json'))
reason='Release selection audit, no retrieval effect benchmark';m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(pin,candidate_id='selected',experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'],runner_path=str(Path(__file__).relative_to(ROOT)),runner_sha256=sha(__file__))]);put(ADR/'실험/manifest.json',m)
put(DES/'preview-authorization.json',{'purpose':'integration_preview'});put(DES/'preview-validation.json',{'structural_checks_passed':True,'quality_certified':False})
with (ART/'preview.log').open('x') as log:
 subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(snapshot),'--generation',release['data_path'],'--release-id',RELEASE+'-preview','--authorization',str(DES/'preview-authorization.json'),'--validation',str(DES/'preview-validation.json'),'--integration-preview',str(DES/'integration-preview.json')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
declaration=read(DES/'integration-preview.json');stage=dict(release['files'])
for row in declaration['changes']:
 assert row['path'] in delta and row['after'] is not None
 stage[row['path']]=row['after'];row['reason']='Verified final-review recovery, explicit incomplete source reply and follow-up visibility; exact engine binding'
assert len(stage)==504 and len(declaration['changes'])==36 and all(f['files'][n]==h for n,h in stage.items())
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':p['release_manifest_sha256'],'candidate':pin,'staged_files':stage,'excluded_candidate_paths':{n:'Auxiliary engine/research dependency outside official serving closure; retained' for n in set(f['files'])-set(stage)}})
declaration.update(candidate=pin,rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',declaration)
put(DES/'stage.json',{'files':stage,'count':len(stage),'changed':36})
print('Integrated verified36, frozen518, serving504; MAIN131 still selected')
