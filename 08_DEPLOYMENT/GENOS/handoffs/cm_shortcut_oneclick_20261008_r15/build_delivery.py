"""Extend sealed R14 with authenticated preservation of the full-error R10 overlay."""
import ast
import base64
import copy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
import zlib

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
PARENT=OUT.with_name('cm_shortcut_oneclick_20261008_r14')
NAME='GENOS_CM_ONECLICK_20261008_R15'
PATH='02_BACKEND/lawrag/pipeline/shortcut_package.py'


def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()


def main():
    assert not (OUT/(NAME+'_RUN.txt')).exists(),'Preserve sealed deliveries; use a new revision'
    old=json.loads(gzip.decompress((PARENT/'PATCH_SPEC.json.gz').read_bytes()))
    hand=json.loads((PARENT/'HANDOFF.json').read_bytes())
    spec=copy.deepcopy(old)
    spec['revision']=NAME
    spec['r14_upgrades']={rid:rid for rid in old['recipes']}
    spec['r14_inventories']={rid:r['after'] for rid,r in old['recipes'].items()}
    logging=OUT.with_name('full_error_logging_20261007_r10')
    library=(logging/'INSTALL.py').read_bytes()
    policy=json.loads((logging/'PATCH_SPEC.json').read_bytes())
    spec['full_error_logging_overlay']={'library':base64.b64encode(library).decode(),
        'library_sha256':sha(library),'spec':policy,'spec_sha256':sha(encoded(policy))}
    (OUT/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(encoded(spec),mtime=0))
    code=(ROOT/'06_TOOLS/COMMANDS/genos_cm_oneclick.py').read_bytes()
    ast.parse(code,feature_version=(3,11))
    assert ("VERSION='"+NAME+"'").encode() in code
    bundle=encoded({'code':base64.b64encode(code).decode(),'spec':spec})
    packed=base64.b64encode(zlib.compress(bundle,9)).decode()
    script='''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
task_transfer="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
task_logs="$task_transfer/cm-oneclick-r15/logs"
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
printf 'CM R15 문서 이름·역할 연결 보완 시작 LOG=%s\\n' "$task_log"
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
    run=OUT/(NAME+'_RUN.txt');run.write_text(script)
    subprocess.run(['bash','-n',str(run)],check=True)
    guide_text='CM R15 — 오류 로그 R10 적용 후 R14 사전 검사 실패 보완\n\n정식 문서명·개별 파일명·보존된 원래 이름/별칭으로 연결합니다.\n부모 폴더명만 같은 시행령·시행규칙·시행세칙은 다른 법령에 연결하지 않습니다.\n정상 규정명에 포함된 서식·별첨은 보존하고 추가 개정·제정안·신구대비·요약·참고와\n별표/서식 폴더는 구분합니다. 분해된 한글(NFD)도 NFC로 대조합니다.\n본문/전문/조문을 유지하며 사본 번호·날짜·판본을 임의로 삭제하지 않습니다.\n금지 문자 치환이나 해시 접두어는 보존된 정식명/원래 이름으로 해결합니다.\n실제 원문 누락·중복 판본/조문·권한·세대 해시 불일치는 계속 중단합니다.\n\nZIP을 기존 ~/DEV/TRANSFER에 올리고 아래 세 줄을 실행합니다.\npython3 -m zipfile -e ~/DEV/TRANSFER/GENOS_CM_ONECLICK_20261008_R15.zip ~/DEV/TRANSFER\n(cd ~/DEV/TRANSFER && sha256sum -c GENOS_CM_ONECLICK_20261008_R15_SHA256SUMS.txt)\nbash ~/DEV/TRANSFER/GENOS_CM_ONECLICK_20261008_R15_RUN.txt\n\n별도 RUN TXT를 TRANSFER에 올렸으면 마지막 bash 한 줄로도 실행할 수 있습니다.\n오류 전체 표시 R10이 VERIFIED인 기존 DEV에서 이어 실행합니다.\nR10 백업·receipt·APPLIED_CODE.zip의 모든 바이트를 검증한 뒤,\nCM 이름 연결 코드를 적용하고 오류 출력 변환을 함께 보존합니다.\nR10을 다시 apply하거나 원복할 필요가 없습니다.\nR11 package-check 실패 상태와 이미 R12/R13/R14를 적용한 상태도 지원합니다.\n검증된 R8/R10/선행 코드도 지원합니다. 기존 조사 한도 설정과 service.py 바이트,\nR11/R12/R13/R14의 원래 부모 inventory·백업·실패 기록을 모두 대조해 보존합니다.\nR10 백업이 없거나 부분 적용 상태, 임의 수정이 있으면 적용하지 않고 중단합니다.\n알 수 없는 코드 변경이나 선택 generation 변경은 덮어쓰지 않습니다.\n원문 재구축·RAW 이름 변경·조사 한도 재적용·새 환경변수/사용자 JSON 입력은 없습니다.\n\n원문51건/근거98개 연결 확인 → commit → 같은 checkout/generation gate →\n공통 등록/검증 → 기존 origin push를 수행합니다. 기존 CM 등록도 원래 이름으로\n같은 문서·근거에 결속되는지 재대조한 뒤 재사용하며 중복 등록하지 않습니다.\n이전 등록이 다른 원문에 연결돼 있으면 기존 자료를 보존하고 중단합니다.\nEXIT=0과 READY_FOR_REVISION_DEPLOYMENT이면 출력된 COMMIT으로 새 코드서빙\n리비전을 배포하고 워크플로우 테스트 화면에서 질문을 확인합니다.\n코드 적용·등록·push·새 리비전·질문 성공은 각각 별도 상태입니다.\n\n상태/문서 연결/등록 영수증:\n~/DEV/TRANSFER/cm-oneclick-r15/STATUS.json\n~/DEV/TRANSFER/cm-oneclick-r15/DATA_CHECKED.json\n~/DEV/TRANSFER/cm-oneclick-r15/CM51_REGISTERED.json\n전체 로그/종료 상태: 같은 폴더 logs/<실행>.log 및 .EXIT_STATUS.json\n단계 상세: package-check.log / package-import.log / package-verify.log\n코드 백업: code-backup/receipt.json\n등록 전 DB 백업: CASE_STATE_BEFORE.sqlite.gz\n이전 CM 기록·조사 한도 백업·오류 로그 R10 백업·원문 generation·기존 DB는 보존합니다.\n\n코드 원복: code-backup/receipt.json의 before/after SHA와 현재 파일을 대조해\n백업을 같은 DEV 위치에 복원합니다. 현재 파일이 after SHA와 다르면 후속 변경을\n보존하고 중단합니다. 이후 별도 commit/gate/push와 이전 검증 리비전으로 복귀합니다.\n등록 원복: 같은 runtime의 package-retire --common --store-version 4 --source\nCM51_REGISTERED.json으로 해당 import만 retire합니다. 이전 등록을 재사용한 경우\n이번 코드 변경의 원복과 이전 공통 등록의 retire는 별도 판단입니다.\n원문 generation은 바꾸지 않습니다. 실제 GENOS 적용·배포·질문 성공은 현장 검증이 필요합니다.\n'
    guide=OUT/(NAME+'_GUIDE.txt');guide.write_text(guide_text)
    (OUT/'GUIDE_UTF8.txt').write_text(guide_text)
    sums=OUT/(NAME+'_SHA256SUMS.txt')
    sums.write_text(''.join(f'{sha(p.read_bytes())}  {p.name}\n' for p in (run,guide)))
    archive=OUT/(NAME+'.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for path in (run,guide,sums):z.write(path,path.name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and z.read(run.name)==run.read_bytes()
        assert all(Path(p).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for p in z.namelist())
    record={'version':NAME,'oneclick_source_sha256':sha(code),
        'parent_r14_run_sha256':sha((PARENT/'GENOS_CM_ONECLICK_20261008_R14_RUN.txt').read_bytes()),
        'parent_r14_handoff_sha256':sha((PARENT/'HANDOFF.json').read_bytes()),
        'package_sha256':spec['package_sha256'],'recipes':len(spec['recipes']),
        'full_error_library_sha256':sha(library),'full_error_spec_sha256':sha(encoded(policy)),
        'paths':spec['paths'],'GENOS_field_verified':False,'code_serving_revision':None,
        'model_calls':0,'local_main_pointer_changed':False,
        'files':[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in (archive,run,guide,sums)]}
    (OUT/'HANDOFF.json').write_bytes(encoded(record))
    print('BUILT R15',len(spec['recipes']),'recipes; ZIP',archive.stat().st_size,'bytes')


if __name__=='__main__':main()
