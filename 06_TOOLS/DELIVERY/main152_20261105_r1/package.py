from common import *
import zipfile,shutil,subprocess,ast,importlib.util
from datetime import datetime,timezone
H=ROOT/'08_DEPLOYMENT/GENOS/handoffs/main152_oneclick_mail_20261105_r1';H.mkdir(exist_ok=True)
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');r=read(ROOT/active['manifest_path']);C=ROOT/r['code_root'];assert active['generation']==152
assert read(SOURCE_ART/'main/activation.json')['active']==active
excluded={n:h for n,h in r['files'].items() if Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'}}
files={n:(C/n).read_bytes() for n,h in r['files'].items() if n not in excluded}
for n,h in r['files'].items():assert sha(C/n)==h
for name in ('genos_codespace_engine_preflight.py','genos_generation_e2e.py','genos_release_gate.py'):
 n='06_TOOLS/COMMANDS/'+name;assert n not in files;files[n]=(ROOT/n).read_bytes()
# Include the existing asset verifier and its local import dependencies, using
# unchanged repository bytes. These tools supplement the frozen serving tree.
queue=['lawrag.pipeline.term_serving_bundle','lawrag.pipeline.glossary_serving'];visited=set()
while queue:
 module=queue.pop()
 if module in visited:continue
 visited.add(module)
 relative='02_BACKEND/'+module.replace('.','/')+'.py';p=ROOT/relative
 if not p.is_file():
  relative='02_BACKEND/'+module.replace('.','/')+'/__init__.py';p=ROOT/relative
 if not p.is_file():continue
 if relative not in files:files[relative]=p.read_bytes()
 # Existing serving imports were already frozen and are not expanded anew.
 if relative in r['files']:continue
 tree=ast.parse(p.read_text());package=module if p.name=='__init__.py' else module.rsplit('.',1)[0]
 def imports(nodes):
  for node in nodes:
   if isinstance(node,ast.Import):
    for alias in node.names:yield alias.name
   elif isinstance(node,ast.ImportFrom):
    base=importlib.util.resolve_name('.'*node.level+(node.module or ''),package) if node.level else node.module or ''
    yield base
    for alias in node.names:yield base+'.'+alias.name
   elif isinstance(node,(ast.If,ast.Try,ast.With)):
    yield from imports(node.body);yield from imports(getattr(node,'orelse',[]))
    for handler in getattr(node,'handlers',[]):yield from imports(handler.body)
 for target in imports(tree.body):
  if target.startswith(('lawrag.','semantic_runtime.')):queue.append(target)
# A helper newly introduced into the delivery had one legacy trailing space.
# Normalize only that helper in the package; preserve its AST and MAIN bytes.
n='02_BACKEND/lawrag/pipeline/glossary_v1.py';original=files[n]
clean=('\n'.join(line.rstrip(' \t') for line in original.decode().split('\n'))).encode()
assert ast.dump(ast.parse(clean))==ast.dump(ast.parse(original))
files[n]=clean
helper_normalization={'path':n,'source_sha256':hashlib.sha256(original).hexdigest(),'package_sha256':hashlib.sha256(clean).hexdigest(),'ast_unchanged':True,'reason':'Existing trailing space on newly packaged verification dependency; main serving code untouched'}
manifest={'format':'8agent-code/1','created_at':datetime.now(timezone.utc).isoformat(),
 'release_id':r['release_id'],'local_main':152,'release_manifest_sha256':sha(ROOT/active['manifest_path']),
 'files':[{'path':n,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)} for n,raw in sorted(files.items())],
 'required_files':[{'path':n,'sha256':h,'reason':'Existing JavaScript dependency, excluded from email attachments by user preference'} for n,h in excluded.items()],
 'quality_certified':False,'field_deployed':False,'data_included':False,'helper_normalization':helper_normalization}
Z=H/'MAIN152_FULL_20261105_R1.zip'
with zipfile.ZipFile(Z,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for n,raw in sorted(files.items()):z.writestr(n,raw)
 z.writestr('CODE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
with zipfile.ZipFile(Z) as z:
 assert len(z.namelist())==len(set(z.namelist()))==len(files)+1
 assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs','.zip','.gz','.tgz','.tar','.7z'} for n in z.namelist())
old=ROOT/'08_DEPLOYMENT/GENOS/handoffs/main151_oneclick_mail_20261105_r1/MAIN151_ONECLICK_R1.txt'
s=old.read_text().replace('MAIN151','MAIN152').replace('main151','main152').replace('53f3ec06ae583364c06614efca7b60e3fb0f57cd99f2d13dd70afe45bdf9104b',sha(Z))
(H/'MAIN152_ONECLICK_R1.txt').write_text(s)
shutil.copyfile(C/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py',H/'MAIN152_WORKFLOW.py')
subprocess.run(['bash','-n',str(H/'MAIN152_ONECLICK_R1.txt')],check=True)
put(H/'CODE_MANIFEST.json',manifest)
put(ART/'mail-package.json',{'handoff':str(H.relative_to(ROOT)),'zip_sha256':sha(Z),'code_files':len(files),'members':len(files)+1,'excluded_required':excluded,'release':active,'full_serving_match':True,'workflow_sha256':sha(H/'MAIN152_WORKFLOW.py'),'extras':list(n for n in files if n not in r['files'])})
print('Built',Z.name,'code',len(files),'JS attachments0; workflow exact')
