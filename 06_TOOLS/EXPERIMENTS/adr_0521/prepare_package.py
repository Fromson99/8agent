"""Build a reviewable serving-code package, without a quality override or activation."""
import json,shutil,importlib.util
from pathlib import Path
from bootstrap import R,A,C,pin
pin()
from semantic_runtime.contracts import sha,write
active=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';pointer=json.loads(active.read_text());release=json.loads((R/pointer['manifest_path']).read_text());source=R/release['code_root']
output=A/'artifacts/review-package-v4';assert not output.exists()
for rel,h in release['files'].items():assert sha(source/rel)==h
shutil.copytree(source,output,ignore=shutil.ignore_patterns('__pycache__'))
c=json.loads((C/'candidate.json').read_text());rev=c['revisions'][-1]
for f in rev['files']:
 rel=f['frozen_path'].split('/snapshot/',1)[1];target=output/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/f['frozen_path'],target)
# Metadata-only copies satisfy the existing packaging verifier; data stays externally bound.
config=json.loads((output/'00_SYSTEM/PIPELINE.json').read_text())
for node in config['profiles']['legal-rag']['nodes']:
 term=node.get('parameters',{}).get('term_agent')
 if not term:continue
 paths=[Path(term['index']['path'])/'manifest.json']
 if term.get('fulltext'):paths.append(Path(term['index']['path']).parent/term['fulltext']['path']/'manifest.json')
 for kind in ('origin_projections','alias_projections'):paths.extend(Path(b['path']) for b in term.get(kind,[]))
 for rel in paths:
  target=output/rel
  if not target.exists():target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/rel,target)
# Existing packaging entrypoint emits schema, domain, profile and engine bindings.
p=output/'00_SYSTEM/LEGAL_AGENT/profile-tools-v5.json'
profile=json.loads(p.read_text());profile.update(max_core_sources=0,max_supplemental_sources=0,auto_reference_read_depth=0);p.write_text(json.dumps(profile,ensure_ascii=False,indent=2)+'\n')
spec=importlib.util.spec_from_file_location('package_contracts',R/'06_TOOLS/COMMANDS/legal_agent_contracts.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.build_v5(output,default=True)
manifest={'schema_version':'adr0521-review-package-v1','candidate_revision':rev['revision_id'],'candidate_sha256':rev['revision_sha256'],'base_release':pointer['release_id'],'active_sha256':sha(active),'code_root':str(output.relative_to(R)),'files':{str(p.relative_to(output)):sha(p) for p in sorted(output.rglob('*')) if p.is_file() and '__pycache__' not in p.parts},'activation':False,'quality_certified':False,'runtime_registry_registered':False,'purpose':'Review and isolated serving validation. Not an activated release.','promotion_blockers':['No out-of-sample model-assisted retrieval/answer validation','Current promotion dispatcher requires a quality waiver forbidden for this experiment']}
write(A/'artifacts/review-package.json',manifest);print(json.dumps({'files':len(manifest['files']),'path':str(output),'activation':False}))
