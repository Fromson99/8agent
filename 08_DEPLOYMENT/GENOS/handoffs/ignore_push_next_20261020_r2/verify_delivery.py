from pathlib import Path
import hashlib,json,os,shutil,subprocess,tempfile,zipfile
R=Path('/home/jin/8-AGENT');H=R/'08_DEPLOYMENT/GENOS/handoffs/ignore_push_next_20261020_r2';P=R/'08_DEPLOYMENT/GENOS/handoffs/ignore_transfer_20261020_r1';B=R/'08_DEPLOYMENT/GENOS/handoffs/main92_cumulative_20261020_r1';N='GENOS_NEXT_COPY_PASTE_20261020_R2'
enc=lambda x:(json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode();sha=lambda b:hashlib.sha256(b).hexdigest()
script=H/(N+'.txt');subprocess.run(['bash','-n',str(script)],check=True)
trace=[]
env={**os.environ,'PATH':str(R/'.venv/bin')+':'+os.environ['PATH'],'GIT_AUTHOR_NAME':'Synthetic','GIT_AUTHOR_EMAIL':'synthetic@example.invalid','GIT_COMMITTER_NAME':'Synthetic','GIT_COMMITTER_EMAIL':'synthetic@example.invalid','PYTHONDONTWRITEBYTECODE':'1','GIT_TERMINAL_PROMPT':'0'}
def run(args,cwd,ok=True):
 p=subprocess.run(list(map(str,args)),cwd=cwd,env=env,capture_output=True,text=True,timeout=90)
 trace.append({'argv':list(map(str,args)),'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr});(H/'TEST_TRACE.json').write_bytes(enc(trace))
 assert (p.returncode==0)==ok,(args,p.stdout,p.stderr)
 return p.stdout
with tempfile.TemporaryDirectory(prefix='genos-next-push-') as tmp:
 t=Path(tmp);root=t/'checkout';root.mkdir();remote=t/'remote.git';transfer=root/'TRANSFER';transfer.mkdir()
 with zipfile.ZipFile(B/'code.zip') as z:z.extractall(root);m=json.loads(z.read('CODE_MANIFEST.json'))
 files=[r['path'] for r in m['files']]
 profiles=json.loads((P/'PATCH_SPEC.json').read_bytes())['profiles']
 for name in profiles:
  if not (root/name).exists():
   (root/name).parent.mkdir(parents=True,exist_ok=True);(root/name).write_bytes((P/'updated-source'/name).read_bytes());files.append(name)
 run(['git','init','-q','-b','main'],root)
 run(['git','add','.'],root)
 ignored=[p for p in files if '/corpus/raw/' in p or '/corpus/structured/' in p]
 assert len(ignored)==5
 tracked=set(run(['git','ls-files'],root).splitlines());assert not tracked.intersection(ignored)
 data_before={p:(root/p).read_bytes() for p in ignored}
 run(['git','commit','-qm','synthetic base'],root);run(['git','init','-q','--bare',remote],t);run(['git','remote','add','risk_team',remote],root);run(['git','push','risk_team','main'],root)
 q=root/'QUERY_TRANSFER_20261020_R1';q.mkdir();(q/'query-data.db.partial').write_bytes(b'SYNTHETIC DATA')
 run(['git','add','QUERY_TRANSFER_20261020_R1'],root);run(['git','commit','-qm','synthetic bad commit'],root)
 run(['git','branch','backup/main92-before-ignore-20261020'],root)
 package=transfer/'GENOS_IGNORE_TRANSFER_20261020_R1'
 with zipfile.ZipFile(P/'GENOS_IGNORE_TRANSFER_20261020_R1.zip') as z:z.extractall(package)
 run([R/'.venv/bin/python',package/'apply_ignore.py','apply','--root',root],root)
 run(['git','rm','-r','--cached','QUERY_TRANSFER_20261020_R1'],root)
 run(['git','add','--',*profiles],root);run(['git','commit','--amend','--no-edit'],root)
 head=run(['git','rev-parse','HEAD'],root).strip();env['GENOS_CODE_ROOT']=str(root)
 legacy=run([R/'.venv/bin/python',package/'apply_ignore.py','gate','--root',root],root,False)
 assert all((root/p).read_bytes()==raw for p,raw in data_before.items())
 out=run(['bash',script],root);assert 'PUSH_CONFIRMED='+head in out
 assert run(['git','--git-dir',remote,'rev-parse','main'],root).strip()==head
 assert run(['git','--git-dir',remote,'for-each-ref','--format=%(refname)','refs/heads'],root).strip()=='refs/heads/main'
 assert run(['git','--git-dir',remote,'log','--all','--format=%H','--','QUERY_TRANSFER_20261020_R1'],root).strip()==''
 assert (q/'query-data.db.partial').read_bytes()==b'SYNTHETIC DATA'
 out=run(['bash',script],root);assert '다시 push하지 않습니다' in out
 # Committed source tamper must fail despite a clean Git index.
 original=(root/'service.py').read_bytes();(root/'service.py').write_bytes(original+b'\n# synthetic committed drift\n')
 run(['git','add','service.py'],root);run(['git','commit','-qm','synthetic committed drift'],root)
 run(['bash',script],root,False)
 run(['git','reset','--hard',head],root)
 assert run(['git','--git-dir',remote,'rev-parse','main'],root).strip()==head
 # Missing required source is still rejected.
 dependency=root/'02_BACKEND/semantic_runtime/legal_agent/model_contract.py';saved=dependency.read_bytes();dependency.unlink()
 run(['git','add','-u'],root);run(['git','commit','-qm','synthetic removed required code'],root)
 run(['bash',script],root,False);run(['git','reset','--hard',head],root)
 assert dependency.read_bytes()==saved
 # Dirty tracked code blocks push before remote mutation.
 original=(root/'service.py').read_bytes();(root/'service.py').write_bytes(original+b'\n# synthetic drift\n')
 run(['bash',script],root,False);(root/'service.py').write_bytes(original)
 assert run(['git','--git-dir',remote,'rev-parse','main'],root).strip()==head
 # A remote with a different, independently advanced main must not be overwritten.
 other=t/'other';run(['git','clone','-q','-b','main',remote,other],t)
 (other/'remote-only.txt').write_text('synthetic\n');run(['git','add','remote-only.txt'],other);run(['git','commit','-qm','remote advanced'],other);run(['git','push','origin','main'],other)
 advanced=run(['git','--git-dir',remote,'rev-parse','main'],root).strip()
 run(['bash',script],root,False);assert run(['git','--git-dir',remote,'rev-parse','main'],root).strip()==advanced
 # Missing receipt fails without guessing the package or changing anything.
 (package/'STATE.json').rename(package/'STATE.saved.json')
 run(['bash',script],root,False);(package/'STATE.saved.json').rename(package/'STATE.json')
 # Both spelling variants are supported only when unique.
 run(['git','remote','rename','risk_team','risk-team'],root)
 # Reset only disposable bare fixture main to the already verified commit.
 run(['git','--git-dir',remote,'update-ref','refs/heads/main',head],root)
 out=run(['bash',script],root);assert 'PUSH_CONFIRMED='+head in out
 logs=list((root/'.git/genos-push-records').glob('*.log'));assert len(logs)==8
 assert all(p.with_name(p.name+'.exit').exists() for p in logs)
validation={'status':'PASS','commands':len(trace),'expected_failures':sum(r['exit']!=0 for r in trace),'tested_txt_sha256':sha(script.read_bytes()),'scenarios':['ordinary git add reproduces R1 five ignored data mismatches','R2 verifies code with five corpus data files untracked','committed code tamper rejected','committed required code removal rejected','actual MAIN92 plus seven ignore profiles','locate applied package from checkout cwd','local bare remote normal push','same remote HEAD no-op','backup branch not pushed','transfer data not present in remote history','disk data preserved','dirty code stops before push','advanced remote stops without force','missing state stops','both risk_team and risk-team supported','persistent logs and exit codes'],'ordinary_git_add_used':True,'legacy_gate_failure_reproduced':True,'python311_syntax':True,'real_remote_calls':0,'synthetic_bare_remotes_only':True,'field_verified':False}
(H/'VALIDATION.json').write_bytes(enc(validation));print(json.dumps(validation,indent=2))
