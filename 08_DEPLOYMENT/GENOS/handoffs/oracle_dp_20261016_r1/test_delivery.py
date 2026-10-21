"""Install exact mailed delta into a real isolated Git checkout of sealed MAIN81 R2."""
import hashlib,json,os,shutil,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];H=Path(__file__).resolve().parent
AUDIT=ROOT/'09_ARTIFACTS/AUDITS/20261016-legal-agent-rag-source-first/oracle_dp_20261016_r1'
case=AUDIT/'installed-main81-r2-c';case.mkdir(exist_ok=True)
code=case/'DEV';transfer=case/'TRANSFER';transfer.mkdir(exist_ok=True)
def run(args,cwd=code,success=True,env=None):
    result=subprocess.run(list(map(str,args)),cwd=cwd,env=env,capture_output=True,text=True)
    with (case/'commands.txt').open('a') as f:f.write('$ '+str(args)+'\n'+result.stdout+result.stderr+'\nEXIT='+str(result.returncode)+'\n')
    if (result.returncode==0)!=success:raise RuntimeError('Unexpected exit '+str(result.returncode)+'; see '+str(case/'commands.txt'))
    return result
if not code.exists():
    code.mkdir()
    with zipfile.ZipFile(H.parent/'main_full_20261016_r2/code.zip') as z:z.extractall(code)
    run(['git','init','-q']);run(['git','add','-f','.'])
    run(['git','-c','user.name=DP fixture','-c','user.email=dp-fixture@example.invalid','commit','-qm','Sealed MAIN81 R2 fixture'])
name='GENOS_ORACLE_DP_20261016_R1_RUN.txt';shutil.copyfile(H/name,transfer/name)
env={**os.environ,'GENOS_PYTHON_DIR':str(Path(sys.executable).parent),'PYTHONDONTWRITEBYTECODE':'1','AD_WORKER_ENABLED':'0'}
script=['bash','./'+name]
run([*script,'check','--root',code],cwd=transfer,env=env)
run([*script,'apply','--root',code],cwd=transfer,env=env)
run([*script,'apply','--root',code],cwd=transfer,env=env)
# The final archive gate must compare committed bytes in this DEV, not extracted candidate files.
run(['git','add','-f','service.py','CODE_MANIFEST.json','02_BACKEND/semantic_runtime/oracle_dp.py','02_BACKEND/semantic_runtime/oracle_dp_assets.py','02_BACKEND/semantic_runtime/oracle_dp_io.py','02_BACKEND/lawrag/pipeline/oracle_migration.py','02_BACKEND/lawrag/pipeline/oracle_publish.py'])
run(['git','-c','user.name=DP fixture','-c','user.email=dp-fixture@example.invalid','commit','-qm','Oracle DP installed fixture'])
run([*script,'gate-code','--root',code],cwd=transfer,env=env)
for p in (ROOT/'05_TESTS').rglob('*.py'):
    if '__pycache__' in p.parts:continue
    target=code/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
# Read-only test artifact used by standalone cell verification.
source=ROOT/'08_DEPLOYMENT/DATAIKU/legal_oracle_dp_20261016_r1/LEGAL_ORACLE_FULL_TRANSFER_20261016_R1_CELL.txt'
target=code/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
source=H/'GENOS_ORACLE_DP_20261016_R1_PUBLISH_CELL.txt';target=code/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
(code/'pytest.ini').write_text('[pytest]\npythonpath = 02_BACKEND\n')
testenv={**env,'PYTHONPATH':str(code/'02_BACKEND'),'LAWRAG_WORKSPACE_ROOT':str(code),'LAWRAG_TOOL_WORKSPACE_ROOT':str(code),'GENOS_AUTO_WARMUP':'0'}
result=run([sys.executable,'-m','pytest','-c',code/'pytest.ini','-q','05_TESTS/CONTRACTS/test_oracle_dp.py','05_TESTS/CONTRACTS/test_oracle_dp_runtime.py','05_TESTS/CONTRACTS/test_genos_compact_service_boot.py','--basetemp',case/'pytest'],env=testenv)
(case/'pytest.txt').write_text(result.stdout+result.stderr)
# Unknown file changes must never be overwritten during apply/undo.
p=code/'service.py';expected=p.read_bytes();p.write_bytes(expected+b'\n# unrelated edit\n')
run([*script,'apply','--root',code],cwd=transfer,env=env,success=False)
run([*script,'undo','--root',code],cwd=transfer,env=env,success=False)
p.write_bytes(expected)
run([*script,'undo','--root',code],cwd=transfer,env=env)
run([*script,'undo','--root',code],cwd=transfer,env=env)
with zipfile.ZipFile(H.parent/'main_full_20261016_r2/code.zip') as z:
    assert (code/'service.py').read_bytes()==z.read('service.py')
    assert (code/'CODE_MANIFEST.json').read_bytes()==z.read('CODE_MANIFEST.json')
assert not (code/'02_BACKEND/semantic_runtime/oracle_dp.py').exists()
report={'status':'PASS','base':'mailed MAIN81 R2','installed_code_root':str(code),'python':sys.executable,
        'package_binding':json.loads((H/'PACKAGE_BINDING.json').read_text()),'functional_tests':result.stdout,
        'checks':['standalone RUN check/apply/idempotent apply','real Git commit + full code archive gate','installed service + Oracle fixture cold/warm/rows/RAG','conflicting file rejection','undo/idempotent undo'],
        'field_oracle_engine':'NOT_TESTED','field_network':'NOT_ACCESSED','model_calls':'SYNTHETIC_TRANSPORT_ONLY',
        'field_full_migration':'USER_EXECUTION_PENDING','field_revision':'NOT_DEPLOYED'}
(H/'VALIDATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('INSTALLED_DELIVERY_PASS')
