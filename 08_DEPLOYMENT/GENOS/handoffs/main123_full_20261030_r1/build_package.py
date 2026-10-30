from pathlib import Path
import ast, hashlib, json, shutil, subprocess, zipfile
ROOT=Path.cwd(); OUT=ROOT/'08_DEPLOYMENT/GENOS/handoffs/main123_full_20261030_r1'
NAME='GENOS_MAIN123_FULL_20261030_R1'; PKG=OUT/NAME
PKG.mkdir(exist_ok=True)
def digest(raw): return hashlib.sha256(raw).hexdigest()
def write_json(path, value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
active=json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text()); release_path=ROOT/active['manifest_path']; release=json.loads(release_path.read_text())
assert active['generation']==123 and digest(release_path.read_bytes())==active['release_manifest_sha256']
source=ROOT/release['code_root']; selected=release['files']; code={}; preserved={}; rows=[]
for name, expected in selected.items():
    raw=(source/name).read_bytes(); assert digest(raw)==expected and (ROOT/name).read_bytes()==raw,name
    if Path(name).suffix.lower() in ('.js','.jsx','.mjs','.cjs'): preserved[name]=expected; continue
    code[name]=raw
aux=['requirements-serving.txt','requirements.txt','06_TOOLS/COMMANDS/genos_generation_e2e.py']
for name in aux:
    assert name not in selected;code[name]=(ROOT/name).read_bytes()
for name, raw in sorted(code.items()):
    assert not any(p in name.split('/') for p in ('.git','.env','.venv','01_DATA'))
    if name.endswith('.py'):ast.parse(raw,filename=name,feature_version=(3,11));compile(raw,name,'exec')
    path=PKG/'payload'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    rows.append({'path':name,'sha256':digest(raw),'bytes':len(raw)})
manifest={'format':'8agent-code/1','release_id':release['release_id'],'files':rows,'required_files':[{'path':p,'sha256':h,'reason':'Existing JavaScript retained under Samsung attachment preference'} for p,h in preserved.items()]}
write_json(PKG/'CODE_MANIFEST.json',manifest)
with zipfile.ZipFile(PKG/'code.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    z.write(PKG/'CODE_MANIFEST.json','CODE_MANIFEST.json')
    for name in sorted(code):z.writestr(name,code[name])
shutil.copyfile(OUT/'runner.py',PKG/'runner.py')
shutil.copyfile(ROOT/'06_TOOLS/COMMANDS/genos_release_gate.py',PKG/'genos_release_gate.py')
run='''#!/usr/bin/env bash
# Run from the actual uploaded TRANSFER directory; target defaults to ~/DEV.
set -Eeuo pipefail
umask 077
TASK_TRANSFER="$PWD"
TASK_LOG_DIR="$TASK_TRANSFER/main123-full-r1-logs"
if [[ -L "$TASK_LOG_DIR" ]]; then echo "Refuse symlink log folder" >&2; exit 1; fi
mkdir -p "$TASK_LOG_DIR"
TASK_LOG="$TASK_LOG_DIR/$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$TASK_LOG") 2>&1
trap 'TASK_RC=$?; printf "%s\\n" "$TASK_RC" > "$TASK_LOG.exit"; echo "MAIN123_EXIT=$TASK_RC LOG=$TASK_LOG"' EXIT
TASK_PACKAGE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
if [[ ! -f "$TASK_PACKAGE/PACKAGE.json" ]]; then
  TASK_PACKAGE="$TASK_TRANSFER/GENOS_MAIN123_FULL_20261030_R1"
fi
if [[ ! -f "$TASK_PACKAGE/PACKAGE.json" ]]; then
  echo "Extract in the actual TRANSFER folder first:"
  echo "python3 -m zipfile -e ./GENOS_MAIN123_FULL_20261030_R1.zip ./GENOS_MAIN123_FULL_20261030_R1"
  exit 1
fi
printf 'TRANSFER=%s\\nPACKAGE=%s\\n' "$TASK_TRANSFER" "$TASK_PACKAGE"
python3 -u "$TASK_PACKAGE/runner.py" "${@:-check}"
'''
run_name=NAME+'_RUN.txt';(PKG/run_name).write_text(run);subprocess.run(['bash','-n',str(PKG/run_name)],check=True)
workflow_name='GENOS_MAIN123_WORKFLOW_PASTE_ALL.txt';(PKG/workflow_name).write_bytes(code['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'])
shutil.copyfile(ROOT/'09_ARTIFACTS/AUDITS/20261030-source-semantics-main123/수정과_실제실험_결과.txt',PKG/'MAIN123_RESULTS.txt')
shutil.copyfile(ROOT/'07_DOCS/REFERENCE/OPERATIONS/DOMAIN_PROFILE_WORKFLOW_20261029.txt',PKG/'DOMAIN_PROFILE_WORKFLOW.txt')
write_json(PKG/'SELECTED_RELEASE_RECORD.json',{'active_release':active,'release':release,'note':'Audit evidence only. Do not copy this local active pointer or local data selection into GENOS.'})
write_json(PKG/'SOURCE_BINDING.json',{'main':123,'release_id':release['release_id'],'selected_serving_files':len(selected),'included_serving_files':len(selected)-len(preserved),'auxiliary_files':aux,'preserve_existing':preserved,'tested_code_root':str(source),'release_manifest_sha256':active['release_manifest_sha256'],'code_zip_sha256':digest((PKG/'code.zip').read_bytes()),'workflow_sha256':digest((PKG/workflow_name).read_bytes()),'local_generation_path':str(ROOT/release['data_path']),'local_generation_manifest_sha256':release['data_manifest_sha256'],'deployment_checkout_requested':'~/DEV','field_checkout_physical':None,'field_commit':None,'field_generation_path':None,'field_generation_manifest_sha256':None,'field_code_serving_revision':None,'field_runtime':None,'quality_certified':False,'field_deployment_verified':False})
(PKG/'COMMIT_PATHS.txt').write_text('\n'.join(sorted(code))+'\n')
guide=f'''MAIN123 전체 실행 코드 인계 / 2026-10-30
이전 MAIN 코드 첨부 대신 GENOS_MAIN123_FULL_20261030_R1.zip을 사용합니다.
선택된 MAIN123의 실행 코드 전체가 기준입니다. 서빙489개 중488개와 운영 보조3개를 포함합니다.
삼성 전달 기준에 따라 JS1개는 첨부하지 않습니다. 기존 DEV의 해당 파일이 CODE_MANIFEST.required_files 해시와 일치해야 적용합니다.
과거 실험 폴더/DB/모델/비밀정보/로컬 활성 포인터는 설치 대상이 아닙니다. 현장 데이터 및 환경설정은 보존합니다.

1. 실제 업로드한 TRANSFER 폴더에서 시작합니다. TRANSFER 절대경로를 임의로 가정하지 마세요.
python3 -m zipfile -e ./GENOS_MAIN123_FULL_20261030_R1.zip ./GENOS_MAIN123_FULL_20261030_R1
bash ./GENOS_MAIN123_FULL_20261030_R1/GENOS_MAIN123_FULL_20261030_R1_RUN.txt check
bash ./GENOS_MAIN123_FULL_20261030_R1/GENOS_MAIN123_FULL_20261030_R1_RUN.txt apply

대상은 기존 Git checkout ~/DEV입니다. 다른 경로라면 모든 명령 뒤에 --root 실제_DEV_경로를 동일하게 붙입니다.
TRANSFER와 DEV는 분리해야 합니다. python3를 사용하고 가상환경 실행 경로를 가정하지 않습니다.
check는 패키지/기존 JS/로컬 변경/파이썬 문법을 검사합니다. 변경한 기존 파일이나 충돌하는 미추적 파일은 자동 덮어쓰지 않습니다.
apply 전 원본을 패키지 backup/에 보관하고 INSTALL_STATE.json을 남깁니다. 동일 apply 재실행은 안전하게 이어집니다.
실행 시작부터 TRANSFER/main123-full-r1-logs/에 성공/실패 로그와 종료코드가 남습니다.

2. 반영 파일을 확인하고 현장에서 commit합니다. 설치기는 commit/push/배포하지 않습니다.
git -C ~/DEV diff --check
git -C ~/DEV diff --stat
COMMIT_PATHS.txt의 파일만 검토해 commit한 후 실제 push checkout에 대해 아래를 실행합니다.
bash ./GENOS_MAIN123_FULL_20261030_R1/GENOS_MAIN123_FULL_20261030_R1_RUN.txt gate-code
이 검사는 패키지 전체와 보존 JS가 같은 바이트로 Git에 반영됐는지 확인합니다.
Oracle 운영은 기존 접속/설정을 유지합니다. NFS generation을 쓰는 환경에서만 다음을 추가 실행합니다.
python3 ./GENOS_MAIN123_FULL_20261030_R1/genos_release_gate.py --code-zip ./GENOS_MAIN123_FULL_20261030_R1/code.zip --deploy-root ~/DEV --generation 실제_GENERATION_절대경로
실제_GENERATION_절대경로는 현장에서 확인해 바꿀 값입니다. SOURCE_BINDING의 로컬 generation 경로를 복사하지 마세요.

3. 게이트가 통과한 commit을 push하고 코드서빙의 새 리비전을 따로 배포합니다.
그 리비전의 commit/데이터 선택/환경과 실제 적용된 파일 해시를 기록합니다.
워크플로우 편집기에는 GENOS_MAIN123_WORKFLOW_PASTE_ALL.txt 전체를 별도로 붙여 넣습니다.
실제 테스트/웜업은 워크플로우 테스트 화면에서 수행하고 요청ID/응답을 기록합니다.
여기서 만든 로컬 검사 통과는 GENOS 현장 배포나 전체 RAG 답변 성공을 뜻하지 않습니다.

복구
bash ./GENOS_MAIN123_FULL_20261030_R1/GENOS_MAIN123_FULL_20261030_R1_RUN.txt rollback
현재 파일이 설치 전후 해시 중 하나일 때만 원본 복구합니다. 이후 현장 Git/서빙 리비전 복구는 별도 수행합니다.
이 패키지는 데이터와 과거 세대를 변경하지 않습니다. backup/과 설치 상태/로그는 복구 때까지 보존하세요.

검증 범위와 남은 문제
MAIN123_RESULTS.txt는 개발·실험 당시 원문 보고서이며 마지막 '메일 없음'은 보고서 작성 시점의 상태입니다.
실제9호출에서 error/null은 없었고, 없는 이유/목적6개는 미기록으로 보존했으며, 오판 지지는 PARTIAL로 바뀌었습니다.
누적 저장은0건이고, 마지막 SAME 제한 수정은 오프라인84계약 검증입니다. 새 실모델로 전체 누적 성공을 확인한 것은 아닙니다.
특정 조문/정답/역할 단어 목록을 제품에 넣지 않았습니다. 법률품질 인증이나 GENOS 현장 성공을 주장하지 않습니다.
'''
(PKG/'GUIDE.txt').write_text(guide)
payload={p.relative_to(PKG).as_posix():digest(p.read_bytes()) for p in PKG.rglob('*') if p.is_file() and p.name!='PACKAGE.json'}
spec={'version':NAME,'code':{**{p:digest(b) for p,b in code.items()},**preserved},'patch':sorted(code),'payload':payload,'selected_release_id':release['release_id'],'selected_main':123,'field_deployment_verified':False}
write_json(PKG/'PACKAGE.json',spec)
with zipfile.ZipFile(OUT/(NAME+'.zip'),'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for p in sorted(PKG.rglob('*')):
        if p.is_file():z.write(p,p.relative_to(PKG).as_posix())
for name in [run_name,workflow_name,'MAIN123_RESULTS.txt','GUIDE.txt']:shutil.copyfile(PKG/name,OUT/name)
attachments=[NAME+'.zip',run_name,workflow_name,'MAIN123_RESULTS.txt','GUIDE.txt']
record={'recipient':'hyungjininfocz.son@partner.samsung.com','main':123,'attachments':[{'filename':p,'path':str(OUT/p),'bytes':(OUT/p).stat().st_size,'sha256':digest((OUT/p).read_bytes())} for p in attachments],'code_files':len(code),'preserved_js':preserved,'selected_binding':json.loads((PKG/'SOURCE_BINDING.json').read_text())}
write_json(OUT/'HANDOFF.json',record)
print(json.dumps({'attachments':[{k:v for k,v in a.items() if k!='path'} for a in record['attachments']],'serving_files':len(selected),'packaged_code':len(code),'preserved':len(preserved)},ensure_ascii=False))
