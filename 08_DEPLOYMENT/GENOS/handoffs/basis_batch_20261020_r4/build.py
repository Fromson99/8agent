"""R3 -> reviewed R4 repair, with the existing offline candidate consumer."""
from pathlib import Path
import ast
import hashlib
import json
import shutil
import subprocess
import zipfile

HERE=Path(__file__).parent
ROOT=HERE.parents[3]
AUDIT=ROOT/'09_ARTIFACTS/AUDITS/20261020-basis-discovery-skip'
STAGE=AUDIT/'validation-code'
BASE=HERE.with_name('basis_batch_20261020_r3')
NAME='GENOS_BASIS_BATCH_20261020_R4'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())
put=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (HERE/'SEALED.json').exists(),'Preserve sealed package; create a new revision'
prior=read(BASE/'PACKAGE.json')
binding=read(AUDIT/'VALIDATION_BINDING.json')
code={n:sha(STAGE/n) for n in prior['code']}
assert all(sha(STAGE/n)==binding['files'][n] for n in code)
patch=[n for n,h in code.items() if h!=prior['code'][n]]
for name in patch:
    dst=HERE/'payload'/name;dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(STAGE/name,dst)
tools=HERE/'tools';tools.mkdir(exist_ok=True)
tool_names=['runner.py','basis_batch_artifacts.py','basis_batch_report.py','basis_batch_candidates.py','basis_batch.py']
shutil.copyfile(HERE.with_name('basis_transfer_report_20261020_r1')/'runner.py',tools/'runner.py')
for name in tool_names[1:]:
    shutil.copyfile(STAGE/'02_BACKEND/lawrag/pipeline'/name,tools/name)
put(tools/'CODE_REQUIREMENTS.json',{'schema_version':'basis-artifacts-code-v1','baseline':NAME,
    'checkout':code,'tool':{n:sha(tools/n) for n in tool_names}})
files=['runner.py',NAME+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION.json']
files+=['tools/'+n for n in tool_names+['CODE_REQUIREMENTS.json']]
files+=['payload/'+n for n in patch]
for name in files:
    if name.endswith('.py'):ast.parse((HERE/name).read_text(),feature_version=(3,11))
subprocess.run(['bash','-n',str(HERE/(NAME+'_RUN.txt'))],check=True)
spec={'version':NAME,'supersedes':prior['version'],'prior_package_sha256':sha(BASE/'PACKAGE.json'),
      'code':code,'patch':patch,
      'allowed_before':{n:list(dict.fromkeys([prior['code'][n],h])) for n,h in code.items()},
      'payload':{n:sha(HERE/n) for n in files},
      'correction':'Durable source task binding; classified unit skip; JSON candidates before manual SQLite import'}
put(HERE/'PACKAGE.json',spec);files+=['PACKAGE.json']
with zipfile.ZipFile(HERE/(NAME+'.zip'),'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for name in sorted(files):z.write(HERE/name,name)
put(HERE/'BUILD.json',{'zip_sha256':sha(HERE/(NAME+'.zip')),'patch_files':len(patch),
    'checkout_files':len(code),'bytes':(HERE/(NAME+'.zip')).stat().st_size,
    'automatic_sqlite_publication':False,'base':prior['version'],
    'borrowed_tools':{n:sha(tools/n) for n in tool_names}})
print(json.dumps(read(HERE/'BUILD.json'),ensure_ascii=False))
