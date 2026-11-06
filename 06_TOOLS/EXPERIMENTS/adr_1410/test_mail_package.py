from common import *
import shutil,subprocess,zipfile
H=ROOT/read(ART/'mail-package.json')['handoff'];OUT=ART/'mail-package-tests-r3';OUT.mkdir(exist_ok=False)
checkout=OUT/'checkout';checkout.mkdir();before=read(DES/'baseline.json')['release'];old=ROOT/before['code_root']
for n in before['files']:
 p=checkout/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(old/n,p)
for n,raw in {'.env':'SYNTHETIC_KEEP=1\n','01_DATA/preserve.txt':'synthetic data','90_RUNTIME/preserve.txt':'synthetic runtime'}.items():
 p=checkout/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(raw)
preserved={n:sha(checkout/n) for n in ('.env','01_DATA/preserve.txt','90_RUNTIME/preserve.txt')}
commands=[]
def run(label,args,cwd=checkout,env=None):
 log=OUT/(label+'.log')
 with log.open('x') as out:r=subprocess.run(list(map(str,args)),cwd=cwd,stdout=out,stderr=subprocess.STDOUT,env=env)
 commands.append({'label':label,'exit_code':r.returncode,'log':str(log.relative_to(ROOT))});put(OUT/'commands.json',commands)
 assert r.returncode==0,label
run('git-init',['git','init','-q']);run('git-name',['git','config','user.name','Codex isolated handoff test']);run('git-email',['git','config','user.email','codex-test@localhost'])
run('base-stage',['git','add','-f','.']);run('base-commit',['git','commit','-qm','Existing MAIN150 fixture'])
python311=Path('/home/jin/.local/bin/python3.11')
script="import zipfile,sys; z=zipfile.ZipFile(sys.argv[1]); rows=[n for n in z.namelist() if n.endswith('.py')]; [compile(z.read(n),n,'exec') for n in rows]; print('PYTHON311_COMPILE_PASS',len(rows))"
run('python311-syntax',[python311,'-c',script,H/'MAIN151_FULL_20261105_R1.zip'])
link=Path.home()/'DEV';assert not os.path.lexists(link), 'Existing DEV must not be replaced'
link.symlink_to(checkout,target_is_directory=True)
base_env=os.environ.copy();base_env.pop('GENOS_PYTHON',None);base_env['PYTHONDONTWRITEBYTECODE']='1'
try:
 run('default-apply',['bash','MAIN151_ONECLICK_R1.txt'],cwd=H,env=base_env)
 receipts=list((checkout/'09_ARTIFACTS/BACKUPS/code-replacement').glob('*/receipt.json'));assert len(receipts)==1;backup=receipts[0].parent
 assert all(sha(checkout/n)==h for n,h in preserved.items())
 run('same-apply',['bash','MAIN151_ONECLICK_R1.txt'],cwd=H,env=base_env)
 run('status',['bash','MAIN151_ONECLICK_R1.txt','status'],cwd=H,env=base_env)
 run('stage',['bash','MAIN151_ONECLICK_R1.txt','stage'],cwd=H,env=base_env)
 run('diff-check',['git','diff','--cached','--check'])
 run('commit',['git','commit','-qm','MAIN151 verified code package'])
 run('gate-code',['bash','MAIN151_ONECLICK_R1.txt','gate-code'],cwd=H,env=base_env)
 run('generation-gate',[ROOT/'.venv/bin/python',checkout/'06_TOOLS/COMMANDS/genos_release_gate.py','--code-zip',H/'MAIN151_FULL_20261105_R1.zip','--deploy-root',checkout,'--generation',ROOT/before['data_path']],env=base_env)
 commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=checkout,text=True).strip()
 put(OUT/'validated-deployment-checkout.json',{'root':str(checkout),'commit':commit,'zip_sha256':sha(H/'MAIN151_FULL_20261105_R1.zip'),'generation':str(ROOT/before['data_path']),'generation_manifest_sha256':sha(ROOT/before['data_path']/'manifest.json'),'field_checkout':None,'field_revision':None,'field_verified':False})
 run('undo',['bash','MAIN151_ONECLICK_R1.txt','undo','--backup',backup],cwd=H,env=base_env)
 assert all(sha(checkout/n)==h for n,h in before['files'].items())
 assert all(sha(checkout/n)==h for n,h in preserved.items())
 assert not (checkout/'02_BACKEND/semantic_runtime/legal_agent/guided_answer.py').exists()
 put(OUT/'result.json',{'passed':True,'commands':commands,'default_DEV_symlink':True,'default_command':'bash MAIN151_ONECLICK_R1.txt','original_files_restored':len(before['files']),'preserved':preserved,'full_generation_gate':True,'user_checkout_changed':False,'new_model_calls':0,'field_deployed':False})
finally:
 assert link.is_symlink() and link.resolve()==checkout.resolve();link.unlink()
print('Package exact default install, repeat, stage/commit, full generation gate, undo PASS')
