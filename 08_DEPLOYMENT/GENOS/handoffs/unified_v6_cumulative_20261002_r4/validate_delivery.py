from pathlib import Path
import ast,hashlib,json,os,re,subprocess,tempfile,zipfile
root=Path.cwd();out=Path(__file__).resolve().parent
archive=out/'GENOS_UNIFIED_V6_CUMULATIVE_20261002_R4.zip'
script=out/'GENOS_UNIFIED_V6_CUMULATIVE_20261002_R4.txt'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
with zipfile.ZipFile(archive) as z:
 raw=z.read('CODE_MANIFEST.json');manifest=json.loads(raw)
 assert not any(Path(n).suffix.lower() in ('.js','.jsx','.mjs','.cjs') for n in z.namelist())
 current=frozen=0
 for row in manifest['files']:
  name=row['path'];payload=z.read(name)
  assert hashlib.sha256(payload).hexdigest()==row['sha256'] and len(payload)==row['bytes']
  assert payload==(root/name).read_bytes(),name
  if name.endswith('.py'):
   if name.startswith(('02_BACKEND/GENERATIONS/','06_TOOLS/GENERATIONS/','02_BACKEND/lawrag/research/candidates/')):frozen+=1
   else:compile(payload,name,'exec');ast.parse(payload,filename=name,feature_version=(3,11));current+=1
 (out/'CODE_MANIFEST.json').write_bytes(raw)
 oldarchive=root/'08_DEPLOYMENT/GENOS/handoffs/unified_v6_nfs_main_20261002_r2/code.zip'
 with zipfile.ZipFile(oldarchive) as old:oldrows={r['path']:r for r in json.loads(old.read('CODE_MANIFEST.json'))['files']}
 changes=[{'path':r['path'],'before_sha256':oldrows.get(r['path'],{}).get('sha256'),'after_sha256':r['sha256'],'kind':'ADDED' if r['path'] not in oldrows else 'CHANGED'} for r in manifest['files'] if r['path'] not in oldrows or oldrows[r['path']]['sha256']!=r['sha256']]
 (out/'CHANGES_SINCE_R2.json').write_text(json.dumps({'baseline_sha256':sha(oldarchive),'new_zip_sha256':sha(archive),'changes':changes},ensure_ascii=False,indent=2)+'\n')
 txt=script.read_text();code=txt.split("<<'GENOS_V6_PY'\n",1)[1].split('\nGENOS_V6_PY\n',1)[0];compile(code,'field-script','exec');ast.parse(code,feature_version=(3,11))
 subprocess.run(['bash','-n',str(script)],check=True)
 with tempfile.TemporaryDirectory(prefix='v6-r4-delivery-',dir='/var/tmp') as temporary:
  task=Path(temporary);dev=task/'DEV';dev.mkdir()
  with zipfile.ZipFile(oldarchive) as old:old.extractall(dev)
  for name in ('service/__init__.py','service/service.py'):
   p=dev/name;p.parent.mkdir(exist_ok=True);p.write_bytes((root/name).read_bytes())
  (dev/'.env').write_text('MOCK_SECRET_VALUE=preserved\n');(dev/'90_RUNTIME').mkdir();(dev/'90_RUNTIME/case-memory-marker').write_text('preserved')
  union=[r['path'] for r in manifest['files']]+['CODE_MANIFEST.json','.env','90_RUNTIME/case-memory-marker']
  before={name:sha(dev/name) if (dev/name).is_file() else None for name in union}
  shim=task/'bin';shim.mkdir();(shim/'python3').symlink_to(root/'.venv/bin/python')
  env={**os.environ,'MAIN_DEV_ROOT':str(dev),'GENOS_HANDOFF_LOG_DIR':str(task/'logs'),'PATH':str(shim)+':'+os.environ['PATH']}
  def run(*args):
   result=subprocess.run(['bash',str(script),*args],env=env,capture_output=True,text=True)
   with (out/'installer-validation.log').open('a') as log:log.write(result.stdout+result.stderr)
   assert result.returncode==0,result.stdout[-2000:]+result.stderr[-2000:]
   return result.stdout
  run('check');applied=run('apply');run('verify');rerun=run('apply');assert 'ALREADY INSTALLED' in rerun
  assert sha(dev/'.env')==before['.env'] and sha(dev/'90_RUNTIME/case-memory-marker')==before['90_RUNTIME/case-memory-marker']
  subprocess.run(['git','init','-q',str(dev)],check=True)
  pathlist=task/'git-paths';pathlist.write_bytes(b'\0'.join(r['path'].encode() for r in manifest['files'])+b'\0')
  subprocess.run(['git','-C',str(dev),'add','--force','--pathspec-from-file='+str(pathlist),'--pathspec-file-nul'],check=True)
  subprocess.run(['git','-C',str(dev),'-c','user.name=Mock Validator','-c','user.email=mock@example.invalid','commit','-q','-m','Mock cumulative v6 R4'],check=True)
  gate=subprocess.run([str(root/'.venv/bin/python'),str(dev/'06_TOOLS/COMMANDS/genos_release_gate.py'),'--code-zip',str(archive),'--deploy-root',str(dev),'--code-only'],capture_output=True,text=True)
  assert gate.returncode==0,gate.stdout+gate.stderr
  with (out/'installer-validation.log').open('a') as log:log.write(gate.stdout+gate.stderr)
  backup=re.search(r'BACKUP/RECOVERY: (.+)',applied).group(1)
  run('rollback',backup);run('rollback',backup)
  after={name:sha(dev/name) if (dev/name).is_file() else None for name in union}
  assert before==after,'rollback bytes mismatch'
  # Mutation must be refused before any apply; no source archive is changed.
  bad=task/'bad';bad.mkdir();(bad/script.name).write_bytes(script.read_bytes());(bad/archive.name).write_bytes(b'not a valid package')
  rejected=subprocess.run(['bash',str(bad/script.name),'apply'],env=env,capture_output=True,text=True)
  assert rejected.returncode!=0 and 'SHA256 mismatch' in rejected.stdout+rejected.stderr
result={'code_files':len(manifest['files']),'syntax_current_checked':current,'frozen_python_preserved_not_certified':frozen,'javascript_members':0,'code_zip_sha256':sha(archive),'code_manifest_sha256':sha(out/'CODE_MANIFEST.json'),'installer_cases':['check','apply from R2 plus installed R3 adapter','verify all bytes','idempotent reapply','environment/runtime preservation','committed mock checkout code-only gate','rollback exact bytes','idempotent rollback','reject tampered archive'],'genos_deployment':'NOT_VERIFIED','onsite_generation':None,'onsite_code_serving_revision':None,'local_active_pointer_changed':False}
(out/'INSTALLER_VALIDATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
