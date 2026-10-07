"""Zero-model-call audit of the frozen service factory and already returned real MAIN question.
Preserve nominal evaluation and resolved service fingerprints separately; no regrade or product edits.
"""
from pathlib import Path
import json,hashlib,importlib.util,importlib,sys,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0677-investigation-main-integrity-generalization';D=A/'artifacts/design';sys.dont_write_bytecode=True
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
b=read(D/'bindings.json');stage=R/b['stage'];rebase=read(D/'release-rebase.json');pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');manifest=read(R/pointer['manifest_path'])
assert manifest['files']==rebase['staged_files']
for p,h in manifest['files'].items():assert sha(R/p)==sha(stage/p)==sha(R/manifest['code_root']/p)==h,p
# This exact service factory was part of the hash-frozen package checked before model calls.
assert read(A/'artifacts/package-001/result.json')['strict_success']
profile=json.loads((A/'artifacts/run-001/integrated/NG01/profile.json').read_text())
spec=importlib.util.spec_from_file_location('frozen_service_profile_audit',stage/'service.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s);s._ROOT=R
s._resolve_binding=lambda:(stage,R/b['source_generation'],{'mode':'local-release','release_id':'frozen-profile-audit','generation':43})
os.environ['GENOS_RUNTIME_DIR']=str(A/'artifacts/service-profile-audit/runtime')
app=s.application();effective=app.state.pipeline.term_agent.profile
namespace=importlib.import_module(app.state.pipeline.__class__.__module__.rsplit('.',1)[0]+'.legal_agent.corrected_memory')
# Normalize the recorded evaluation profile through the same pinned v5 validator.
v5=importlib.import_module(app.state.pipeline.__class__.__module__.rsplit('.',1)[0]+'.legal_agent.workflow_tiers_policy')
nominal=v5.profile(profile,require_model=True)
delta={k:{'evaluation':nominal.get(k),'service':effective.get(k)} for k in set(nominal)|set(effective) if nominal.get(k)!=effective.get(k)}
assert delta=={'max_transport_retries':{'evaluation':1,'service':0}},delta
resolved_hash=namespace.digest(effective);nominal_hash=namespace.digest(nominal)
expected=read(A/'artifacts/run-001/integrated/NG01/diagnostic.json')['binding'];assert nominal_hash==expected['profile']
outcome=read(A/'artifacts/main-smoke-response.json');assert outcome['status']==200;out=outcome['body'];runtime=R/'90_RUNTIME/semantic'
import sqlite3
paths=list((runtime/'legal-agent/runs').glob('*/'+out['run_id']+'/journal.sqlite'));assert len(paths)==1
conn=sqlite3.connect(paths[0].resolve().as_uri()+'?mode=ro',uri=True);native=json.loads(conn.execute("SELECT payload_json FROM entity_version WHERE kind='case_stage' AND entity_id='case:READ' ORDER BY created_seq DESC LIMIT 1").fetchone()[0])['binding'];conn.close()
resolved_expected={**expected,'profile':resolved_hash}
assert native==resolved_expected,(native,resolved_expected)
# The saved real response already passed manifest/profile/data/search/schema/process assertions;
# additionally recheck its selection and exact inventory against the current pointer.
release=out['release'];assert release['release_id']==pointer['release_id'] and release['generation']==pointer['generation'] and release['release_manifest_sha256']==pointer['release_manifest_sha256']
assert release['profile_sha256']==sha(stage/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
meta=out['assembly']['term_agent'];assert meta['control_contract']=='investigation-control-v2' and meta['investigation_chain']
proof={'mode':'deterministic launch-profile resolution, no model call','source_service':{'path':str((stage/'service.py').relative_to(R)),'sha256':sha(stage/'service.py')},'source_profile':{'path':str((stage/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').relative_to(R)),'sha256':sha(stage/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')},'source_policy':{'path':str((stage/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json').relative_to(R)),'sha256':sha(stage/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')},'normalization_delta':delta,'nominal_evaluation_profile_sha256':nominal_hash,'effective_frozen_service_profile_sha256':resolved_hash,'actual_native_service_profile_sha256':native['profile'],'full_effective_profile':effective,'same_frozen_factory_same_actual_profile':True,'actual_model_call_count_in_this_audit':0,'nominal_profile_fingerprint_was_not_rewritten':True,'source_experiment_unchanged':True}
put(A/'artifacts/service-profile-resolution.json',proof)
provider=A/'artifacts/main-smoke-provider';calls=sorted(provider.glob('call-*'));usage=[]
for p in calls:
 f=p/'usage.json'
 if f.exists():usage.append(read(f))
# ExperimentClient's aggregate usage is the authoritative transport receipt when available.
if (provider/'usage.json').exists():
 u=read(provider/'usage.json');usage=u.get('usage',u.get('calls',[])) if isinstance(u,dict) else u
report={'status':'passed','entrypoint':'service.service','process_id':release['process_id'],'pointer':pointer,'execution_binding':release,'native_binding':native,'evaluation_binding':expected,'effective_frozen_service_binding':resolved_expected,'profile_resolution':{'path':str((A/'artifacts/service-profile-resolution.json').relative_to(R)),'sha256':sha(A/'artifacts/service-profile-resolution.json')},'nominal_evaluation_equals_actual_runtime_profile':False,'effective_frozen_service_equals_actual_runtime_profile':True,'same_working_candidate_release_files':True,'service_health_status':200,'search_status':200,'question':'상법상 대표이사는 누가 선정하고 정관으로 달리 정할 수 있나요?','answer':out['answer']['text'],'investigation_id':out.get('investigation_id'),'run_id':out['run_id'],'answer_coverage':meta['answer_coverage'],'issue_assessments':meta['issue_assessments'],'model_calls':len(calls),'usage':usage,'runtime':str(runtime),'resident_server_restarted':False,'genos_deployed':False,'real_response_path':str((A/'artifacts/main-smoke-response.json').relative_to(R)),'real_response_sha256':sha(A/'artifacts/main-smoke-response.json')}
put(A/'artifacts/main-smoke.json',report);print(json.dumps({'status':report['status'],'model_calls':len(calls),'profile_delta':delta,'actual_profile':native['profile']},ensure_ascii=False))
