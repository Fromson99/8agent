from pathlib import Path
import ast
import hashlib
import json
import zipfile

HERE=Path(__file__).resolve().parent
PACKAGE=HERE/'package'
files={}
for path in sorted([*PACKAGE.glob('*.py'),PACKAGE/'PLAN.json']):
    raw=path.read_bytes()
    if path.suffix=='.py':ast.parse(raw,feature_version=(3,9))
    files[path.name]=hashlib.sha256(raw).hexdigest()
(PACKAGE/'MANIFEST.json').write_text(json.dumps({'version':'g19-response-batch-check-20261103-r1','files':files},indent=2)+'\n')
name='G19_RESPONSE_BATCH_CHECK_20261103_R1.zip'
with zipfile.ZipFile(HERE/name,'w',zipfile.ZIP_DEFLATED) as archive:
    for n in [*files,'MANIFEST.json']:
        info=zipfile.ZipInfo(n,date_time=(2026,11,3,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
        archive.writestr(info,(PACKAGE/n).read_bytes())
with zipfile.ZipFile(HERE/name) as archive:
    assert len(archive.namelist())==len(files)+1
    assert all(Path(n).suffix in ('.py','.json') for n in archive.namelist())
    assert archive.testzip() is None
sha=hashlib.sha256((HERE/name).read_bytes()).hexdigest()
text=(HERE/'launch_template.py').read_text().replace('__ZIP_NAME__',name).replace('__ZIP_SHA256__',sha).replace('__ZIP_PREFIX__',sha[:16])
ast.parse(text,feature_version=(3,9))
(HERE/'01_RUN_RESPONSE_BATCH_CHECK_R1.txt').write_text(text)
print(json.dumps({'zip':name,'sha256':sha,'members':len(files)+1}))
