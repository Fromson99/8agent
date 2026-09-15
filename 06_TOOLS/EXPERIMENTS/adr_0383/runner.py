from pathlib import Path
import sys,json,hashlib,importlib,importlib.util
R=Path(__file__).resolve().parents[3]
C=R/'02_BACKEND/lawrag/research/candidates/adr_0383/gemini'
def install():
 m=json.loads((C/'candidate.json').read_text());rev=next(r for r in m['revisions'] if r['revision_id']=='rev-001')
 sys.path.insert(0,str(R/'02_BACKEND'));sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'))
 import types
 pkg=types.ModuleType('scripts');pkg.__path__=[str(R/'06_TOOLS/COMMANDS')];pkg.__package__='scripts';sys.modules['scripts']=pkg
 for name,target in [('scripts.adr_structure','06_TOOLS/COMMANDS/adr_structure.py'),('lawrag.research.experiment_client','02_BACKEND/lawrag/research/experiment_client.py')]:
  row=next(x for x in rev['files'] if x['snapshot_path'].endswith('/snapshot/'+target));p=R/row['frozen_path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==row['snapshot_sha256']
  parent,attr=name.rsplit('.',1);pkg=importlib.import_module(parent);spec=importlib.util.spec_from_file_location(name,p);mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);setattr(pkg,attr,mod)
 return m,rev
if __name__=='__main__':
 install()
 import pytest
 raise SystemExit(pytest.main(sys.argv[1:]))
