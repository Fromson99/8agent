"""Generate deploy instructions and the complete mail bundle from tested bytes."""
import hashlib
import io
import json
from pathlib import Path
import zipfile
from build import writezip
HERE=Path(__file__).parent
manifest=json.loads((HERE/'BUILD.json').read_text())
name='GENOS_DATAIKU_COMPUTE_20261027_R1.zip';archive_sha=manifest['files'][name]['sha256'];code_sha=manifest['code_sha256']
old=HERE.parent/'pipeline_service_20261022_r3/install_here_20261022_r1/install_here.py'
installer=old.read_text().replace('GENOS_PIPELINE_SERVICE_20261022_R2.zip',name).replace('a1650207b077571446df2c2942403f4e9c0bfc5781d509db8658d66f2a81b926',archive_sha).replace('771afb12a8fcf8c71417151cc80c8f4a9141e23d621ae27ec58cba67a7a22c46',code_sha).replace("STATE_DIR = '.pipeline-install-r2'","STATE_DIR = '.dataiku-compute-install-r1'")
installer=installer.replace("    audit = checked(root, STATE_DIR)","    if current(checked(root,'CODE_PINS.json')) not in ('771afb12a8fcf8c71417151cc80c8f4a9141e23d621ae27ec58cba67a7a22c46', CODE_SHA):\n        raise ValueError('PIPELINE_R2_CHECKOUT_REQUIRED: RAG 앱 checkout에 적용하지 마세요')\n    audit = checked(root, STATE_DIR)")
installer=installer.replace('새 파이프라인 전용 DEV 루트','기존 legal_pipeline_serving Git checkout ~/DEV 루트').replace('기존 서비스 R2 ZIP을 같은 DEV에 두세요.','이번 compute ZIP을 같은 DEV에 두세요.')
installer=installer.replace("    audit.mkdir(exist_ok=True)", "    audit.mkdir(exist_ok=True)\n    if action == 'apply' and not (audit/'plan.json').exists():\n        before_pins=json.loads((root/'CODE_PINS.json').read_text())\n        for before_name,before_hash in before_pins['files'].items():\n            if current(checked(root,before_name))!=before_hash:\n                raise ValueError('EXISTING_CHECKOUT_EDIT: '+before_name)")
(HERE/'install_compute.py').write_text(installer)
script='''# GENOS legal_pipeline_serving 기존 Git checkout ~/DEV에 적용합니다.
# RAG 채팅 코드서빙 checkout이 아닙니다. 배포 코드 적용이며 원격 job/로그 조회 없음.
# 압축 해제한 전달 폴더(아래 ZIP이 있는 폴더)에서 이 TXT 전체를 터미널에 붙여넣습니다.
set -e
python3 - <<'PY_COPY'
from pathlib import Path
import hashlib, shutil
name=ARCHIVE_LITERAL
source=Path.cwd()/name
if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=ARCHIVE_HASH:
    raise SystemExit('이번 ZIP이 있는 디렉터리에서 실행하세요. ZIP hash 불일치/미발견')
destination=Path.home()/'DEV'/name
if not (destination.parent/'.git').exists():raise SystemExit('기존 ~/DEV Git checkout이 없습니다')
if source.resolve()!=destination.resolve():
    if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest()!=ARCHIVE_HASH:
        raise SystemExit('기존 동명 ZIP 충돌')
    shutil.copyfile(source,destination)
PY_COPY
cd "$HOME/DEV"
python3 - <<'PY_INSTALL'
INSTALLER_SOURCE
run('apply')
PY_INSTALL
python3 - <<'PY_STAGE'
INSTALLER_SOURCE
run('stage')
PY_STAGE
git diff --cached --stat
git commit -m "Move pipeline lifecycle to Dataiku; cancellable ephemeral compute"
python3 VERIFY_PIPELINE_RELEASE.py --code-root "$HOME/DEV" --require-committed
git push
# 여기까지는 Git 적용/전송입니다. GENOS 화면에서 위 commit으로 새 리비전을 배포합니다.
# legal_pipeline_serving(761), 프로세스 worker 1 / replica 1. Python service(config,data) 진입점 유지.
# 별도 S3 설정/자격/방화벽은 필요 없습니다. Dataiku URL/TOKEN 기존 변수 유지.
# 배포 뒤 Dataiku 00의 CONNECTED_COMPUTE_CODE_MATCH가 이 리비전 연결 확인입니다.
# 성공 뒤 02 → 03. 기존 01 원문이 완료되어 있으면 재실행하지 않습니다.
'''.replace('ARCHIVE_LITERAL',repr(name)).replace('ARCHIVE_HASH',repr(archive_sha))
embedded=installer[:installer.index("if __name__ == '__main__':")]
script=script.replace('INSTALLER_SOURCE',embedded)
(HERE/'GENOS_COMPUTE_INSTALL_20261027_R1.txt').write_text(script)
# Recoverable rollback uses the exact same embedded installer, on the actual checkout.
rollback='''# 위 설치가 적용된 legal_pipeline_serving ~/DEV. Dataiku 배치가 중지된 상태에서만 사용.
set -e
cd "$HOME/DEV"
python3 - <<'PY_ROLLBACK'
'''+embedded+"\nrun('rollback')\nPY_ROLLBACK\n# 복원 파일을 검토·commit/push한 후 이전 리비전으로 배포합니다. Dataiku 설치 TXT의 ACTION='rollback'도 실행합니다.\n"
(HERE/'ROLLBACK_GENOS.txt').write_text(rollback)
files=[name,'DATAIKU_COMPUTE_RECIPES_20261027_R1.zip','DATAIKU_COMPUTE_INSTALL_20261027_R1.txt',
       'DATAIKU_COMPUTE_CONTROL_20261027_R1.txt','GENOS_COMPUTE_INSTALL_20261027_R1.txt',
       'ROLLBACK_GENOS.txt','GUIDE.txt','WORK_CONTRACT.txt','install_compute.py','VALIDATION.json']
values={n:(HERE/n).read_bytes() for n in files}

def inspect(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():
            if Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'}:raise ValueError('MAIL_FORBIDDEN_EXTENSION '+n)
            if n.lower().endswith('.zip'):inspect(z.read(n))
writezip(HERE/'DATAIKU_OWNED_COMPUTE_20261027_R1.zip',values)
inspect((HERE/'DATAIKU_OWNED_COMPUTE_20261027_R1.zip').read_bytes())
manifest['files'].update({n:{'sha256':hashlib.sha256((HERE/n).read_bytes()).hexdigest(),'bytes':(HERE/n).stat().st_size} for n in
    files+['DATAIKU_OWNED_COMPUTE_20261027_R1.zip']})
(HERE/'DELIVERY_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('DELIVERY_READY',len(files),'files')
