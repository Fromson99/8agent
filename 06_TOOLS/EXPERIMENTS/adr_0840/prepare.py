from pathlib import Path
import hashlib,json,shutil,subprocess,sys
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0840-comparison-source-handoff';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert p['generation']==79
release=read(R/p['manifest_path']);old=R/release['code_root'];assert all(sha(old/n)==h for n,h in release['files'].items())
put(D/'baseline.json',{'pointer':p,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':release,'selected_release_manifest':release})
put(D/'data-binding.json',{'path':release['data_path'],'manifest_sha256':release['data_manifest_sha256']})
criteria={'hypothesis':'Source investigation uncertainty does not veto already-read original evidence or semantic comparison; only structural, provenance, authorization, binding and budget errors stop execution.',
 'success':['Same-issue target refinement does not reject completion or reset investigation allowance','On known incomplete investigation, verified read originals reach parent without fabricated child claims','Saved and duplicate consumers verify the same exports and source binding','Each followup yields to review; no new evidence does not force a repeat research cycle','Both known actual questions return grounded field observations, and comparison runs when the LLM finds a pair'],
 'failure':['Invented or foreign-side evidence accepted','Source/ACL/hash or stale state check bypassed','Failed child presented as successful investigation','Already read evidence discarded because completion judgment is uncertain'],
 'recovery':{'owner':'native gap binding owns continuation identity; workflow export owns verified raw originals; task board owns research/review sequencing','allowed':'same-issue current source binding may refine target; raw read evidence is explicitly unreviewed, no claims generated','retry':'no new model repair added; original global40 calls and1800sec deadline preserved','research':'one task then review, existing max_recoveries rounds; preserve comparison allowance before followup','terminal':'partial with actual originals and unresolved causes; safety contract errors still fail'},
 'known_cases':'Exact0839 two questions, candidate once each, sequential; historical0839 is descriptive context, not a paired causal accuracy comparison',
 'in_sample':True,'decision_eligible':False,'quality_certified':False,'model':'qwen/qwen3.8-27b','provider':'Parasail','reasoning':'none','fallback':False,'max_calls_per_case':40,'wall_seconds':1800}
put(D/'criteria.json',criteria);put(D/'cases.json',read(R/'04_EXPERIMENTS/ADR/ADR-0839-main79-live-comparison/artifacts/design/cases.json'))
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Source handoff and nonblocking semantic execution with integrity preserved',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
for arm in m['design']['arms']:arm.update(changes='MAIN79 historical0839 and unchanged contract baseline' if arm['id']=='baseline' else 'Gap refinement, verified read export, followup/review scheduling',controls=['same data/model/global budget','no fixed legal answers or coordinates'])
m['runs'][0].update(arm_ids=['relaxed'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)),selection_rule=criteria['known_cases'])
m['dataset'].update(name='known-main79-failures',version='20261016-v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
put(A/'실험/manifest.json',m)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0840/relaxed'
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','relaxed','--experiment-id','ADR-0840-experiment-v1','--arm-id','relaxed','--run-id','run-001']
for n in release['files']:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for n in release['files']:shutil.copy2(old/n,C/'snapshot'/n)
put(D/'working-before.json',{n:sha(R/n) for n in release['files']})
for name in ('run_tests.py','consumer_check.py'):
 s=(R/'06_TOOLS/EXPERIMENTS/adr_0838'/name).read_text().replace('adr_0838','adr_0840').replace('ADR-0838-comparison-judgment-qualification','ADR-0840-comparison-source-handoff').replace('/connected','/relaxed')
 (T/name).write_text(s)
print(C)
