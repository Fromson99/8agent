from pathlib import Path
import ast
import hashlib
import json
import zipfile

HERE=Path(__file__).resolve().parent
PACKAGE=HERE/'package'
VERSION='g19-index-join-temp-check-20261103-r1'
files={}
for path in sorted(PACKAGE.glob('*.py')):
    raw=path.read_bytes();ast.parse(raw,feature_version=(3,9))
    files[path.name]=hashlib.sha256(raw).hexdigest()
(PACKAGE/'MANIFEST.json').write_text(json.dumps({'version':VERSION,'files':files},indent=2)+'\n')
name='G19_INDEX_JOIN_TEMP_CHECK_20261103_R1.zip'
with zipfile.ZipFile(HERE/name,'w',zipfile.ZIP_DEFLATED) as archive:
    for member in [*files,'MANIFEST.json']:
        info=zipfile.ZipInfo(member,date_time=(2026,11,3,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
        archive.writestr(info,(PACKAGE/member).read_bytes())
with zipfile.ZipFile(HERE/name) as archive:
    assert archive.testzip() is None
    assert set(archive.namelist())==set(files)|{'MANIFEST.json'}
    assert all(Path(n).suffix in ('.py','.json') for n in archive.namelist())
sha=hashlib.sha256((HERE/name).read_bytes()).hexdigest()
text=(HERE/'launch_template.py').read_text().replace('__ZIP_NAME__',name).replace('__ZIP_SHA256__',sha).replace('__ZIP_PREFIX__',sha[:16])
ast.parse(text,feature_version=(3,9))
(HERE/'01_RUN_INDEX_JOIN_TEMP_CHECK_R1.txt').write_text(text,encoding='utf-8')
attachments=[]
for filename in (name,'01_RUN_INDEX_JOIN_TEMP_CHECK_R1.txt','GUIDE.txt'):
    path=HERE/filename
    attachments.append({'name':filename,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(HERE/'ATTACHMENT_MANIFEST.json').write_text(json.dumps({'version':VERSION,'files':attachments},indent=2)+'\n')
print(json.dumps({'zip':name,'sha256':sha,'members':len(files)+1}))
