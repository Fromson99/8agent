from pathlib import Path
import json,hashlib,shutil,subprocess,sys
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0841-comparison-direct-review';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
P=R/'04_EXPERIMENTS/ADR/ADR-0840-comparison-source-handoff';assert read(P/'실험/manifest.json')['reservation']['status']=='completed'
v=read(P/'artifacts/design/verification-binding.json');old=R/v['code_root'];b=read(P/'artifacts/design/baseline.json');assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'];put(D/'baseline.json',b);put(D/'data-binding.json',read(P/'artifacts/design/data-binding.json'))
criteria={'hypothesis':'Already reviewed field evidence flows directly to comparison; optional gap attribution and adoption bookkeeping cannot veto valid source actions. Meaning stays with LLM.', 'success':['No separate BASIS model call in task-board workflow','FINISH explicit delivered original selection is enough without separate ADOPT metadata','Omitted gap links/resolutions do not block reads or FINISH; unresolved gaps remain unresolved','Unknown/altered/foreign sources, stale state, false absence, ACL and hash failures still reject','Known committee packet produces actual comparison opinions with original citations'], 'failure':['Invented evidence or automatic legal finding','Source tampering accepted','Partial observations lost'], 'recovery':{'owner':'native navigation validates source identity once; task board assembles already selected citations; COMPARE model owns meaning','limits':'Existing model/time budget and one structural repair; no semantic retry or new approval model','terminal':'Partial observations retained; missing sources reported, not inferred absent'},'known_packet':'840 committee original parent checkpoint plus exact original evidence; fixed one attempt per issue, maximum2calls, no retrieval rerun or repairs','in_sample':True,'decision_eligible':False,'quality_certified':False}
put(D/'criteria.json',criteria);put(D/'working-before.json',{n:sha(R/n) for n in v['serving_files']})
C=R/'02_BACKEND/lawrag/research/candidates/adr_0841/direct';cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','direct','--experiment-id','ADR-0841-experiment-v1','--arm-id','direct','--run-id','run-001']
for n in v['serving_files']:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for n in v['serving_files']:shutil.copy2(old/n,C/'snapshot'/n)
for name in ('run_tests.py','consumer_check.py','freeze.py'):
 s=(R/'06_TOOLS/EXPERIMENTS/adr_0840'/name).read_text().replace('adr_0840','adr_0841').replace('ADR-0840-comparison-source-handoff','ADR-0841-comparison-direct-review').replace('ADR-0840-experiment-v1','ADR-0841-experiment-v1').replace('relaxed','direct').replace("'1.6.0'","'1.7.0'")
 if name=='freeze.py':
  start=s.index("m['llm_policy']['llm_calls']")
  stop=s.index("paths=list(T.glob",start)
  s=s[:start]+"m['llm_policy']['llm_calls']=[{'role':'comparison','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0}];put(A/'실험/manifest.json',m)\n"+s[stop:]
 (T/name).write_text(s)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Nonblocking source-backed comparison execution',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
for arm in m['design']['arms']:arm.update(changes='Completed840 source handoff' if arm['id']=='baseline' else 'Direct item-to-comparison; optional native investigation metadata',controls=['same data/model','no fixed legal answers'])
m['runs'][0].update(arm_ids=['direct'],selection_rule=criteria['known_packet'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='known-committee-evidence-packet',version='840-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
reason='Known read-only original packet and synthetic software contracts; no new retrieval, no legal gold.';m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason;put(A/'실험/manifest.json',m)
print(C)
