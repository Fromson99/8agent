from pathlib import Path
import ast,hashlib,io,json,subprocess,zipfile
H=Path(__file__).resolve().parent;R=H.parents[3];NAME='GENOS_WORKFLOW_PROGRESS_20261019_R1'
sha=lambda b:hashlib.sha256(b).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
assert not (H/'SEALED.json').exists()
with zipfile.ZipFile(H/'code.zip') as z:
    (H/(NAME+'_WORKFLOW_PASTE_ALL.txt')).write_bytes(z.read('08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'))
files=['code.zip','CODE_MANIFEST.json','PACKAGE_SPEC.json','SOURCE_POINTER.json','SOURCE_BINDING.json','replace.py','run.py','code_smoke.py',
 NAME+'_RUN.txt',NAME+'_WORKFLOW_PASTE_ALL.txt','ORACLE_QUERY_DDL.sql','ORACLE_QUERY_IMPLEMENTATION_UTF8.txt','GUIDE_UTF8.txt']
if (H/'VALIDATION.json').exists():files.append('VALIDATION.json')
files+=['wheels/'+p.name for p in (H/'wheels').glob('*.whl')]
for f in files:
    raw=(H/f).read_bytes()
    if f.endswith('.py'):ast.parse(raw,filename=f,feature_version=(3,11))
subprocess.run(['bash','-n',str(H/(NAME+'_RUN.txt'))],check=True)
manifest={f:sha((H/f).read_bytes()) for f in files};(H/'PACKAGE_CONTENTS.json').write_bytes(enc(manifest));files.append('PACKAGE_CONTENTS.json')
with zipfile.ZipFile(H/(NAME+'.zip'),'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for f in sorted(files):
        i=zipfile.ZipInfo(f,(2026,10,19,0,0,0));i.compress_type=zipfile.ZIP_DEFLATED;i.external_attr=0o100644<<16;z.writestr(i,(H/f).read_bytes())
def scan(raw,label):
    count=0
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for i in z.infolist():
            assert Path(i.filename).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'},(label,i.filename)
            if i.filename.lower().endswith(('.zip','.whl')):count+=scan(z.read(i.filename),label+'!'+i.filename)
            count+=1
    return count
raw=(H/(NAME+'.zip')).read_bytes();count=scan(raw,NAME)
(H/'ARCHIVE_SCAN.json').write_bytes(enc({'status':'PASS','members_recursive':count,'javascript_files':0,'outer_sha256':sha(raw),'bytes':len(raw)}))
print(json.dumps({'zip_bytes':len(raw),'members_recursive':count,'sha256':sha(raw)}))
