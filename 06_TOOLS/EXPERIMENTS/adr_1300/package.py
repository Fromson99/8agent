from common import *
import shutil,zipfile,subprocess,tempfile,os
f=read(DES/'freeze-v2.json');code=ROOT/f['code_root']
folder=ROOT/'08_DEPLOYMENT/GENOS/handoffs/connected_sources_20261103_r1';folder.mkdir(exist_ok=False)
name='GENOS_CONNECTED_SOURCES_20261103_R1';pkg=folder/name;pkg.mkdir()
workflow='08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
base=ROOT/'08_DEPLOYMENT/RELEASES/ontology-console-20261103-r1/code'
assert sha(code/workflow)==f['files'][workflow]
dest=pkg/'payload'/workflow;dest.parent.mkdir(parents=True);shutil.copyfile(code/workflow,dest)
shutil.copyfile(code/workflow,pkg/'GENOS_워크플로우_편집기.txt')
shutil.copyfile(ROOT/'06_TOOLS/EXPERIMENTS/adr_1300/handoff_installer.py',pkg/'install.py')
gate=ROOT/'08_DEPLOYMENT/GENOS/handoffs/main123_full_20261030_r1/GENOS_MAIN123_FULL_20261030_R1/genos_release_gate.py'
shutil.copyfile(gate,pkg/'genos_release_gate.py')
required=[{'path':n,'sha256':sha(base/n)} for n in sorted(f['files']) if n!=workflow and (base/n).is_file()]
manifest={'format':'8agent-code/1','scope':'one-file source display patch; not a full MAIN release',
    'files':[{'path':workflow,'sha256':sha(dest),'bytes':dest.stat().st_size,'previous_sha256':sha(base/workflow)}],
    'required_files':required,'verified_code_root':str(code),'base_main':'MAIN134/ontology-console-20261103-r1',
    'local_generation':str(ROOT/read(DES/'source.json')['data_path']),
    'local_generation_manifest_sha256':sha(ROOT/read(DES/'source.json')['data_path']/'manifest.json'),
    'field_checkout':'~/DEV','field_commit':None,'field_generation':None,'field_serving_revision':None,
    'actual_field_executed':False,'quality_certified':False}
put(pkg/'payload/CODE_MANIFEST.json',manifest)
with zipfile.ZipFile(pkg/'code.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted((pkg/'payload').rglob('*')):
        if p.is_file():z.write(p,p.relative_to(pkg/'payload'))
shell='''#!/usr/bin/env bash
set -euo pipefail
package_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
operation="${1:-check}"
mkdir -p "$package_dir/logs"
run_log="$package_dir/logs/${operation}-$(date +%Y%m%d-%H%M%S)-$$.log"
exec > >(tee -a "$run_log") 2>&1
trap 'code=$?; echo "EXIT_STATUS=$code"; exit "$code"' EXIT
python3 "$package_dir/install.py" "$operation" --root "$HOME/DEV"
'''
(pkg/'실행.txt').write_text(shell)
guide=f'''GENOS 출처 펼침 수정본 — 현장 미배포, MAIN134 기반 부분 패치

검증: 동결 후보의 표시 계약49개, 실제 workflow run의 dict/socket 동일 전달,
로컬 Chromium의 접힘→펼침→재접힘 통과. GENOS HTML 정제/렌더러는 현장 확인 전입니다.
검토 미완료 본문에는 확보 문서·조항 범위만 표시하고, 원문은 출처 안에서 펼칩니다.
이 수정은 법률 내용을 요약한 확정 답변이나 최종 검토 성공을 만들어 내지 않습니다.

업로드한 TRANSFER 폴더를 현재 위치로 두고 실행합니다. TRANSFER 절대 위치를 가정하지 않습니다.
python3 -m zipfile -e ./{name}.zip ./{name}
bash ./{name}/실행.txt check
bash ./{name}/실행.txt apply

적용 대상은 기존 ~/DEV입니다. MAIN134 의존 코드 해시가 다르면 쓰기 전에 중단합니다.
다른 현장 버전에는 이 패치를 강제로 덮어쓰지 말고 차이를 검토해야 합니다.
첫 check부터 logs에 지속 기록/종료 상태를 보존합니다. 기존 파일 백업은 ~/DEV/09_ARTIFACTS/GENOS_PATCH_BACKUPS에 있습니다.

코드 변경 검토와 commit 후, TRANSFER 위치에서 게이트를 실행합니다.
git -C "$HOME/DEV" diff --check
git -C "$HOME/DEV" diff -- {workflow}
해당 변경만 검토하여 commit한 뒤:
python3 ./{name}/genos_release_gate.py --code-zip ./{name}/code.zip --deploy-root "$HOME/DEV"
게이트는 현재 설정/CURRENT의 generation을 선택하여 실제 checkout의 E2E와 verify_assets를 실행합니다.
다른 generation을 선택해야 하면 --generation에 확인된 절대경로를 명시합니다.
게이트가 출력한 commit·ZIP SHA·generation 경로와 manifest SHA를 기록합니다.
확인한 commit을 push하고 새 코드서빙 리비전에 연결합니다. NFS 데이터를 새로 만들거나 바꾸는 패치가 아닙니다.

별도로 GENOS 워크플로우 Python 편집기에 GENOS_워크플로우_편집기.txt 전체를 반영하고 저장합니다.
워크플로우 테스트 화면 질문: SOURCE_DISPLAY_CHECK
예상: '출처'를 누르면 합성 문서 목록, 문서명을 누르면 확인 문장, 다시 누르면 접힘.
이 확인은 모델/백엔드 호출0이며 answer_display_revision=workflow-source-summary-20261103-r1입니다.
HTML 태그가 문자로 보이거나 눌리지 않으면 현장 표시 미통과입니다. 서버 변경 성공으로 대신 판정하지 않습니다.
표시 확인 후 실제 질문으로 요청 ID·선택 리비전·답변/원문을 확인합니다. 코드서빙 직접 테스트 UI를 요구하지 않습니다.

원복: bash ./{name}/실행.txt rollback
원복 파일을 검토/commit하고 이전 코드서빙 리비전·기존 generation으로 복귀합니다.
워크플로우 편집기도 백업한 이전 Python 내용으로 되돌립니다.

검증 파일 SHA256: {sha(dest)}
code.zip SHA256: {sha(pkg/'code.zip')}
현장 commit/리비전/generation 경로 및 해시: 미확인. 현재 로컬 MAIN134 포인터는 변경하지 않았습니다.
'''
(pkg/'사용안내.txt').write_text(guide)
archive=folder/f'{name}.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(pkg.rglob('*')):
        if p.is_file():z.write(p,p.relative_to(pkg))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for n in z.namelist():assert hashlib.sha256(z.read(n)).hexdigest()==sha(pkg/n)
put(folder/'검증_인계.json',{'zip':str(archive.relative_to(ROOT)),'zip_sha256':sha(archive),
    'workflow_sha256':sha(dest),'code_manifest_sha256':sha(pkg/'payload/CODE_MANIFEST.json'),
    'required_files':len(required),'actual_genos_field':False,'main_changed':False})
print(str(archive));print('ZIP_SHA256',sha(archive))
