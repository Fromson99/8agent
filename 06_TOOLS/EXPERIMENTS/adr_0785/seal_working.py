"""Refresh only the isolated candidate's declared hashes during development."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[3]
C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0785/integrated/snapshot'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
wf=C/'02_BACKEND/workflow'
manifest={'schema_version':'workflow-manifest-v1','workflow_id':'risk_team_compare_workflow',
    'version':'1.0.0','allowed_teams':['risk_team'],'entrypoint':'risk_team_compare_workflow.flow.execute',
    'reporter':'risk_team_compare_workflow.report.build',
    'input_contract':'workflow-request-v1','output_contract':'workflow-result-v1',
    'capabilities':['rag.source_tools','rag.exact_spans','model.structured','state.durable'],
    'budget_source':'selected RAG effective profile; shared journal physical counters and original deadline',
    'max_recoveries':2,'max_stage_corrections':1,'max_call_depth':1,
    'quality_certified':False,
    'files':{str(p.relative_to(wf)):sha(p) for p in sorted(wf.rglob('*.py'))}}
write(wf/'risk_team_compare_workflow/manifest.json',manifest)
p=C/'00_SYSTEM/PIPELINE.json';config=json.loads(p.read_text())
config['workflows']={'schema_version':'workflow-registry-v1','enabled':True,
    'runtime':'02_BACKEND/workflow/runtime.py','rag_port':'02_BACKEND/semantic_runtime/workflow_bridge.py',
    'registered':[{'id':manifest['workflow_id'],'version':manifest['version'],
        'manifest':'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json',
        'sha256':sha(wf/'risk_team_compare_workflow/manifest.json')}],
    'entrypoints':['/v1/workflows/run','/v1/workflows/resume','/v1/workflows/runs/{run_id}','/v1/rag/ask:대사'],
    'consumes':['selected source generation','term/definition/reference index'],
    'produces':['workflow-result-v1','exact source receipts','durable checkpoint'],
    'state_namespace':'runtime/semantic/workflows'}
schema=C/'00_SYSTEM/SCHEMAS/pipeline-v1.schema.json';s=json.loads(schema.read_text())
s['properties']['workflows']={'type':'object','properties':{
    'schema_version':{'const':'workflow-registry-v1'},'enabled':{'type':'boolean'},
    **{k:{'type':'string','minLength':1} for k in ('runtime','rag_port','state_namespace')},
    **{k:{'type':'array','items':{'type':'string'}} for k in ('entrypoints','consumes','produces')},
    'registered':{'type':'array','items':{'type':'object','properties':{
        'id':{'type':'string'},'version':{'type':'string'},'manifest':{'type':'string'},
        'sha256':{'type':'string','pattern':'^[a-f0-9]{64}$'}},
        'required':['id','version','manifest','sha256'],'additionalProperties':False}}},
    'required':list(config['workflows']),'additionalProperties':False}
write(schema,s)
extra={str(p.relative_to(C)):sha(p) for p in wf.rglob('*') if p.is_file() and p.suffix in ('.py','.json')}
extra['02_BACKEND/semantic_runtime/workflow_bridge.py']=sha(C/'02_BACKEND/semantic_runtime/workflow_bridge.py')
for path in (C/'02_BACKEND/ENGINES').rglob('*.json'):
    e=json.loads(path.read_text())
    if 'files' not in e:continue
    for name in e['files']:
        if (C/name).is_file():e['files'][name]=sha(C/name)
    e['files'].update(extra)
    write(path,e)
for entry in config['engines'].values():entry['sha256']=sha(C/entry['manifest'])
for contract in config['contracts'].values():
    if (C/contract['schema_path']).is_file():contract['schema_sha256']=sha(C/contract['schema_path'])
write(p,config)
print('Candidate hashes updated:',len(extra),'workflow/bridge files')
