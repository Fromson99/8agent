"""Validate installed code/pins/imports without opening field data or calling models."""
from pathlib import Path
import hashlib,json,sys
root=Path(sys.argv[1]).resolve(strict=True)
sys.path[:0]=[str(root/'02_BACKEND'),str(root)]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
pipeline=json.loads((root/'00_SYSTEM/PIPELINE.json').read_bytes())
for entry in pipeline['engines'].values():
    p=root/entry['manifest'];assert sha(p)==entry['sha256'],entry['manifest']
    for name,pin in json.loads(p.read_bytes())['files'].items():assert sha(root/name)==pin,name
workflows={}
for entry in pipeline['workflows']['registered']:
    p=root/entry['manifest'];assert sha(p)==entry['sha256']
    manifest=json.loads(p.read_bytes());workflows[entry['id']]=manifest['version']
    for name,pin in manifest['files'].items():assert sha(root/'02_BACKEND/workflow'/name)==pin,name
assert workflows=={'risk_team_compare_workflow':'1.10.0','internal_basis_discovery_workflow':'1.0.0'}
import semantic_runtime.app,semantic_runtime.oracle_dp,semantic_runtime.basis_links.api
import semantic_runtime.legal_agent.minimal_output,semantic_runtime.legal_agent.source_handoff
import workflow.risk_team_compare_workflow.report,lawrag.pipeline.oracle_publish
assert Path(semantic_runtime.app.__file__).resolve().is_relative_to(root)
print(json.dumps({'status':'CODE_SMOKE_PASS','code_root':str(root),'python':sys.executable,'version':sys.version,
                  'workflow_versions':workflows,'field_data_opened':False,'model_calls':0}))
