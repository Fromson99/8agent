from pathlib import Path
import ast
import hashlib
import json
import shutil
import subprocess
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
AUDIT=ROOT/'09_ARTIFACTS/AUDITS/20261020-basis-batch'
NAME='GENOS_BASIS_BATCH_20261020_R1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (HERE/'EMAIL_SENT.json').exists()
binding=json.loads((AUDIT/'VALIDATION_BINDING.json').read_text())
stage=Path(binding['code_root'])
base=json.loads((ROOT/'08_DEPLOYMENT/RELEASES/genos-model-metadata-20261020-r1/release.json').read_text())
before=json.loads((AUDIT/'BEFORE.json').read_text())['files']
code=binding['files']
patch=binding['delivery_files']
prior_zip=ROOT/'08_DEPLOYMENT/GENOS/handoffs/main92_cumulative_20261020_r1/code.zip'
allowed={}
with zipfile.ZipFile(prior_zip) as z:
    names=set(z.namelist())
    for name,expected in code.items():
        allowed[name]=list(dict.fromkeys([expected,base['files'].get(name),
            hashlib.sha256(z.read(name)).hexdigest() if name in names else None,
            before.get(name,expected)])) if name in patch else [expected]
        if name not in patch and name in names:
            assert hashlib.sha256(z.read(name)).hexdigest()==expected,('unchanged baseline mismatch',name)
for name in patch:
    p=stage/name
    assert sha(p)==code[name]
    dest=HERE/'payload'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
shutil.copyfile(stage/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py',HERE/(NAME+'_WORKFLOW_PASTE_ALL.txt'))
files=['runner.py',NAME+'_RUN.txt',NAME+'_WORKFLOW_PASTE_ALL.txt','GUIDE_UTF8.txt']
if (HERE/'VALIDATION.json').exists():files.append('VALIDATION.json')
files += ['payload/'+name for name in patch]
for name in files:
    if name.endswith('.py'):ast.parse((HERE/name).read_bytes(),filename=name,feature_version=(3,11))
subprocess.run(['bash','-n',str(HERE/(NAME+'_RUN.txt'))],check=True)
spec={'version':NAME,'code':code,'patch':patch,'allowed_before':allowed,
      'payload':{n:sha(HERE/n) for n in files},
      'source_release':base['release_id'],'local_MAIN_changed':False,
      'field_GENOS_verified':False}
put(HERE/'PACKAGE.json',spec)
files.append('PACKAGE.json')
with zipfile.ZipFile(HERE/(NAME+'.zip'),'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for name in sorted(files):
        assert Path(name).suffix.lower() not in ('.js','.jsx','.mjs','.cjs')
        info=zipfile.ZipInfo(name,(2026,10,20,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
        info.external_attr=0o100644<<16
        z.writestr(info,(HERE/name).read_bytes())
put(HERE/'BUILD.json',{'zip_sha256':sha(HERE/(NAME+'.zip')),
     'bytes':(HERE/(NAME+'.zip')).stat().st_size,'patch_files':len(patch),
     'bound_code_files':len(code),'javascript_files':0})
print(json.dumps(json.loads((HERE/'BUILD.json').read_text())))
