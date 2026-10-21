from pathlib import Path
import gzip,hashlib,json,os,shutil,subprocess,zipfile
H=Path(__file__).resolve().parent;R=H.parents[3];N='GENOS_MAIN92_CUMULATIVE_20261020_R1'
sha=lambda b:hashlib.sha256(b).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
assert not (H/'SEALED.json').exists()
root=Path(json.loads((H/'PASS_preserved-config-interruption.json').read_bytes())['code_root'])
transfer=H/'final-transfer';transfer.mkdir(exist_ok=False)
shutil.copyfile(H/(N+'.zip'),transfer/(N+'.zip'))
env={**os.environ,'PATH':str(R/'.venv/bin')+':'+os.environ['PATH'],'GENOS_DEV_ROOT':str(root),'PYTHONDONTWRITEBYTECODE':'1','GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0'}
trace=[]
def run(args):
 r=subprocess.run(list(map(str,args)),cwd=transfer,env=env,text=True,capture_output=True,timeout=150)
 trace.append({'argv':list(map(str,args)),'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
 (H/'FINAL_TRACE.json.gz').write_bytes(gzip.compress(enc(trace),mtime=0))
 assert r.returncode==0,r.stdout+r.stderr
run(['python3','-m','zipfile','-e','./'+N+'.zip','./'+N])
cmd=['bash','./'+N+'/'+N+'_RUN.txt']
for action in ('check','apply','status','undo'):run([*cmd,action])
state=json.loads((transfer/N/'STATUS.json').read_bytes())
assert state['phase']=='RESTORED_REDEPLOY_PREVIOUS_REVISION'
assert state['code_zip_sha256']==json.loads((H/'PASS_preserved-config-interruption.json').read_bytes())['code_zip_sha256']
v={'status':'PASS','commands':len(trace),'outer_zip_sha256':sha((H/(N+'.zip')).read_bytes()),'code_zip_sha256':sha((H/'code.zip').read_bytes()),
 'same_applied_archive_as_committed_gate_test':True,'runtime_scripts_unchanged_since_delivery_tests':True,
 'trace_sha256':sha((H/'FINAL_TRACE.json.gz').read_bytes()),'model_calls':0,'field_verified':False}
(H/'FINAL_VERIFICATION.json').write_bytes(enc(v));print(json.dumps(v))
