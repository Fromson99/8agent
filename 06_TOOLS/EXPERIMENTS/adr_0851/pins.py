from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0851/qualified/snapshot'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
w=C/'02_BACKEND/workflow'
new={'schema_version':'workflow-manifest-v1','workflow_id':'internal_basis_discovery_workflow','version':'1.0.0',
     'allowed_teams':['risk_team'],'entrypoint':'internal_basis_discovery_workflow.flow.execute',
     'reporter':'internal_basis_discovery_workflow.report.build','normalizer':'internal_basis_discovery_workflow.contracts.normalize',
     'presenter':'internal_basis_discovery_workflow.report.view','input_contract':'basis-discovery-request-v1',
     'output_contract':'workflow-result-v1','budget_source':'Selected RAG profile and persistent parent counters/deadline',
     'capabilities':['rag.question_answer','rag.exact_spans','model.structured','state.durable','basis.authority'],
     'max_stage_corrections':1,'max_call_depth':1,'quality_certified':False,'files':{}}
put(w/'internal_basis_discovery_workflow/manifest.json',new)
for name,version in [('risk_team_compare_workflow','1.9.0'),('internal_basis_discovery_workflow','1.0.0')]:
 p=w/name/'manifest.json';v=json.loads(p.read_text());v['version']=version
 v['files']={str(p.relative_to(w)):sha(p) for p in w.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}
 put(p,v)
extras={str(p.relative_to(C)):sha(p) for folder in ['02_BACKEND/semantic_runtime/basis_links','02_BACKEND/workflow'] for p in (C/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=json.loads(p.read_text())
 if 'files' not in v:continue
 for f in v['files']:
  if (C/f).is_file():v['files'][f]=sha(C/f)
 if any(n.startswith('02_BACKEND/semantic_runtime/') for n in v['files']):v['files'].update(extras)
 put(p,v)
p=C/'00_SYSTEM/PIPELINE.json';v=json.loads(p.read_text())
for e in v['engines'].values():
 if (C/e['manifest']).is_file():e['sha256']=sha(C/e['manifest'])
v['workflows']['registered']=[{'id':name,'version':version,'manifest':'02_BACKEND/workflow/'+name+'/manifest.json','sha256':sha(w/name/'manifest.json')} for name,version in [('risk_team_compare_workflow','1.9.0'),('internal_basis_discovery_workflow','1.0.0')]]
put(p,v)
