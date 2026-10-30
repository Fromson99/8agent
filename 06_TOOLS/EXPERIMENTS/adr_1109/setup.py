from pathlib import Path
import json,hashlib,shutil,sys,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1109-genos-mode-admission-main';P=R/'04_EXPERIMENTS/ADR/ADR-1108-genos-applied-mode-main';C=R/'02_BACKEND/lawrag/research/candidates/adr_1109/mode-admission-r1';PC=R/'02_BACKEND/lawrag/research/candidates/adr_1108/applied-mode-r1';S=A/'artifacts/staged-code';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
base=json.loads((P/'artifacts/design/baseline.json').read_text());put(D/'baseline.json',base)
criteria=json.loads((P/'artifacts/design/criteria.json').read_text());criteria['implementation']+=' Before method validation, bind explicit source marker for CASE_START, PURPOSE_REVISE, RESEARCH_REPLAN. Comparison tests bind actual runtime.execute, after real ingress identity resolution.';criteria['prior_failure']='ADR1108, not inherited as passed';put(D/'criteria.json',criteria)
m=json.loads((P/'실험/manifest.json').read_text());scaffold=json.loads((A/'실험/manifest.json').read_text())
for k in ('adr_id','experiment_id','reservation','lineage','relationships'):m[k]=scaffold[k]
m['design']['hypothesis']=criteria['implementation'];m['design']['code_isolation'].update(mode='candidate_snapshot',candidates=[])
m['results'].update(status='not_run',by_arm={},error_taxonomy=[]);m['runs'][0].update(status='planned',artifact_path='TODO',sha256='PENDING');m['runs'][0].pop('success_criteria_met',None)
m['dataset'].update(frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'));put(A/'실험/manifest.json',m)
files=[x['target_path'] for x in json.loads((PC/'candidate.json').read_text())['files']]+['02_BACKEND/semantic_runtime/legal_agent/corrected_memory.py']
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--experiment-id',m['experiment_id'],'--candidate-id','mode-admission-r1','--arm-id','integrated','--run-id','run-001']
for n in files:cmd+=['--source',n]
subprocess.run(cmd,check=True,cwd=R)
for n in files:
 src=PC/'revisions/rev-001/snapshot'/n if (PC/'revisions/rev-001/snapshot'/n).exists() else R/base['manifest']['code_root']/n
 shutil.copyfile(src,C/'snapshot'/n)
p=C/'snapshot/02_BACKEND/semantic_runtime/legal_agent/corrected_memory.py';s=p.read_text();old='            output.validate_shape(raw,closed)\n            try:command=normalize(raw,context)';new='''            output.validate_shape(raw,closed)
            # UI/source scope is explicit request configuration. Bind it before
            # validating a replan so a model KEEP cannot erase the user's change.
            if raw.get('method_id') in ('CASE_START','PURPOSE_REVISE','RESEARCH_REPLAN'):
                from ..pipeline import route_question
                _, category = route_question(context['utterance'])
                if category is not None:raw = {**raw, 'source_category': category}
            try:command=normalize(raw,context)''';assert old in s;s=s.replace(old,new);p.write_text(s)
for n,h in base['manifest']['files'].items():
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/base['manifest']['code_root']/n,p)
for n in files:shutil.copyfile(C/'snapshot'/n,S/n)
(S/'01_DATA').symlink_to(R/'01_DATA',target_is_directory=True)
sys.path.insert(0,str(R/'02_BACKEND'));from semantic_runtime.control import rehash_engines
put(D/'rehash.json',rehash_engines(S,apply=True))
for n in files:shutil.copyfile(S/n,C/'snapshot'/n)
put(D/'staging.json',{'code_root':str(S.relative_to(R)),'files':{n:sha(S/n) for n in base['manifest']['files']},'changed':{n:sha(S/n) for n,h in base['manifest']['files'].items() if sha(S/n)!=h},'base_manifest_sha256':base['pointer']['release_manifest_sha256']})
runner=(R/'06_TOOLS/EXPERIMENTS/adr_1108/run_tests.py').read_text().replace('ADR-1108-genos-applied-mode-main','ADR-1109-genos-mode-admission-main');(Path(__file__).parent/'run_tests.py').write_text(runner)
p=R/'05_TESTS/CONTRACTS/test_genos_applied_mode.py';s=p.read_text();s=s[:s.index('def test_compare_reaches_registered_workflow')]+'''def test_compare_reaches_registered_workflow(tmp_path,mixed_generation,monkeypatch):
    import service,asyncio
    principal={'user_id':'u','team_id':'risk_team','document_ids':['internal','external']}
    app=create_app(tmp_path,mixed_generation,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',legal_agent_profile={**settings(),'max_model_attempts':40},legal_agent_transport=ScriptedTransport(),memory_identity=lambda req:principal)
    monkeypatch.setattr(service,'_bootstrap_application',lambda:app)
    seen=[]
    def intercept(body,who):
        seen.append((body,who));return {'response_schema':'workflow-result-v1','status':'completed','answer':{'text':'모의 대사'}}
    monkeypatch.setattr(app.state.workflow_runtime,'execute',intercept)
    body=adapter.request_body({'question':'승인','request_id':'r','chatId':'s','team_id':'risk_team','applied_fields':{'mode':'대사'}},'승인')
    result=asyncio.run(service.service({},body))
    assert result['status']==200 and len(seen)==1,result
    assert seen[0][0]['workflow_id']=='risk_team_compare_workflow'
    assert seen[0][1]['document_ids']==['internal','external']
    assert result['body']['response_schema']=='workflow-result-v1'
    app.state.pipeline.store.close()
''';p.write_text(s)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,cwd=R)
c=json.loads((C/'candidate.json').read_text());rev=c['revisions'][-1];b={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
r=Path(__file__).parent/'run_tests.py';put(D/'freeze.json',{'candidate':b,'runner':{'path':str(r.relative_to(R)),'sha256':sha(r)},'test':{'path':str(p.relative_to(R)),'sha256':sha(p)}})
m['design']['code_isolation']['candidates']=[{**b,'candidate_id':c['candidate_id'],'arm_id':'integrated','experiment_id':c['experiment_id'],'run_ids':['run-001'],'runner_path':str(r.relative_to(R)),'runner_sha256':sha(r)}];put(A/'실험/manifest.json',m)
print('Frozen38files before follow-up tests')
