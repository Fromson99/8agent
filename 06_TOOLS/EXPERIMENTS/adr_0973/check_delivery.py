"""Validate the actual handoff ZIP in a disposable existing Git checkout."""
from common import *
import gzip,os,subprocess,sys,tempfile,zipfile,importlib.util
P=ROOT/'08_DEPLOYMENT/GENOS/handoffs/structured_selection_20261021_r1';NAME='GENOS_STRUCTURED_SELECTION_20261021_R1'
package=read(P/'PACKAGE.json');audit=ROOT/'09_ARTIFACTS/AUDITS/20261021-natural-language-routing';base=read(audit/'GENOS_CODE.json')['base_code']
trace=[];environment={k:v for k,v in os.environ.items() if not k.startswith(('GENOS_','SEMANTIC_','LEGAL_AGENT_','LAWRAG_','PYTHON','WORKFLOW_','GIT_'))}
environment.update(PATH=str(ROOT/'.venv/bin')+':'+environment['PATH'],PYTHONDONTWRITEBYTECODE='1',AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
def call(args,cwd,ok=True,timeout=180):
 p=subprocess.run(list(map(str,args)),cwd=cwd,env=environment,capture_output=True,text=True,timeout=timeout)
 trace.append({'args':list(map(str,args)),'cwd':str(cwd),'exit':p.returncode,'output':p.stdout+p.stderr,'expected_success':ok})
 with gzip.open(P/'DELIVERY_TRACE.json.gz','wt') as f:json.dump(trace,f,ensure_ascii=False)
 assert (p.returncode==0)==ok,trace[-1]
 return p.stdout
with tempfile.TemporaryDirectory(prefix='zip-validation-',dir=ART) as temp:
 temp=Path(temp);code=temp/'DEV';transfer=temp/'uploaded-TRANSFER';code.mkdir();transfer.mkdir()
 with zipfile.ZipFile(audit/'GENOS_BASE.zip') as z:
  for n,h in base.items():
   raw=z.read(n);assert hashlib.sha256(raw).hexdigest()==h
   dst=code/n;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(raw)
 keep={'.env':b'TEAM_ID=\nAD_WORKER_ENABLED=0\n','00_SYSTEM/GENOS_SERVING_PATHS.json':b'{"generation":"/existing/field/path","runtime":"/existing/runtime"}\n','user-file.txt':b'keep the existing user file\n'}
 for n,b in keep.items():(code/n).write_bytes(b)
 call(['git','init','-q'],code);call(['git','config','user.email','fixture@example.invalid'],code);call(['git','config','user.name','Installer fixture'],code);call(['git','add','.'],code);call(['git','commit','-qm','Synthetic known baseline'],code)
 folder=transfer/NAME
 with zipfile.ZipFile(P/(NAME+'.zip')) as z:z.extractall(folder)
 def run(action,ok=True):return call(['bash',folder/(NAME+'_RUN.txt'),action,'--root',code],transfer,ok)
 run('check');run('gate',False)
 n='02_BACKEND/semantic_runtime/legal_agent/request_entry.py';target=code/n;before=target.read_bytes();target.write_bytes(before+b'\n# unknown edit\n')
 run('check',False);assert target.read_bytes()==before+b'\n# unknown edit\n';target.write_bytes(before)
 run('apply');run('apply');run('gate');run('status')
 assert all(sha(code/n)==h for n,h in package['code'].items())
 assert all((code/n).read_bytes()==b for n,b in keep.items())
 call(['git','diff','--check'],code);call(['git','add','--',*package['patch']],code);call(['git','commit','-qm','Synthetic exact qualified payload'],code);run('gate-code')
 support_spec=importlib.util.spec_from_file_location('installer_test_support',audit/'test_support.py');support=importlib.util.module_from_spec(support_spec);support_spec.loader.exec_module(support)
 support.TESTS=['test_required_structure_selection','test_model_structure_selection','test_natural_language_routing','test_structural_scope_output_recovery'];support.install(code)
 for names in [('test_required_structure_selection','test_model_structure_selection','test_structural_scope_output_recovery'),('test_natural_language_routing',)]:
  call([ROOT/'.venv/bin/python','-B','-m','pytest','-q',*[f'05_TESTS/CONTRACTS/{x}.py' for x in names],'--tb=short'],code)
 assert all(sha(code/n)==h for n,h in package['code'].items())
 after=target.read_bytes();target.write_bytes(after+b'\n# newer user edit\n');run('rollback',False);assert target.read_bytes()==after+b'\n# newer user edit\n';target.write_bytes(after)
 run('rollback');run('check');run('apply',False)
 assert all(sha(code/n)==h for n,h in base.items())
 assert all(not (code/n).exists() for n in package['code'] if n not in base)
 assert all((code/n).read_bytes()==b for n,b in keep.items())
 for exit_file in (transfer/'structured-selection-r1-logs').glob('*.exit'):assert exit_file.read_text().strip() in ('0','1','2')
save(P/'DELIVERY_VALIDATION.json',{'passed':True,'commands':len(trace),'installer':'actual ZIP check/apply/idempotency/committed checkout gate/unknown-byte refusal/rollback/newer-edit preservation','installed_contracts':80,'archive_sha256':sha(P/(NAME+'.zip')),'code_files':len(package['code']),'source_code_identical_to_qualified_main':True,'synthetic_only':True,'GENOS_field_verified':False})
print('Final ZIP installed contracts and installer lifecycle PASS',len(trace))
