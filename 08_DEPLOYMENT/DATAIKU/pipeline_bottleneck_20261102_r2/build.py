from pathlib import Path
import ast
import hashlib
import json
import zipfile

HERE=Path(__file__).resolve().parent
PACKAGE=HERE/'package'
files={}
for path in sorted(PACKAGE.glob('*.py')):
    raw=path.read_bytes(); ast.parse(raw,feature_version=(3,10))
    files[path.name]=hashlib.sha256(raw).hexdigest()
(PACKAGE/'MANIFEST.json').write_text(json.dumps({'version':'g19-bottleneck-observer-20261102-r2','files':files},indent=2)+'\n')
name='G19_BOTTLENECK_DIAGNOSTIC_20261102_R2.zip'
with zipfile.ZipFile(HERE/name,'w',zipfile.ZIP_DEFLATED) as z:
    for n in [*files,'MANIFEST.json']:
        info=zipfile.ZipInfo(n,date_time=(2026,11,2,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
        z.writestr(info,(PACKAGE/n).read_bytes())
with zipfile.ZipFile(HERE/name) as z:
    assert all(Path(n).suffix.lower() in ('.py','.json') for n in z.namelist())
sha=hashlib.sha256((HERE/name).read_bytes()).hexdigest()
base=(HERE/'launch_template.py').read_text().replace('__ZIP_NAME__',name).replace('__ZIP_SHA256__',sha).replace('__ZIP_PREFIX__',sha[:16])
for filename,settings,call in (
    ('01_DIAG_AND_ROLLBACK_INSERT_RUN_R2.txt','RUN_INSERT_PROBES = True  # 작은 INSERT/내용검증/ROLLBACK 시험. 실제 정상 적재를 재개하지 않습니다.',
     '_g19_result = _g19_observer.snapshot(OLD_JOB_DIR, STATE_DIR, PACKAGE_DIR, insert_probes=RUN_INSERT_PROBES, hints=_G19_CONTEXT_HINTS)'),
    ('02_PROFILE_EXISTING_STAGE_RUN_R2.txt',"PROFILE_STAGE = ''  # 빈 값이면 실행 안 함. 실제 재개할 단계: load / verify_publish / vector 중 하나.",
     '_g19_result = _g19_observer.profile(PROFILE_STAGE, OLD_JOB_DIR, STATE_DIR, PACKAGE_DIR, hints=_G19_CONTEXT_HINTS)')):
    text=base.replace('__MODE_SETTINGS__',settings).replace('__RUN_CALL__',call)
    ast.parse(text,feature_version=(3,10));(HERE/filename).write_text(text)
print(json.dumps({'zip':name,'sha256':sha,'members':len(files)+1}))
