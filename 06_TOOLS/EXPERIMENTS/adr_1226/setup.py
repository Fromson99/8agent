from common import *
import shutil
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1206-domain-profile-real-records'
m=read(ADR/'실험/manifest.json');active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==122 and active['release_id']=='cumulative-authoring-20261029-r1'
assert all(sha(ROOT/n)==h and sha(ROOT/release['code_root']/n)==h for n,h in release['files'].items())
assert len(release['files'])==487
meta=read(ROOT/release['data_path']/'manifest.json')
put(DES/'baseline.json',{'active':active,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release_sha256':sha(ROOT/active['manifest_path']),'release':release,'data_path':release['data_path'],'generation_manifest_sha256':sha(ROOT/release['data_path']/'manifest.json'),'data_binding':meta,'authorization_path':'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json','authorization_sha256':sha(ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json')})
for name in ('cases.json','originals.json'):raw(DES/name,read(parent/'artifacts/design'/name))
put(ART/'evaluation-only/expectations.json',read(parent/'artifacts/evaluation-only/expectations.json'))
criteria=read(parent/'artifacts/design/criteria.json')
criteria.update(user_request='재검증해봐',hypothesis='Exact selected MAIN122 including final SAME/full-graph guidance permits fresh normalization of both known raw subtrees and two source-checked accumulated revisions/previews. Exact structural success is distinct from absent-reason/purpose classification and source meaning.',changes='No product change. Exact selected487 + unchanged ExperimentClient. Fresh isolated store/namespace; all four product stages run again rather than reuse prior normalized outputs. Existing authoring parser/schema/validator/repair/compile/store remain unchanged; research bridge only substitutes external Qwen endpoint.',historical_comparison='Previous1220/1222/1224 are known development results, preserved unchanged. New normalization can differ stochastically; not a paired speed/quality causal comparison or holdout.',resource_limits={'startup_available_GiB':5,'running_available_GiB':3,'worker_rss_GiB':4,'process_address_space_GiB':6,'workspace_free_GiB':20,'swap_growth_MiB':128,'global_swap_is_host_metric':True},maximum_physical_calls=9,maximum_stage_attempts=2,maximum_batch_seconds=1800,stop_rule='One frozen batch. Same original one repair per stage. Stop UNKNOWN/resource exhaustion; never rerun completed batch. If A fails, independent B normalization may run but B accumulation requires saved A revision. No prompt/schema/product edits after observation; no approval/publication.')
criteria['success_criteria']+=['All10 raw segments accounted for and exact selected quote locators validated; no fabricated reason/purpose inferred from structure-only values','No prior nodes silently dropped with SAME; any graph deletion follows exact previous graph diff','Every actual request schema expands back to exact request-bound schema, original prompts/context exact; original provider JSON, rejected jobs, normalized records and compiled packages preserved','Selected MAIN122/working487/candidate487/data unchanged, no source/ACL/hash drift, no import leaks or operating DB writes; max9physical, one confirmed429-only provider switch']
put(DES/'criteria.json',criteria)
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Fresh normalization2 + accumulated draft revisions2 and exact compiled previews; all frozen content/absence criteria separately assessed',success_criteria=criteria['success_criteria'],failure_criteria=criteria['failure_criteria'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')},execution=criteria,arms=[{'id':'baseline','role':'baseline','derived_from':['ADR-1225-experiment-v1/authoring-contract'],'changes':'Selected MAIN122 and previous known probes; no extra baseline model calls','controls':'Same raw subtrees/public sources/glossary/model policy'},{'id':'main122','role':'candidate','derived_from':['baseline'],'changes':'Exact MAIN122 fresh four-stage revalidation; product unchanged','controls':'Original profile/validation/budgets/source data unchanged; evaluation expectations never sent'}])
m['runs'][0].update(arm_ids=['main122'],selection_rule=criteria['selection'],artifact_path=str((RUN/'result.json').relative_to(ROOT)))
pm=read(parent/'실험/manifest.json');m['llm_policy']=pm['llm_policy'];m['dataset']={**pm['dataset'],'frozen_source':str((DES/'cases.json').relative_to(ROOT)),'sha256':sha(DES/'cases.json')};m['retrieval_accounting']=pm['retrieval_accounting']
(ADR/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
files=sorted(set(release['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'})
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
candidate=ac.snapshot(ADR,'main122',files,experiment_id=m['experiment_id'],arm_id='main122',run_ids=['run-001'])
for n,h in release['files'].items():
 assert sha(candidate/'snapshot'/n)==h
ac.freeze(candidate);assert not ac.validate(candidate),ac.validate(candidate)
v=read(candidate/'candidate.json')['revisions'][-1];C=candidate/'revisions'/v['revision_id']/'snapshot'
binding={'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
put(DES/'candidate.json',{'code_root':str(C.relative_to(ROOT)),'files':{n:sha(C/n) for n in files},'candidate_revision':binding,'selected_serving_files':487,'research_transport_files':1})
print('MAIN122 working/selected/candidate487 identical; frozen488 incl transport; model0')
