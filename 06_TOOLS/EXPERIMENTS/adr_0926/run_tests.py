from pathlib import Path
import hashlib,json,os,runpy,sys
R=Path(__file__).resolve().parents[3];D=R/'04_EXPERIMENTS/ADR/ADR-0926-connected-source-release-qualification/artifacts/design'
f=json.loads((D/'freeze.json').read_text())
for n,h in f['files'].items():
    assert hashlib.sha256((R/n).read_bytes()).hexdigest()==h,n
os.environ['TASK_TEST_CODE_ROOT']=str(R/json.loads((D/'binding.json').read_text())['code_root'])
sys.path.insert(0,str(R/'06_TOOLS/EXPERIMENTS/adr_0924'))
runpy.run_path(str(R/'06_TOOLS/EXPERIMENTS/adr_0895/run_tests.py'),run_name='__main__')
