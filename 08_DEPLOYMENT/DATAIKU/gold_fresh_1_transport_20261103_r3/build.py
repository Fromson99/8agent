from pathlib import Path
import csv,hashlib,json,sys,zipfile
HERE=Path(__file__).resolve().parent
PACKAGE=HERE/'package'
sys.path.insert(0,str(PACKAGE))
from gold_io import Contract
contract=Contract(PACKAGE/'contract.json')
files={}
for p in sorted(PACKAGE.rglob('*')):
    if not p.is_file() or '__pycache__' in p.parts or p.name=='CODE_MANIFEST.json':continue
    assert p.suffix.lower() not in {'.zip','.pyc','.js','.jsx','.mjs','.cjs'}
    if p.suffix=='.py':compile(p.read_bytes(),str(p),'exec')
    files[p.relative_to(PACKAGE).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
(PACKAGE/'CODE_MANIFEST.json').write_text(json.dumps({'version':'gold-fresh-1-transport-code-r3','files':files},indent=2)+'\n')
name='DATAIKU_GOLD_FRESH_1_TRANSPORT_20261103_R3.zip'
with zipfile.ZipFile(HERE/name,'w',zipfile.ZIP_DEFLATED) as z:
    for n in [*files,'CODE_MANIFEST.json']:
        info=zipfile.ZipInfo(n,date_time=(2026,11,3,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
        z.writestr(info,(PACKAGE/n).read_bytes())
checksum=hashlib.sha256((HERE/name).read_bytes()).hexdigest()
text=(HERE/'launch_template.py').read_text().replace('__ZIP_NAME__',name).replace('__ZIP_SHA256__',checksum)
compile(text,'DATAIKU_GOLD_FRESH_1_RUN_R3.txt','exec')
(HERE/'DATAIKU_GOLD_FRESH_1_RUN_R3.txt').write_text(text)
print(json.dumps({'zip':name,'sha256':checksum,'tables':len(contract.tables),'contract_sha256':contract.sha256}))
