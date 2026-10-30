from pathlib import Path
import json,hashlib,sys,shutil,datetime
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1232-gold-connected-live-revalidation';D=A/'artifacts/design';O=A/'artifacts/run-001';P=R/'04_EXPERIMENTS/ADR/ADR-1214-gold-main120-engine-implementation';D.mkdir(parents=True);O.mkdir()
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
b=read(R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/binding.json');m=read(A/'실험/manifest.json');pm=read(P/'실험/manifest.json')
for n in ['cases.json','documents.json']:shutil.copy2(P/'artifacts/design'/n,D/n)
auth=read(P/'artifacts/design/authorization.json');auth['continuation_request']={'text':'이거 계속확인하고 싶음','session_id':m['reservation']['session_id'],'scope':'New frozen CM009 then CM007 once each, same endpoint/providers/question/source scope, no automatic same-case retry','previous_approval_path':str((P/'artifacts/design/authorization.json').relative_to(R)),'previous_approval_sha256':sha(P/'artifacts/design/authorization.json')};put(D/'authorization.json',auth)
criteria={'hypothesis':'The unchanged final rev036 Gold adapter on fixed MAIN120 can now complete fresh real CM009 and CM007 requests beyond the former connector and SQL-budget stops. Answer issuance, source fidelity, and semantic completeness are evaluated separately.','order':['cm-009','cm-007'],'repetitions_per_case':1,'limits':{'sql_per_case':10000,'physical_model_per_case':40,'tools_per_case':1024,'seconds_per_case':1800,'minimum_available_GiB':3,'maximum_RSS_GiB':5,'maximum_worker_swap_MiB':128,'maximum_host_swap_growth_MiB':128,'minimum_disk_GiB':80},'success_criteria':['Both fresh native API requests issue nonempty final answers within unchanged budgets','Engine487 and adapter rev036 hashes match before and after; scoped21 sources and exact quote validation retained','Actual requests/responses, canonical views, failed proposals, SQL and journal preserved; no corpus SQLite fallback','Review final claims against actually delivered original source; separately report omitted conditions, duties and exceptions without automatic legal certification'],'failure_criteria':['No final answer or exceeded original budget','UNKNOWN or resource/integrity/ACL violation stops remaining batch; preserve partial state','Any source/hash mismatch, source fabrication, engine/DB/pointer mutation'],'historical_comparison':'Previous failed actual runs and saved-response replays are historical only; no paired speed or quality causality claimed. No prompt or data change after results.','authorization':auth['continuation_request'],'source_scope':auth['explicit_external_approval'],'product_changes':'None. Only research output paths, lossless recording, and resource sampling differ. No model/provider recovery change.','quality_certified':False}
put(D/'criteria.json',criteria);put(D/'before.json',{'active_pointer':read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'active_pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'connector_binding_sha256':sha(R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/binding.json'),'parent_manifest_sha256':sha(P/'실험/manifest.json'),'existing_whitespace_failure':'02_BACKEND/semantic_runtime/legal_agent/wire_schema.py:99 trailing whitespace; unrelated working change retained','graph_errors_before':16})
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Actual final answer issuance 0..2; source/citation and semantic review separately',success_criteria=criteria['success_criteria'],failure_criteria=criteria['failure_criteria'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((D/'criteria.json').relative_to(R)),'sha256':sha(D/'criteria.json')},execution=criteria)
m['design']['arms'][0].update(changes='Historical ADR1214 failed actual runs and post-fix replay, no extra baseline dispatch',controls='Same MAIN120, 21document Gold publication, model profile and budgets')
m['design']['arms'][1].update(changes='Fresh full actual inference using unchanged final rev036 adapter',controls='Same product code, model policy, data, budgets; fresh request journal per case')
m['runs'][0].update(arm_ids=['live'],selection_rule='Known CM009 then CM007, once each, sequential; UNKNOWN/resource/integrity abort remainder',artifact_path=str((O/'result.json').relative_to(R)))
m['llm_policy']=pm['llm_policy'];m['dataset']={**pm['dataset'],'name':'CM009 and CM007, Gold21 rev036 revalidation','frozen_source':str((D/'cases.json').relative_to(R)),'sha256':sha(D/'cases.json')};m['retrieval_accounting']=pm['retrieval_accounting'];put(A/'실험/manifest.json',m)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
S=ac.snapshot(A,'live',['08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/connect.py'],experiment_id=m['experiment_id'],arm_id='live',run_ids=['run-001'])
source=(R/b['adapter_root']/'engine_live.py').read_text()
old='''def gz(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 with gzip.open(path,'wt',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False)'''
new='''sys.path.insert(0,str(R/'06_TOOLS/maintenance'))
from experiment_json import write_summary,write_raw_json
PARENT_O=O
A=R/'04_EXPERIMENTS/ADR/ADR-1232-gold-connected-live-revalidation'
D=A/'artifacts/design';O=A/'artifacts/run-001'
base_guard=guard;resource_samples=[];initial_resource=base_guard()
initial_swap=initial_resource['SwapTotal']-initial_resource['SwapFree']
def guard():
 value=base_guard()
 value['host_swap_growth']=value['SwapTotal']-value['SwapFree']-initial_swap
 if value['host_swap_growth']>128*1024**2:raise RuntimeError('HOST_SWAP_GROWTH')
 if len(resource_samples)<4000:resource_samples.append(value)
 return value
def put(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 temporary=path.with_name('.'+path.name+'.'+str(time.time_ns())+'.json')
 write_summary(temporary,value);os.replace(temporary,path)
def gz(path,value):
 ref=write_raw_json(path,value)
 put(Path(str(path)+'.receipt.json'),ref)
 return ref'''
assert old in source;source=source.replace(old,new)
source=source.replace("assert read(O/'latest-check.json')['passed'] and read(O/'vector-check/result.json')['passed'] and read(O/'glossary-id-check/result.json')['passed']","assert read(PARENT_O/'latest-check.json')['passed'] and read(PARENT_O/'vector-check/result.json')['passed'] and read(PARENT_O/'glossary-id-check/result.json')['passed']")
source=source.replace("case_id=sys.argv[1];assert case_id in ('cm-007','cm-009')","case_id=sys.argv[1];assert case_id in ('cm-007','cm-009');assert len(sys.argv)==2, 'New validation accepts fresh real requests only'")
source=source.replace("release_id=read(O/'build-result.json')['query_id']","release_id=read(PARENT_O/'build-result.json')['query_id']")
source=source.replace("'mode':'isolated-gold-main120'","'mode':'isolated-gold-main120-revalidation-1232'")
source=source.replace("put(out/'response.json',{'http_status':response.status_code,'body':body})","response_ref=gz(out/'response.json.gz',{'http_status':response.status_code,'body':body});put(out/'response.json',{'http_status':response.status_code,'raw':response_ref})")
source=source.replace("put(out/'sql-statements.json',transport.statements if transport else []);put(out/'sql-errors.json',transport.errors if transport else [])","gz(out/'sql-statements.json.gz',transport.statements if transport else []);gz(out/'sql-errors.json.gz',transport.errors if transport else []);put(out/'resources.json',resource_samples)")
target='06_TOOLS/EXPERIMENTS/adr_1232/live.py';f=S/'snapshot'/target;f.parent.mkdir(parents=True);f.write_text(source);ac.register_file(S,target,upstream_state='absent');ac.freeze(S);assert not ac.validate(S),ac.validate(S)
v=read(S/'candidate.json')['revisions'][-1];C=S/'revisions'/v['revision_id']/'snapshot'
put(D/'candidate.json',{'root':str(S.relative_to(R)),'entry':str((C/target).relative_to(R)),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']})
print('Prepared frozen',v['revision_id'],'model calls 0')
