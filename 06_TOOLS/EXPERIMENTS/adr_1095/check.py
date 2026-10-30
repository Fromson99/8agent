"""One small sequential process; exact frozen product imports and recorded results."""
from pathlib import Path
import hashlib,json,os,sys,time
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1095-ontology-assess-wire'
f=json.loads((ADR/'artifacts/freeze.json').read_text());code=ROOT/f['code_root']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(Path(__file__))==f['binding']['runner_sha256']
for n,h in f['tests_sha256'].items():assert sha(Path(__file__).with_name(n))==h
manifest=json.loads((ROOT/f['binding']['manifest_path']).read_text());rev=next(r for r in manifest['revisions'] if r['revision_id']==f['binding']['revision_id'])
assert all(sha(ROOT/r['frozen_path'])==r['snapshot_sha256'] for r in rev['files'])
sys.dont_write_bytecode=True;os.environ.update(LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT))
os.chdir(code);sys.path[:0]=[str(code/'02_BACKEND'),str(code),str(code/'05_TESTS'),str(code/'05_TESTS/CONTRACTS')]
import pytest
tests=[str(code/'05_TESTS/CONTRACTS'/p) for p in ['test_ontology_compiler.py','test_ontology_context.py','test_ontology_review_adr1061.py','test_ontology_api.py','test_action_choice_ontology_adr1066.py','test_compact_model_input.py','test_compact_wire_binding.py','test_journal_evidence_batch.py','test_action_choice_contract_adr1066.py','test_action_choice_repair_adr1066.py']]
tests.extend(str(Path(__file__).with_name(n)) for n in f['tests_sha256'])
class Results:
 def __init__(self):self.rows=[]
 def pytest_runtest_logreport(self,report):
  r=report
  if r.when=='call' or r.failed:self.rows.append({'test':r.nodeid,'when':r.when,'status':r.outcome,'error':r.longreprtext if r.failed else None})
plugin=Results();start=time.perf_counter()
rc=pytest.main(['-c','/dev/null','--confcutdir='+str(code),'-q','-s','--tb=short','--show-capture=no','-p','no:cacheprovider',*tests],plugins=[plugin])
imports={n:str(Path(v.__file__).resolve()) for n,v in sys.modules.items() if n.split('.')[0] in ('semantic_runtime','lawrag') and getattr(v,'__file__',None)}
leaks={n:p for n,p in imports.items() if not Path(p).is_relative_to(code)}
changed=[r['frozen_path'] for r in rev['files'] if sha(ROOT/r['frozen_path'])!=r['snapshot_sha256']]
result={'status':int(rc),'passed':sum(r['status']=='passed' for r in plugin.rows),'failed':sum(r['status']=='failed' for r in plugin.rows),'seconds':time.perf_counter()-start,'rows':plugin.rows,'imports':imports,'import_leaks':leaks,'changed_files':changed,'code_root':f['code_root'],'new_model_calls':0,'real_corpus_loads':0}
out=ADR/'artifacts'/(sys.argv[1] if len(sys.argv)>1 else 'check.json')
if out.exists():raise RuntimeError('check receipt already exists')
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print('FROZEN',json.dumps({k:result[k] for k in ('passed','failed','import_leaks','changed_files','seconds')}))
raise SystemExit(int(bool(rc or leaks or changed)))
