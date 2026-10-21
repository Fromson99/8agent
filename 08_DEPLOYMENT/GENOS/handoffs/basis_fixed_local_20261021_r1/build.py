"""Add local review commands over sealed MAIN96 or delivered stable R1."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
NAME='GENOS_BASIS_FIXED_LOCAL_20261021_R1'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
cp=ROOT/'00_SYSTEM/BASIS_COMMANDS.json'
contract=json.loads(cp.read_text())
contract['files']={n:sha((ROOT/n).read_bytes()) for n in contract['files']}
cp.write_text(json.dumps(contract,ensure_ascii=False,indent=2)+'\n')
names=['00_SYSTEM/BASIS_COMMANDS.json',*contract['files']]
old=HERE.parent/'stable_commands_20261021_r1'
base=HERE.parent/'main95_comparison_scope_20261020_r1/code.zip'
main96=HERE.parent/'main96_ad_disabled_20261021_r1'
previous=json.loads((old/'PACKAGE.json').read_text())
newbase=json.loads((main96/'PACKAGE.json').read_text())
allowed,payload={},{}
with zipfile.ZipFile(base) as z:
    for n in names:
        raw=(ROOT/n).read_bytes()
        if n.endswith('.py'): ast.parse(raw,filename=n,feature_version=(3,11))
        target=HERE/'payload'/n
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(raw)
        payload[n]=sha(raw)
        fingerprint=(newbase['payload']['payload/'+n] if n in newbase['patch'] else sha(z.read(n)) if n in z.namelist() else None)
        allowed[n]=list(dict.fromkeys([fingerprint,previous['payload'].get(n)]))
package={'schema_version':'genos-stable-commands-patch-v1','revision':NAME,
         'payload':payload,'allowed_before':allowed,
         'base_code_zip_sha256':sha(base.read_bytes()),
         'main96_package_sha256':sha((main96/'PACKAGE.json').read_bytes()),
         'runtime_data_modified':False,'main_changed':False,'field_verified':False}
(HERE/'PACKAGE.json').write_text(json.dumps(package,ensure_ascii=False,indent=2)+'\n')
subprocess.run(['bash','-n',str(HERE/'GENOS_BASIS_FIXED_LOCAL_RUN.txt')],check=True)
ast.parse((HERE/'installer.py').read_bytes(),feature_version=(3,11))
files=['installer.py','GENOS_BASIS_FIXED_LOCAL_RUN.txt','PACKAGE.json','PATCH_NOTE.txt',*['payload/'+n for n in names]]
archive=HERE/(NAME+'.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for n in files:
        assert Path(n).suffix.lower() not in ('.js','.jsx','.mjs','.cjs')
        z.write(HERE/n,n)
with zipfile.ZipFile(archive) as z:
    assert not z.testzip()
    assert z.read('GENOS_BASIS_FIXED_LOCAL_RUN.txt')==(HERE/'GENOS_BASIS_FIXED_LOCAL_RUN.txt').read_bytes()
(HERE/'SHA256SUMS.txt').write_text('\n'.join(sha((HERE/n).read_bytes())+'  '+n for n in [NAME+'.zip','GENOS_BASIS_FIXED_LOCAL_RUN.txt','PATCH_NOTE.txt'])+'\n')
print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive.read_bytes())}))
