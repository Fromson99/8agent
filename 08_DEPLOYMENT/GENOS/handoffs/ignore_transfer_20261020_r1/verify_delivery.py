from pathlib import Path
import ast,base64,hashlib,json,os,shutil,subprocess,tempfile,zipfile
R=Path('/home/jin/8-AGENT');H=R/'08_DEPLOYMENT/GENOS/handoffs/ignore_transfer_20261020_r1';B=R/'08_DEPLOYMENT/GENOS/handoffs/main92_cumulative_20261020_r1';N='GENOS_IGNORE_TRANSFER_20261020_R1'
sha=lambda b:hashlib.sha256(b).hexdigest();enc=lambda x:(json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode()
ship_files=['apply_ignore.py','IGNORE_RULES.txt','MAIN92_BASE_INVENTORY.json','PATCH_SPEC.json','GUIDE_UTF8.txt',N+'_RUN.txt',*[p.relative_to(H).as_posix() for p in (H/'updated-source').rglob('*') if p.is_file()]]
for file in ship_files:
 if file.endswith('.py'):ast.parse((H/file).read_text(),feature_version=(3,11))
subprocess.run(['bash','-n',str(H/(N+'_RUN.txt'))],check=True)
with zipfile.ZipFile(H/(N+'.zip'),'w',zipfile.ZIP_DEFLATED) as z:
 for name in ship_files:z.write(H/name,name)
trace=[]
env={**os.environ,'PATH':str(R/'.venv/bin')+':'+os.environ['PATH'],'PYTHONDONTWRITEBYTECODE':'1','GIT_AUTHOR_NAME':'Synthetic Check','GIT_AUTHOR_EMAIL':'synthetic@example.invalid','GIT_COMMITTER_NAME':'Synthetic Check','GIT_COMMITTER_EMAIL':'synthetic@example.invalid'}
def run(argv,cwd,ok=True):
 p=subprocess.run(list(map(str,argv)),cwd=cwd,env=env,capture_output=True,text=True,timeout=90)
 trace.append({'argv':list(map(str,argv)),'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
 (H/'TEST_TRACE.json').write_bytes(enc(trace))
 assert (p.returncode==0)==ok,(argv,p.stdout,p.stderr)
 return p
with tempfile.TemporaryDirectory(prefix='genos-ignore-delivery-') as tmp:
 T=Path(tmp);root=T/'checkout';root.mkdir();transfer=T/'uploaded-transfer';transfer.mkdir()
 with zipfile.ZipFile(B/'code.zip') as z:
  z.extractall(root);m=json.loads(z.read('CODE_MANIFEST.json'))
 (root/'00_SYSTEM/GENOS_SERVING_PATHS.json').write_text('{"fixture":"preserved"}\n')
 run(['git','init','-q','-b','main'],root)
 names=[x['path'] for x in m['files']]+['00_SYSTEM/GENOS_SERVING_PATHS.json']
 p=subprocess.run(['git','-C',str(root),'add','-f','--pathspec-from-file=-','--pathspec-file-nul'],input=('\0'.join(names)+'\0').encode(),env=env,capture_output=True)
 assert p.returncode==0,p.stderr
 run(['git','commit','-qm','synthetic MAIN92 base'],root)
 originals={p:(root/p).read_bytes() for p in ['.gitignore','genosIgnore','service.py','00_SYSTEM/GENOS_SERVING_PATHS.json']}
 q=root/'QUERY_TRANSFER_20261020_R1';q.mkdir();(q/'query-data.db.partial').write_bytes(b'SYNTHETIC ONLY\0');(q/'events.jsonl').write_text('{}\n')
 run(['git','add','QUERY_TRANSFER_20261020_R1'],root);run(['git','commit','-qm','synthetic interrupted push commit'],root)
 shutil.copyfile(H/(N+'.zip'),transfer/(N+'.zip'));shutil.copyfile(H/(N+'_RUN.txt'),transfer/(N+'_RUN.txt'))
 # Separate TXT exercises its own archive extraction.
 cmd=['bash','./'+N+'_RUN.txt'];run([*cmd,'check','--root',root],transfer)
 package=transfer/N
 before_index=run(['git','ls-files','-s'],root).stdout
 run([*cmd,'apply','--root',root],transfer);run([*cmd,'apply','--root',root],transfer)
 assert run(['git','ls-files','-s'],root).stdout==before_index
 run([*cmd,'status','--root',root],transfer);run([*cmd,'gate','--root',root],transfer,False)
 state=json.loads((package/'STATE.json').read_bytes())
 assert state['config_sha256']==sha(originals['00_SYSTEM/GENOS_SERVING_PATHS.json'])
 # Resume a saved partially applied state without losing backup bytes.
 (root/'genosIgnore').write_bytes(base64.b64decode(state['files']['genosIgnore']['before']))
 state['phase']='APPLYING';(package/'STATE.json').write_bytes(enc(state))
 run([*cmd,'apply','--root',root],transfer)
 # Unrelated field edits must not be overwritten.
 expected=(root/'.gitignore').read_bytes();(root/'.gitignore').write_bytes(expected+b'\nsite-edit/\n')
 run([*cmd,'apply','--root',root],transfer,False);assert (root/'.gitignore').read_bytes().endswith(b'site-edit/\n')
 (root/'.gitignore').write_bytes(expected)
 # Only a disposable fixture's unpublished last commit is amended here.
 run(['git','rm','-r','--cached','--','QUERY_TRANSFER_20261020_R1'],root)
 assert (q/'query-data.db.partial').read_bytes()==b'SYNTHETIC ONLY\0'
 run(['git','add','--','.gitignore','genosIgnore'],root);run(['git','commit','--amend','--no-edit'],root)
 run([*cmd,'gate','--root',root],transfer)
 assert not run(['git','log','--format=%H','--all','--','QUERY_TRANSFER_20261020_R1'],root).stdout.strip()
 # A committed runtime change cannot be masked as an ignore patch.
 (root/'service.py').write_bytes(originals['service.py']+b'\n# synthetic drift\n')
 run(['git','add','service.py'],root);run(['git','commit','-qm','synthetic drift'],root)
 run([*cmd,'gate','--root',root],transfer,False)
 (root/'service.py').write_bytes(originals['service.py'])
 raw=(package/'IGNORE_RULES.txt').read_bytes();(package/'IGNORE_RULES.txt').write_bytes(raw+b'tamper/\n')
 run([*cmd,'check','--root',root],transfer,False);(package/'IGNORE_RULES.txt').write_bytes(raw)
 run([*cmd,'undo','--root',root],transfer);run([*cmd,'undo','--root',root],transfer)
 for name,raw in originals.items():assert (root/name).read_bytes()==raw,name
 assert (q/'query-data.db.partial').read_bytes()==b'SYNTHETIC ONLY\0'
 assert all((p.with_name(p.name+'.exit')).is_file() for p in (transfer/'genos-ignore-r1-logs').glob('*.log'))
 # Existing optional profiles and site-specific rules are retained.
 other=T/'second-checkout';other.mkdir();(other/'service.py').write_text('# synthetic\n')
 spec=json.loads((H/'PATCH_SPEC.json').read_bytes())
 for name in spec['profiles']:
  target=other/name;target.parent.mkdir(parents=True,exist_ok=True)
  target.write_bytes((H/'updated-source'/name).read_bytes()+b'\n# site-specific preserved\n/onsite-cache/\n')
 run(['git','init','-q','-b','main'],other);run(['git','add','.'],other);run(['git','commit','-qm','synthetic optional profiles'],other)
 t2=T/'transfer2';t2.mkdir();shutil.copyfile(H/(N+'.zip'),t2/(N+'.zip'))
 run(['python3','-m','zipfile','-e','./'+N+'.zip','./'+N],t2)
 cmd2=['bash','./'+N+'/'+N+'_RUN.txt']
 run([*cmd2,'check','--root',other],t2);run([*cmd2,'apply','--root',other],t2);run([*cmd2,'status','--root',other],t2)
 state2=json.loads((t2/N/'STATE.json').read_bytes());assert len(state2['files'])==7
 for name in state2['files']:assert b'/onsite-cache/' in (other/name).read_bytes()
 run([*cmd2,'undo','--root',other],t2)
(H/'TEST_TRACE.json').write_bytes(enc(trace))
validation={'status':'PASS','commands':len(trace),'intentional_failure_checks':sum(x['exit']!=0 for x in trace),'python311_syntax':True,'bash_syntax':True,'scenarios':['standalone TXT extraction','explicit zip extraction and extracted TXT','append preserves site rules','7 optional profiles','idempotence','interrupted apply resume','index untouched by installer','tracked transfer detection','synthetic unpublished commit cleanup preserves data','1306-file MAIN92 base plus ignore/config committed gate','runtime drift rejection','payload tamper rejection','post-apply user-edit rejection','exact undo and repeated undo','persistent logs and exit status'],'trace_sha256':sha((H/'TEST_TRACE.json').read_bytes()),'base_code_zip_sha256':sha((B/'code.zip').read_bytes()),'model_calls':0,'genos_field_verified':False,'remote_calls':0}
(H/'VALIDATION.json').write_bytes(enc(validation));print(json.dumps(validation,indent=2))
