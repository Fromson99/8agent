from pathlib import Path
import base64
import hashlib
import json
import subprocess
import zipfile
import zlib

OUT = Path(__file__).resolve().parent
SOURCE = OUT.parent / 'main123_full_20261030_r1' / 'GENOS_MAIN123_FULL_20261030_R1.zip'
NAME = 'GENOS_MAIN123_TRANSFER_20261030_R2'
RUN = NAME + '_RUN.txt'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


source_sha = sha(SOURCE.read_bytes())
assert source_sha == 'f6236b965ee5528e5130a79e277ec9b76e536be43bb8074ecaccceabd3d9f924'
guide = f'''MAIN123 — TRANSFER에서 한 번에 설치

기존 GENOS_MAIN123_FULL_20261030_R1.zip이 있는 TRANSFER에 {RUN}을 올립니다.
현재 TRANSFER 터미널에서 아래 한 줄을 실행합니다.

bash ./{RUN}

압축 준비 → 검사 → 원본 백업 → ~/DEV 적용 → 코드 검증을 자동 수행합니다.
DEV 아래의 TRANSFER도 지원합니다. 폴더 이동과 사전 압축 해제가 필요 없습니다.
성공: APPLIED MAIN123 및 MAIN123_TRANSFER_EXIT=0.
같은 명령 재실행은 기존 백업/상태를 유지합니다. 원래 R1 폴더/실패 로그도 보존합니다.
R2 설치 패키지와 backup/은 현재 TRANSFER/{NAME}/에 남습니다.
로그/종료코드: 현재 TRANSFER/main123-transfer-r2-logs/.
검사 실패 시 적용을 시작하지 않습니다. 적용 중 실패는 백업/상태를 보존하며 성공으로 표시하지 않습니다.

조회: bash ./{RUN} status
검사만: bash ./{RUN} check
필요할 때 원복: bash ./{RUN} rollback
검토 및 commit 후 코드 게이트: bash ./{RUN} gate-code
다른 checkout은 --root 실제_DEV경로를 붙입니다. 첫 검사 뒤 대상을 바꿀 수 없습니다.
파일 검토/commit은 패키지의 COMMIT_PATHS.txt를 기준으로 수행합니다.
Git push/코드서빙 리비전 배포와 워크플로우 편집기 반영은 별도입니다.
현장 질문 검증은 워크플로우 테스트 화면에서 수행합니다.

변경 범위: 설치 경로 검사와 한 번 실행하는 진입점. R1의 제품 코드/워크플로우/JS 보존 조건은 동일합니다.
R1 자체를 수정하지 않으며 R2는 고정 R1 ZIP으로만 준비합니다. 데이터/비밀값은 설치 대상이 아닙니다.
MAIN123의 개발·실험 한계는 동봉 MAIN123_RESULTS.txt에 보존합니다.
로컬 검증은 현장 배포 및 실제 질문 성공을 의미하지 않습니다.
'''
fix = {'source_zip': SOURCE.name, 'source_zip_sha256': source_sha,
       'change': 'Permit a package inside DEV when disjoint from code targets and Git metadata.',
       'product_code_changed': False, 'field_deployment_verified': False}
overrides = {'runner.py': (OUT / 'runner.py').read_text(), 'GUIDE.txt': guide,
             'INSTALLER_FIX.json': encoded(fix).decode()}
with zipfile.ZipFile(SOURCE) as archive:
    spec = json.loads(archive.read('PACKAGE.json'))
    binding = json.loads(archive.read('SOURCE_BINDING.json'))
    source_runner_sha = sha(archive.read('runner.py'))
for name, text in overrides.items():
    spec['payload'][name] = sha(text.encode())
spec['version'] = NAME
spec_raw = encoded(spec)
bootstrap = (OUT / 'bootstrap.py').read_text()
bootstrap = bootstrap.replace('__SOURCE_SHA256__', source_sha).replace('__SPEC_SHA256__', sha(spec_raw))
bootstrap = bootstrap.replace('__OVERRIDES__', base64.b64encode(zlib.compress(encoded(overrides), 9)).decode())
compile(bootstrap, 'embedded_bootstrap.py', 'exec')
shell = '''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
TASK_LOG_DIR="$PWD/main123-transfer-r2-logs"
if [[ -L "$TASK_LOG_DIR" ]]; then echo "Refuse symlink log folder" >&2; exit 2; fi
mkdir -p "$TASK_LOG_DIR"
TASK_LOG="$TASK_LOG_DIR/$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$TASK_LOG") 2>&1
trap 'TASK_RC=$?; printf "%s\\n" "$TASK_RC" > "$TASK_LOG.exit"; echo "MAIN123_TRANSFER_EXIT=$TASK_RC LOG=$TASK_LOG"' EXIT
python3 -u - "$@" <<'MAIN123_TRANSFER_PY'
'''
(OUT / RUN).write_text(shell + bootstrap + '\nMAIN123_TRANSFER_PY\n')
subprocess.run(['bash', '-n', str(OUT / RUN)], check=True)
(OUT / 'GUIDE.txt').write_text(guide)
(OUT / 'EXPECTED_PACKAGE.json').write_bytes(spec_raw)
(OUT / 'HANDOFF.json').write_bytes(encoded({
    'run_file': RUN, 'run_sha256': sha((OUT / RUN).read_bytes()),
    'run_bytes': (OUT / RUN).stat().st_size, 'source_zip_sha256': source_sha,
    'derived_package_sha256': sha(spec_raw), 'source_runner_sha256': source_runner_sha,
    'runner_sha256': sha(overrides['runner.py'].encode()), 'code_files': len(spec['code']),
    'selected_binding': binding, 'product_code_changed': False,
    'field_deployment_verified': False, 'email_sent': False}))
print(json.dumps({'run_file': RUN, 'bytes': (OUT / RUN).stat().st_size,
                  'product_code_changed': False}))
