"""Focused tests against one explicit frozen code map, never selected MAIN."""
from pathlib import Path
import hashlib,json,os,sys,time
import pytest
ROOT=Path(__file__).resolve().parents[3]
ART=ROOT/'04_EXPERIMENTS/ADR/ADR-1072-definition-link-visibility-point-check/artifacts'
code=Path(sys.argv[1]).resolve();name=sys.argv[2]
if not name or Path(name).name != name:raise ValueError('validation output name must be a basename')
if (ART/(name+'.json')).exists():raise ValueError('validation result already exists; never overwrite')
candidate_root=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1072/profile-optimized-r2'
if code.parent.parent.parent != candidate_root or code.name != 'snapshot' or code.parent.parent.name != 'revisions':
    raise ValueError('explicit ADR1072 B2 frozen snapshot required')
candidate_data=json.loads((candidate_root/'candidate.json').read_text())
revision=next(row for row in candidate_data['revisions'] if row['revision_id']==code.parent.name)
canonical=lambda value:json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
if hashlib.sha256(canonical({k:v for k,v in revision.items() if k!='revision_sha256'})).hexdigest()!=revision['revision_sha256']:
    raise ValueError('frozen revision metadata hash mismatch')
if candidate_data['experiment_id']!='ADR-1072-experiment-v1' or candidate_data['arm_id']!='B2' or candidate_data['run_ids']!=['run-001']:
    raise ValueError('candidate arm/run linkage mismatch')
sys.dont_write_bytecode=True
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT),ADR1072_OPTIMIZED_SNAPSHOT=str(code))
os.chdir(code);sys.path[:0]=[str(code/'02_BACKEND'),str(code),str(code/'05_TESTS'),str(code/'05_TESTS/CONTRACTS')]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def files():return {str(p.relative_to(code)):sha(p) for p in code.rglob('*') if p.is_file()}
before=files()
expected={str((ROOT/row['frozen_path']).relative_to(code)):row['snapshot_sha256'] for row in revision['files']}
if before!=expected:raise ValueError('frozen candidate file map mismatch before tests')
tests=[]
for item in sys.argv[3:]:
    path,node=(item.split('::',1)+[None])[:2] if '::' in item else (item,None)
    p=Path(path)
    if not p.is_absolute():p=code/'05_TESTS/CONTRACTS'/p
    tests.append(str(p)+('::'+node if node else ''))
class Results:
    def __init__(self):self.rows=[]
    def pytest_runtest_logreport(self,report):
        r=report
        if r.when=='call' or r.failed:self.rows.append({'nodeid':r.nodeid,'when':r.when,'outcome':r.outcome,'error':r.longreprtext if r.failed else None})
plugin=Results();start=time.perf_counter()
status=pytest.main(['-c','/dev/null','--confcutdir='+str(code),'-q','--tb=short','--show-capture=no','-p','no:cacheprovider','-o','faulthandler_timeout=45',*tests],plugins=[plugin])
imports={n:str(Path(m.__file__).resolve()) for n,m in sys.modules.items() if n.split('.')[0] in ('semantic_runtime','lawrag','genos_timing_probe','service') and getattr(m,'__file__',None)}
leaks={n:p for n,p in imports.items() if not Path(p).is_relative_to(code)}
after=files()
value={'status':int(status),'elapsed_seconds':time.perf_counter()-start,'passed':sum(r['outcome']=='passed' for r in plugin.rows),'failed':sum(r['outcome']=='failed' for r in plugin.rows),'rows':plugin.rows,'code_root':str(code.relative_to(ROOT)),'revision_sha256':revision['revision_sha256'],'files':before,'candidate_changed':before!=after,'imports':imports,'import_leaks':leaks,'live_model_calls':0,'real_corpus_loads':0}
with (ART/(name+'.json')).open('x',encoding='utf-8') as stream:stream.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
print('BINDING',json.dumps({'imports':len(imports),'leaks':len(leaks),'changed':before!=after}))
raise SystemExit(int(bool(status or leaks or before!=after)))
