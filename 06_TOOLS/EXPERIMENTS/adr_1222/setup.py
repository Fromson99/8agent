from common import *
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1206-domain-profile-real-records'
m=read(ADR/'실험/manifest.json');active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==121
working={n:sha(ROOT/n) for n in release['files']};assert all(sha(ROOT/release['code_root']/n)==h for n,h in release['files'].items())
data=ROOT/release['data_path'];meta=read(data/'manifest.json')
put(DES/'baseline.json',{'active':active,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release_sha256':sha(ROOT/active['manifest_path']),'release':release,'working_files':working,'data_path':release['data_path'],'generation_manifest_sha256':sha(data/'manifest.json'),'data_binding':meta,'authorization_path':'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json','authorization_sha256':sha(ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json')})
for name in ('cases.json','originals.json'):raw(DES/name,read(parent/'artifacts/design'/name))
put(ART/'evaluation-only/expectations.json',read(parent/'artifacts/evaluation-only/expectations.json'))
criteria=read(parent/'artifacts/design/criteria.json')
criteria.update(user_request='남은 상태·참조 불일치랑 입력 구간 누락도 수정하고, 정규화부터 누적까지 다시 실험해봐',hypothesis='Use unchanged validated normalization from1220; explicit graph namespaces, request-bound provenance/deletion schema and unchanged compiler inside existing repair allow two accumulation drafts and previews.',changes='Candidate: exact ADR1221 frozen487 with request-bound coverage/locator assembly and unchanged original canonical validator/profile; same authoring transport, existing Qwen ExperimentClient supplies external policy routing. The authoring HTTP endpoint is substituted only in the explicit research runner; original response parsing, schema generation/projection, validation and repair owner remain selected product code.',historical_comparison='Exactly saved normalized records from1220, same two raw subtrees, five public units and glossary as ADR1206; historical failure is diagnostic only, not a paired causal speed/quality baseline.',resource_limits={'startup_available_GiB':5,'running_available_GiB':3,'worker_rss_GiB':4,'process_address_space_GiB':6,'workspace_free_GiB':20,'swap_growth_MiB':128,'global_swap_is_host_metric':True},stop_rule='One predeclared batch only. Never retry UNKNOWN or resource stop. Format/known provider failures may allow the other independent normalization as predeclared; dependent accumulation stays NOT_RUN. No schema/prompt/output edits after results.')
criteria['success_criteria'] += ['Actual authoring uses strict=true; wire expands to request-bound schema with equivalent REF spelling; original model proposal persists and canonical assembly hash/raw-index hash and original validator are verified','Selected487 MAIN121 product bytes remain exact until separate technical integration; known provider switch only once, within5 physical continuation total; prior batch4 plus continuation<=9; no outside product imports or operating DB writes']
criteria['continuation']='No new NORMALIZE call. Copy1220 isolated store/DB read-only, validate original two canonical normalized observations before accumulating. Original JOB failures remain. New candidate producer/prompt/schema gives distinct job identity.'
criteria['maximum_physical_calls']=5
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1220-normalization-accumulation-live/artifacts/live'
paths=[prior/'work.sqlite']+[p for p in (prior/'objects').rglob('*') if p.is_file()]+[prior/n for n in ['binding.json','saved-007-a-status.json','saved-007-b-status.json','execution.json']]
put(DES/'continuation.json',{'source':str(prior.relative_to(ROOT)),'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'binding':read(prior/'binding.json'),'observations':[read(prior/f'saved-007-{c}-status.json')['observation'] for c in ('a','b')]})
put(DES/'criteria.json',criteria)
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Real structured stage completion, exact strict-schema transport and original source-bound acceptance; latency/tokens descriptive only',success_criteria=criteria['success_criteria'],failure_criteria=criteria['failure_criteria'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')},execution=criteria,arms=[{'id':'baseline','role':'baseline','derived_from':['ADR-1218-experiment-v1/compatible'],'changes':'Historical ADR1206 failure and current selected MAIN120 technical checks only; no new baseline calls','controls':'Same stored raw subtrees/public units; no historical outputs changed'},{'id':'graph-refs','role':'candidate','derived_from':['baseline'],'changes':criteria['changes'],'controls':'Same original profile/model/data/glossary/budgets; no gold or analyst hints in product context'}])
m['runs'][0].update(arm_ids=['graph-refs'],selection_rule=criteria['selection'],artifact_path=str((RUN/'result.json').relative_to(ROOT)))
pm=read(parent/'실험/manifest.json');m['llm_policy']=pm['llm_policy'];m['dataset']={**pm['dataset'],'frozen_source':str((DES/'cases.json').relative_to(ROOT)),'sha256':sha(DES/'cases.json')};m['retrieval_accounting']=pm['retrieval_accounting']
(ADR/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
files=sorted(set(release['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'})
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
candidate=ac.snapshot(ADR,'graph-refs',files,experiment_id=m['experiment_id'],arm_id='graph-refs',run_ids=['run-001'])
source=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1221-accumulation-reference-contract/artifacts/design/freeze.json')
import shutil
for name,h in source['files'].items():
 assert sha(ROOT/source['code_root']/name)==h
 shutil.copy2(ROOT/source['code_root']/name,candidate/'snapshot'/name)
ac.freeze(candidate);assert not ac.validate(candidate),ac.validate(candidate)
v=read(candidate/'candidate.json')['revisions'][-1];C=candidate/'revisions'/v['revision_id']/'snapshot'
binding={'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
put(DES/'candidate.json',{'code_root':str(C.relative_to(ROOT)),'files':{n:sha(C/n) for n in files},'candidate_revision':binding,'selected_serving_files':487,'research_transport_files':len(files)-487})
print('Prepared MAIN121 baseline / coverage candidate:',len(files),'frozen files, candidate487 exact to technical1221; real calls0')
