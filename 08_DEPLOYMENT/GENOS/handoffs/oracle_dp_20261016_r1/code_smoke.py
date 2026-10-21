"""Verify installed imports and engine/workflow pins, without opening field data."""
from pathlib import Path
import hashlib,json,sys

root=Path(sys.argv[1]).resolve(strict=True)
sys.path[:0]=[str(root/'02_BACKEND'),str(root)]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
pipeline=json.loads((root/'00_SYSTEM/PIPELINE.json').read_bytes())
for entry in pipeline['engines'].values():
    p=root/entry['manifest'];assert sha(p)==entry['sha256'],entry['manifest']
    for name,pin in json.loads(p.read_bytes())['files'].items():assert sha(root/name)==pin,name
for entry in pipeline['workflows']['registered']:
    p=root/entry['manifest'];assert sha(p)==entry['sha256']
    manifest=json.loads(p.read_bytes())
    assert manifest['version']=='1.8.0',manifest['version']
    for name,pin in manifest['files'].items():assert sha(root/'02_BACKEND/workflow'/name)==pin,name
import semantic_runtime.app
import semantic_runtime.legal_agent.source_handoff
import semantic_runtime.legal_agent.source_investigation
import workflow.risk_team_compare_workflow.report
assert Path(semantic_runtime.app.__file__).resolve().is_relative_to(root)
print(json.dumps({'status':'CODE_SMOKE_PASS','code_root':str(root),'python':sys.executable,'version':sys.version,
                  'workflow_version':'1.8.0','field_data_opened':False,'model_calls':0}))

import semantic_runtime.oracle_dp, lawrag.pipeline.oracle_publish
print("ORACLE_DP_IMPORT_PASS")
