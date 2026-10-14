from pathlib import Path
import hashlib,json,subprocess,sys,os,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0774-assessment-gap-action-main';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');b=read(D/'baseline.json');code=R/f['code_root'];paired={k:read(O/(k+'.json')) for k in ['baseline','source-gap-action']}
assert not (O/'contracts.xml').exists() and not (O/'result.json').exists()
assert 'FileNotFoundError' in (O/'contracts.log').read_text()
for p,h in f['files'].items():assert sha(R/p)==h,p
put(O/'fixture-setup-recovery.json',{'initial_failure':'Fixture import before pytest collection: copied conftest defaulted workspace root to frozen snapshot lacking glossary authoring data','fix':'Explicit LAWRAG_WORKSPACE_ROOT/LAWRAG_TOOL_WORKSPACE_ROOT point to canonical local test support; product imports and contracts_root remain frozen candidate','model_calls':0,'matrix_rerun':False,'test_results_before_fix':0,'product_or_fixture_code_changed':False})
tests=[str(code/'05_TESTS/CONTRACTS'/x) for x in read(D/'criteria.json')['regression_suites']]
with (O/'contracts-attempt-002.log').open('w') as out:
 result=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0774/run_tests.py',str(code),*tests,'--junitxml='+str(O/'contracts.xml')],cwd=R,env={**os.environ,'LAWRAG_WORKSPACE_ROOT':str(R),'LAWRAG_TOOL_WORKSPACE_ROOT':str(R)},stdout=out,stderr=subprocess.STDOUT)
# Resume the frozen runner after its pending contract invocation. No matrix rerun.
source=(R/'06_TOOLS/EXPERIMENTS/adr_0774/audit.py').read_text();exec(compile(source[source.index('cases=list(ET.parse'):],str(R/'06_TOOLS/EXPERIMENTS/adr_0774/audit.py'),'exec'))
