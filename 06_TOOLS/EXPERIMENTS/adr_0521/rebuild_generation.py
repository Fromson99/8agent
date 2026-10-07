"""Run the frozen candidate through the existing reference-resolution pipeline API."""
import json,time
from bootstrap import R,A,pin
pin()
from lawrag.platform.workspace import load_layout
from lawrag.pipeline.reference_resolution import rebuild
from semantic_runtime.contracts import sha,write
layout=load_layout(R)
active=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
pointer=json.loads(active.read_text());release=json.loads((R/pointer['manifest_path']).read_text())
parent=R/release['data_path']
output=layout.path('data')/'TERM_RELEASES/adr0521-shared-reference-v1/generation'
plan={'schema_version':'adr0521-generation-plan-v1','active_sha256':sha(active),'parent_generation':str(parent),'parent_manifest_sha256':sha(parent/'manifest.json'),'output':str(output),'activation':False}
write(A/'artifacts/generation-plan.json',plan)
started=time.monotonic();print(json.dumps({'phase':'rebuild','parent':str(parent),'output':str(output)}),flush=True)
result=rebuild(parent,output)
result.update(elapsed_seconds=time.monotonic()-started,active_pointer_unchanged=sha(active)==plan['active_sha256'])
write(A/'artifacts/generation-result.json',result)
print(json.dumps(result,ensure_ascii=False),flush=True)
