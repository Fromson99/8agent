from pathlib import Path
import importlib,importlib.util,sys,json,hashlib
R=Path('/home/jin/8-AGENT')
C=R/'02_BACKEND/lawrag/research/candidates/adr_0392/patches'
def install():
 m=json.loads((C/'candidate.json').read_text());rev=next(r for r in m['revisions'] if r['revision_id']=='rev-001')
 for row in rev['files']:
  path=R/row['frozen_path']
  assert hashlib.sha256(path.read_bytes()).hexdigest()==row['snapshot_sha256']
 order=['lawrag.research.experiment_client','lawrag.core.structure.recipe_visual_loop','lawrag.core.structure.recipe_patch','lawrag.core.structure.recipe_evidence','lawrag.core.structure.recipe_pages','lawrag.core.structure.recipe_runtime']
 for name in order:
  target='02_BACKEND/'+name.replace('.','/')+'.py';row=next(r for r in rev['files'] if r['snapshot_path'].endswith('/snapshot/'+target));p=R/row['frozen_path']
  parent,attr=name.rsplit('.',1);pkg=importlib.import_module(parent)
  spec=importlib.util.spec_from_file_location(name,p);mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);setattr(pkg,attr,mod)
 return m,rev
if __name__=='__main__':
 install()
 import pytest
 raise SystemExit(pytest.main(sys.argv[1:]))
