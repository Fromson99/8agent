from pathlib import Path
import json,hashlib,shutil,subprocess
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0852-basis-workflow-ingress-repair';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
P=R/'04_EXPERIMENTS/ADR/ADR-0851-basis-lifecycle-qualification';f=read(P/'artifacts/design/freeze.json');old=R/f['code_root'];cm=read(R/f['candidate']['manifest_path']);names=[x['target_path'] for x in cm['files']];C=R/'02_BACKEND/lawrag/research/candidates/adr_0852/qualified'
assert read(P/'실험/manifest.json')['reservation']['status']=='completed'
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert p['generation']==81;m=read(R/p['manifest_path']);put(D/'baseline.json',{'pointer':p,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':m});put(D/'data-binding.json',{'path':m['data_path'],'manifest_sha256':m['data_manifest_sha256']});put(D/'working-before.json',{n:sha(R/n) if (R/n).exists() else None for n in names})
criteria={'scope':'Repair local asyncio shadowing in GENOS workflow editor entry; source/runtime code retained', 'success':['Only editor local import removal and exact dependent pins change','Pinned editor AD start succeeds without legal bootstrap','All8explicit control operations and implicit discovery preserve response and request; errors remain errors','All139 previous contracts pass on integrated working code','Exact selected service verified'], 'failure':['Existing AD/RAG question path fails','New explicit API performs a wrong operation','Model calls or permission bypass introduced'], 'model_calls':0,'quality_certified':False,'novelty':'Pinned editor entry tests on actual candidate path; prior test loaded working editor before integration and missed this defect. Deterministic software fix, no legal quality comparison.'}
put(D/'criteria.json',criteria)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','qualified','--experiment-id','ADR-0852-experiment-v1','--arm-id','qualified','--run-id','run-001']
for n in names:
 if (R/n).exists():cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for n in names:
 dest=C/'snapshot'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old/n,dest)
 if not (R/n).exists():subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',n,'--upstream-state','absent'],check=True,stdout=subprocess.DEVNULL)
g=C/'snapshot/08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py';text=g.read_text();assert text.count('        import asyncio\n')==1;g.write_text(text.replace('        import asyncio\n',''))
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=criteria['scope'];m['design'].update(hypothesis=criteria['scope'],primary_metric='Bound authorization and source authority ingress',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
for arm in m['design']['arms']:arm.update(changes='Completed0847' if arm['id']=='baseline' else 'Remove function-local asyncio shadowing; all other product behavior retained',controls=['Exact0847 source code','same selected data/model policy','zero external model calls'])
m['runs'][0].update(arm_ids=['qualified'],selection_rule=criteria['novelty'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
reason='Finite authorization/state contract checks, not retrieval or legal quality comparison';m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason;put(A/'실험/manifest.json',m)
for name in ('run_tests.py','pins.py','consumer.py','preview.py','seal.py'):
 t=(T.parent/'adr_0851'/name).read_text().replace('adr_0851/qualified','adr_0852/qualified').replace('adr_0851','adr_0852').replace('ADR-0851-basis-lifecycle-qualification','ADR-0852-basis-workflow-ingress-repair').replace("'candidate_id':'wired'","'candidate_id':'qualified'").replace("'arm_id':'wired'","'arm_id':'qualified'").replace("arm_ids=['wired']","arm_ids=['qualified']").replace('basis-lifecycle-wired-preview','basis-lifecycle-qualified-preview')
 (T/name).write_text(t)
print(C)
