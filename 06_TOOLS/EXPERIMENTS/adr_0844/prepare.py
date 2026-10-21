from pathlib import Path
import json,hashlib,shutil,subprocess,sys
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0844-comparison-source-return';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert p['generation']==80
m=read(R/p['manifest_path']);base=R/m['code_root'];assert sha(R/p['manifest_path'])==p['release_manifest_sha256']
put(D/'baseline.json',{'pointer':p,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':m,'selected_release_manifest':m})
put(D/'data-binding.json',{'path':m['data_path'],'manifest_sha256':m['data_manifest_sha256']})
put(D/'working-before.json',{n:sha(R/n) for n in m['files']})
criteria={'hypothesis':'Named short originals and existing explicit references are acquired before broad search; child source investigation has a normal durable terminal and no ASSESS; one comparison table preserves opinions and evidence.',
 'success':['Named short document originals reach parent with exact spans','Existing exact references are followed first; local missing document is not generalized to GENOS','Sources terminal zero child ASSESS, no semantic sufficiency veto','Sources terminal, duplicate, restart, followup share current binding and persisted budget','Normal standalone RAG remains on existing completion contract','One final opinion table with issue-owned titles and all rows counted'],
 'failure':['Altered/foreign/inaccessible evidence accepted','Originals lost after later failure','Sources return promoted to legal answer or experience','Same logical request resets budget or duplicates physical calls'],
 'recovery':{'owner':'Existing gateway transport and native navigation structural repair; sources handoff owns commit and replay; parent owns meaning','limits':'Inherited profile physical/tool/deadline limits; at most existing one structural correction, no semantic retries','terminal':'Verified original handoff with unresolved targets; integrity failures remain failures'},
 'in_sample':True,'decision_eligible':False,'quality_certified':False,
 'known_case':'committee-duties-01; one candidate run, baseline0843 historical observational only, no speed significance claim',
 'genos':'Existing targets preferred; no remote access or inference from local absence',
 'design_source':'09_ARTIFACTS/AUDITS/20261016-risk-comparison-simplification-design/DESIGN.txt'}
put(D/'criteria.json',criteria)
put(D/'cases.json',[{'id':'committee-duties-01','api_type':'WORKFLOW_RUN','workflow_id':'risk_team_compare_workflow','question':'위험관리위원회운영준칙의 위원회 역할과 심의·의결사항을 관련 외규와 대사해서 공통사항과 차이를 설명해 주세요.'}])
C=R/'02_BACKEND/lawrag/research/candidates/adr_0844/sources'
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','sources','--experiment-id','ADR-0844-experiment-v1','--arm-id','sources','--run-id','run-001']
for n in m['files']:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for n,h in m['files'].items():
 assert sha(base/n)==h,n
 shutil.copy2(base/n,C/'snapshot'/n)
v=read(A/'실험/manifest.json');v['lineage']['hypothesis_delta']=criteria['hypothesis'];v['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Durable source acquisition and comparison execution',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
for arm in v['design']['arms']:arm.update(changes='Selected MAIN80' if arm['id']=='baseline' else criteria['hypothesis'],controls=['same data, model, authorization, total limits','no fixed legal answers'])
v['runs'][0].update(arm_ids=['sources'],selection_rule=criteria['known_case'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
v['dataset'].update(name='known-committee-source-return',version='20261016-v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
put(A/'실험/manifest.json',v)
print(C)
