"""Preserve R10 sources and recognize only the sealed budget R1 overlay."""
import ast
import base64
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
R10 = OUT.with_name('cm_shortcut_oneclick_20261007_r10')
BUDGET = OUT.with_name('investigation_budget_20261007_r1')
NAME = 'GENOS_CM_ONECLICK_20261007_R11'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode()


def main():
    assert not (OUT/(NAME+'_RUN.txt')).exists(), 'Preserve sealed deliveries; use a new revision'
    spec = json.loads(gzip.decompress((R10/'PATCH_SPEC.json.gz').read_bytes()))
    spec['revision'] = NAME
    spec['r10_upgrades'] = {key: key for key in spec['recipes']}
    spec['r10_inventories'] = {key: recipe['after'] for key, recipe in spec['recipes'].items()}
    budget_code = (BUDGET/'install_budget.py').read_bytes()
    expected_budget = json.loads((BUDGET/'HANDOFF.json').read_bytes())['zip_members']['install_budget.py']['sha256']
    assert sha(budget_code) == expected_budget
    spec['investigation_budget_overlay'] = {'library': base64.b64encode(budget_code).decode(),
        'library_sha256': sha(budget_code), 'spec': json.loads((BUDGET/'PATCH_SPEC.json').read_bytes())}
    (OUT/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(encoded(spec), mtime=0))
    code = (ROOT/'06_TOOLS/COMMANDS/genos_cm_oneclick.py').read_bytes()
    ast.parse(code, feature_version=(3, 11))
    bundle = encoded({'code': base64.b64encode(code).decode(), 'spec': spec})
    packed = base64.b64encode(zlib.compress(bundle, 9)).decode()
    script = '''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
task_transfer="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
task_logs="$task_transfer/cm-oneclick-r11/logs"
mkdir -p -- "$task_logs"
task_log="$task_logs/$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$task_log") 2>&1
cm_exit() {
    task_exit=$?
    python3 - "$task_log.EXIT_STATUS.json" "$task_exit" <<'EXIT_PY'
import json,os,sys
path=sys.argv[1];raw=(json.dumps({'exit_code':int(sys.argv[2])})+'\\n').encode()
with open(path+'.tmp','xb') as stream:
    stream.write(raw);stream.flush();os.fsync(stream.fileno())
os.replace(path+'.tmp',path)
EXIT_PY
    printf 'EXIT=%s LOG=%s\\n' "$task_exit" "$task_log"
}
trap cm_exit EXIT
printf 'CM R11 조사 한도 보존·현장 문서 연결 시작 LOG=%s\\n' "$task_log"
python3 - "$task_transfer" "$@" <<'CM_ONECLICK_PY'
'''+f'''import base64,hashlib,json,sys,types,zlib
raw=zlib.decompress(base64.b64decode({packed!r}))
if hashlib.sha256(raw).hexdigest()!={sha(bundle)!r}:raise ValueError('Embedded bundle hash mismatch')
bundle=json.loads(raw);m=types.ModuleType('cm_oneclick')
code=base64.b64decode(bundle['code'])
if hashlib.sha256(code).hexdigest()!={sha(code)!r}:raise ValueError('Embedded installer hash mismatch')
exec(compile(code,'genos_cm_oneclick.py','exec'),m.__dict__)
raise SystemExit(m.main(bundle['spec'],sys.argv[1:]))
CM_ONECLICK_PY
'''
    run = OUT/(NAME+'_RUN.txt');run.write_text(script)
    subprocess.run(['bash', '-n', str(run)], check=True)
    guide_text = '''CM R11 — 조사 한도 패치 적용 후 CM R10 중단 복구

사진의 조사 한도 설정 R1 check/apply/verify는 통과했습니다. CM R10은 그 뒤의
R8 code differs from the verified upgrade inventory 검사에서 코드 적용 전에 중단했습니다.
R11은 검증된 조사 한도 R1 변경과 부모 inventory를 함께 확인해 그 수정을 보존합니다.
알 수 없는 코드 변경이나 세대/해시 차이는 계속 거부합니다.

ZIP을 기존 ~/DEV/TRANSFER에 올린 다음 아래 세 줄을 실행합니다.
unzip 설치는 필요 없습니다. 조사 한도 패치를 원복하거나 다시 적용할 필요도 없습니다.

python3 -m zipfile -e ~/DEV/TRANSFER/GENOS_CM_ONECLICK_20261007_R11.zip ~/DEV/TRANSFER
(cd ~/DEV/TRANSFER && sha256sum -c GENOS_CM_ONECLICK_20261007_R11_SHA256SUMS.txt)
bash ~/DEV/TRANSFER/GENOS_CM_ONECLICK_20261007_R11_RUN.txt

별도 첨부 RUN TXT를 TRANSFER에 올렸다면 마지막 bash 한 줄로 실행할 수도 있습니다.
현재 DEV에 필요한 CM 이름/조문 연결 수정만 이어 적용하고 51건/98근거 확인,
commit, 같은 checkout/generation gate, 공통 등록/검증, 기존 origin push를 수행합니다.
R8/R10 실패 로그와 조사 한도 백업, 원문 generation, 기존 DB 기록은 보존합니다.
사용자/팀 JSON이나 새 환경변수 입력, 원문 재구축은 필요 없습니다.
조사 한도 설정은 기존 값을 유지하며 코드서빙 환경 저장 여부는 별도입니다.

EXIT=0 및 READY_FOR_REVISION_DEPLOYMENT이면 출력한 COMMIT으로 새 코드서빙 리비전을
배포하고 워크플로우 테스트 화면에서 실제 질문을 확인합니다. 코드 적용/공통 등록/
Git push/리비전 배포/워크플로우 성공은 각각 별도 상태입니다.

실행 결과: ~/DEV/TRANSFER/cm-oneclick-r11/STATUS.json
문서 연결: ~/DEV/TRANSFER/cm-oneclick-r11/DATA_CHECKED.json
등록 영수증: ~/DEV/TRANSFER/cm-oneclick-r11/CM51_REGISTERED.json
로그와 종료 상태: ~/DEV/TRANSFER/cm-oneclick-r11/logs/<실행>.log 및 .EXIT_STATUS.json
코드 백업: ~/DEV/TRANSFER/cm-oneclick-r11/code-backup/receipt.json
등록 전 기존 DB 백업: 같은 폴더의 CASE_STATE_BEFORE.sqlite.gz

등록 원복은 같은 runtime의 package-retire --common --store-version 4 --source
CM51_REGISTERED.json으로 해당 import만 retire합니다. 코드 원복은 code-backup의
receipt.json에 기록된 before/after 해시를 대조하고 백업 파일을 원래 위치로 복구한 뒤
별도 commit/push하며 이전 검증 리비전으로 돌아갑니다. 이후 변경된 파일은 덮어쓰지 않습니다.
원문 generation은 바꾸지 않습니다.

검증은 공개/모의 자료로 수행하며 모델 호출 없음. 실제 GENOS 등록/배포/워크플로우는
현장 실행 결과를 받기 전까지 미확인입니다.
'''
    guide = OUT/(NAME+'_GUIDE.txt');guide.write_text(guide_text)
    (OUT/'GUIDE_UTF8.txt').write_text(guide_text)
    sums = OUT/(NAME+'_SHA256SUMS.txt')
    sums.write_text(''.join(f'{sha(p.read_bytes())}  {p.name}\n' for p in (run, guide)))
    archive = OUT/(NAME+'.zip')
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in (run, guide, sums):z.write(path, path.name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and z.read(run.name) == run.read_bytes()
    record = {'version': NAME, 'oneclick_source_sha256': sha(code), 'parent_r10_run_sha256':
        sha((R10/'GENOS_CM_ONECLICK_20261007_R10_RUN.txt').read_bytes()),
        'budget_library_sha256': sha(budget_code), 'package_sha256': spec['package_sha256'],
        'recipes': len(spec['recipes']), 'r8_upgrades': len(spec['r8_upgrades']),
        'r10_upgrades': len(spec['r10_upgrades']), 'paths': spec['paths'],
        'GENOS_field_verified': False, 'code_serving_revision': None, 'model_calls': 0,
        'local_main_pointer_changed': False,
        'files': [{'name': p.name, 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())}
                  for p in (archive, run, guide, sums)]}
    (OUT/'HANDOFF.json').write_bytes(encoded(record))
    print('BUILT R11', len(spec['recipes']), 'recipes; ZIP', archive.stat().st_size, 'bytes')


if __name__ == '__main__':main()
