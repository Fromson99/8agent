from pathlib import Path
import datetime,hashlib,json,shutil
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0909-reference-context-charter-trace';D=A/'artifacts/design';D.mkdir(exist_ok=True)
P=R/'04_EXPERIMENTS/ADR/ADR-0900-main87-charter-stateless-trace';Q=R/'04_EXPERIMENTS/ADR/ADR-0908-reference-context-continuity'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists();f=read(Q/'artifacts/design/freeze.json');old=read(P/'artifacts/design/baseline.json');code=R/f['code_root']
baseline={'pointer':old['pointer'],'manifest':{**old['manifest'],'code_root':f['code_root'],'files':f['serving_files']},'active_release':old['manifest'],'candidate':f['candidate'],'source':'Exact qualified ADR0908 frozen candidate; active MAIN87 data/profile. Existing working session changes predate this patch, so not controlled A/B.'}
assert read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer'];put(D/'baseline.json',baseline)
shutil.copyfile(P/'artifacts/design/cases.json',D/'cases.json')
c=read(P/'artifacts/design/criteria.json');c['hypothesis']='Bounded previous reference opinions survive focus changes and FOLLOW options name actual anchor sources. Observe one known public question after the input repair; no causal or general performance certification.'
c['controls']='Explicit qualified candidate application injected into its exact service.py RAG_ASK entry, unchanged MAIN87 data/profile/public source scope. Local external Qwen3.8 only, no GENOS access. Same low-memory instrumentation as prior observation.'
c['success_criteria'][0]='Actual service entry uses exact qualified candidate code pins and selected public data/profile, with active MAIN87 pointer unchanged.'
put(D/'criteria.json',c)
live=(R/'06_TOOLS/EXPERIMENTS/adr_0900/live.py').read_text().replace('ADR-0900-main87-charter-stateless-trace','ADR-0909-reference-context-charter-trace').replace('adr0900-','adr0909-')
live=live.replace('import asyncio, hashlib, importlib, json, os, resource, sys, time, traceback','import asyncio, hashlib, importlib, importlib.util, json, os, resource, sys, time, traceback')
live=live.replace('WSL local active service.application bootstrap and ASGI dispatch; active pointer unchanged','WSL local qualified candidate service.py with injected application and ASGI dispatch; active pointer unchanged').replace("'app_injected': False","'app_injected': True")
start=live.index('    import service\n');end=live.index("    t = app.state.pipeline.term_agent.transport",start)
bootstrap="""    sys.path[:0]=[str(C/'02_BACKEND'),str(C)]
    from semantic_runtime.app import create_app
    from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
    transport=LocalGemmaTransport(C,R)
    native_profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
    native_profile['model_binding']=transport.binding
    app=create_app(R,R/release['data_path'],contracts_root=C,workspace_root=R,provider=object(),
        implementation='legal-agent-unified-v6',runtime_root=O/'runtime',
        legal_agent_profile=native_profile,legal_agent_transport=transport,
        release={'mode':'local-release','release_id':'qualified-reference-observation'})
    spec=importlib.util.spec_from_file_location('qualified_service_entry',C/'service.py')
    actual=importlib.util.module_from_spec(spec);spec.loader.exec_module(actual)
    actual._APP=app;actual._BINDING={'mode':'local-release','generation':87,'candidate_code_root':str(C)}
    assert Path(app.state.pipeline.store.path).resolve()==(R/release['data_path']).resolve()
    assert Path(sys.modules[type(app.state.pipeline).__module__].__file__).resolve().is_relative_to(C)
    put(O/'health.json',asyncio.run(actual.service({}, {'API_TYPE':'HEALTH'})))
"""
live=live[:start]+bootstrap+live[end:]
(T/'live.py').write_text(live)
for n in ['observe.py','archive.py']:(T/n).write_text((R/'06_TOOLS/EXPERIMENTS/adr_0900'/n).read_text().replace('ADR-0900-main87-charter-stateless-trace','ADR-0909-reference-context-charter-trace'))
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=c['hypothesis'];m.update(in_sample=True,decision_eligible=False)
m['design'].update({k:c[k] for k in ('hypothesis','primary_metric','success_criteria','failure_criteria')});m['design']['criteria_frozen_before_run']=True
m['design']['code_isolation'].update(mode='not_applicable',reason='No new product implementation; explicit reuse of completed immutable qualified candidate from ADR0908. All frozen code hashes recorded; active selection unchanged.',candidates=[])
m['design']['arms']=[{'id':'observed','role':'candidate','derived_from':['ADR-0908-experiment-v1/retained'],'changes':'No change from technically qualified candidate; one known-question observation','controls':c['controls']}]
plans=[{'stage_id':'native_read','kind':'source','parent_stage_ids':[]},{'stage_id':'selected','kind':'select','parent_stage_ids':['native_read']},{'stage_id':'cited','kind':'present','parent_stage_ids':['selected']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'observed':plans}
m['runs'][0].update(arm_ids=['observed'],selection_rule=c['selection'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='user-charter-quorum',version='20261019-v2',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'native_rag','class':'product','model':c['model'],'repeats':1,'max_calls':40,'temperature':0}]
m['retrieval_accounting']['not_applicable_reason']='Measured acquired/selected/cited accounting; no approved legal gold or search recall claim.'
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
files={n:h for n,h in f['files'].items() if n.startswith(f['code_root']+'/')}
for folder in [T,D]:
 for p in folder.glob('*'):
  if p.is_file():files[str(p.relative_to(R))]=sha(p)
for p in [R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',R/'02_BACKEND/lawrag/research/experiment_client.py',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'06_TOOLS/EXPERIMENTS/resource_guard.py',*[R/old['manifest']['data_path']/n for n in ('manifest.json','fulltext/manifest.json','navigation/manifest.json')]]:files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':files,'serving_files':f['serving_files'],'code_root':f['code_root'],'candidate':f['candidate']})
print('Frozen one known question, explicit qualified service code, public-only external model, one worker RSS6/AS8GiB.')
