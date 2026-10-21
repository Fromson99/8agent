import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
AUDIT=ROOT/'09_ARTIFACTS/AUDITS/20261020-risk-basis-staging-r3'
COMMON=HERE/'common'; COMMON.mkdir(exist_ok=True)
BASE=json.loads((HERE.with_name('basis_batch_20261020_r3')/'PACKAGE.json').read_text())['code']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
put=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
common_names=['basis_batch_artifacts.py','basis_batch_report.py','basis_batch_candidates.py','basis_batch.py']
for n in common_names:
    shutil.copyfile(ROOT/'02_BACKEND/lawrag/pipeline'/n,COMMON/n)
shutil.copyfile(HERE.with_name('basis_transfer_report_20261020_r1')/'runner.py',COMMON/'runner.py')
put(COMMON/'CODE_REQUIREMENTS.json',{'schema_version':'basis-artifacts-code-v1','baseline':'GENOS_BASIS_BATCH_20261020_R3','checkout':BASE,'tool':{n:sha(COMMON/n) for n in common_names+['runner.py']}})
for n in ('risk_basis_seed.py','risk_basis_staging.py','risk_basis_seed_cli.py'):
    shutil.copyfile(ROOT/'02_BACKEND/lawrag/pipeline'/n,HERE/n)
for p in [*COMMON.glob('*.py'),HERE/'runner.py',*HERE.glob('risk_basis_*.py')]:
    ast.parse(p.read_text(),filename=str(p),feature_version=(3,11))
run='GENOS_RISK_BASIS_REVIEW_20261020_R3_RUN.txt'
subprocess.run(['bash','-n',str(HERE/run)],check=True)
if (AUDIT/'VALIDATION.json').exists():shutil.copy2(AUDIT/'VALIDATION.json',HERE/'VALIDATION.json')
names=['runner.py','risk_basis_seed.py','risk_basis_staging.py','risk_basis_seed_cli.py',run,'읽어주세요.txt']+['common/'+n for n in common_names+['runner.py','CODE_REQUIREMENTS.json']]
if (HERE/'VALIDATION.json').exists():names.append('VALIDATION.json')
files={n:sha(HERE/n) for n in names}
put(HERE/'CODE_MANIFEST.json',{'schema':'risk-basis-json-review-v3','checkout':BASE,'files':files,'direct_sqlite_write':False,'main_changed':False,'genos_verified':False})
archive=HERE/'GENOS_RISK_BASIS_REVIEW_20261020_R3.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for name in names+['CODE_MANIFEST.json']:
        assert Path(name).suffix.lower() not in ('.js','.jsx','.mjs','.cjs')
        z.write(HERE/name,name)
put(HERE/'SHA256.json',{'archive':archive.name,'sha256':sha(archive),'code_manifest_sha256':sha(HERE/'CODE_MANIFEST.json')})
print(json.dumps({'zip':str(archive),'sha256':sha(archive),'bytes':archive.stat().st_size,'files':len(names)+1}))
