from pathlib import Path
import hashlib,json,os,runpy,sys
R=Path(__file__).resolve().parents[3]
D=R/'04_EXPERIMENTS/ADR/ADR-0939-research-continuity-qualified/artifacts/design'
freeze=json.loads((D/'freeze.json').read_text())
for name,expected in freeze['files'].items():
    assert hashlib.sha256((R/name).read_bytes()).hexdigest()==expected,name
binding=json.loads((D/'connected-binding.json').read_text())
os.environ['TASK_TEST_CODE_ROOT']=str(R/binding['code_root'])
sys.path.insert(0,str(R/'06_TOOLS/EXPERIMENTS/adr_0936'))
runpy.run_path(str(R/'06_TOOLS/EXPERIMENTS/adr_0895/run_tests.py'),run_name='__main__')
