"""Build the user-requested Samsung overwrite handoff from selected MAIN bytes."""
from pathlib import Path
import ast,base64,hashlib,json,shutil,subprocess,zipfile

R=Path(__file__).resolve().parents[4]
H=R/'08_DEPLOYMENT/GENOS/handoffs/main138_full_mail_20261104_r1'
H.mkdir(exist_ok=False)
NAME='MAIN138_FULL_ORACLE_20261104_R1'
sha=lambda b:hashlib.sha256(b).hexdigest()
active=json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
assert active['generation']==138 and active['release_id']=='oracle-development-vector-20261104-r1'
release=json.loads((R/active['manifest_path']).read_text())
source=Path(__file__).parent/'MAIN138_ORACLE_VECTOR_20261104_R1.zip'
with zipfile.ZipFile(source) as z:
 old=json.loads(z.read('CODE_MANIFEST.json'));files={r['path']:z.read(r['path']) for r in old['files']}
 for row in old['files']:assert sha(files[row['path']])==row['sha256']
for n,h in release['files'].items():assert sha(files[n])==sha((R/release['code_root']/n).read_bytes())==h
excluded={n:files.pop(n) for n in list(files) if Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'}}
assert len(excluded)==1
manifest={**old,'files':[{'path':n,'sha256':sha(raw),'bytes':len(raw)} for n,raw in sorted(files.items())],
 'required_files':[{'path':n,'sha256':sha(raw),'bytes':len(raw),'reason':'Existing unchanged JavaScript asset; excluded from email by user attachment preference'} for n,raw in excluded.items()],
 'delivery_id':NAME,'original_verified_zip_sha256':sha(source.read_bytes()),'code_files_in_email':len(files)}
raw_manifest=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
archive=H/(NAME+'.zip')
with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for n,raw in sorted(files.items()):z.writestr(n,raw)
 z.writestr('CODE_MANIFEST.json',raw_manifest)
archive_sha=sha(archive.read_bytes())
original=(R/'08_DEPLOYMENT/GENOS/handoffs/main_full_20261016_r2/replace.py').read_text()
original=original.split("\nif __name__ == '__main__':")[0]
wrapper=r'''

# The tested whole-code installer above is reused without changing its apply/undo semantics.
def delivery_main():
    parser=argparse.ArgumentParser(description='MAIN138 full serving-code overlay; Oracle data and secrets untouched')
    parser.add_argument('action',choices=['check','apply','status','stage','gate-code','undo'])
    parser.add_argument('--root',type=Path,required=True,help='Actual existing Git checkout to overwrite')
    parser.add_argument('--backup',type=Path,help='Receipt directory printed by apply; required for undo')
    args=parser.parse_args()
    root=plain(args.root).resolve(strict=True)
    if not (root/'.git').exists():raise ValueError('Use the actual existing Git checkout')
    archive=plain(Path(os.environ['MAIN138_RUN_PATH']).resolve().parent/'__ZIP__')
    if sha(archive.read_bytes())!='__SHA__':raise ValueError('Wrong or changed ZIP; retain the attachment pair')
    content,_,_=full_payload(archive)
    manifest=json.loads(content['CODE_MANIFEST.json'][0])
    required=manifest.get('required_files',[])
    def dependencies():
        for row in required:
            p=plain(root/row['path'])
            if not p.is_file() or sha(p.read_bytes())!=row['sha256']:
                raise ValueError('Existing JavaScript dependency missing/different; no files changed: '+row['path'])
    def verify():
        dependencies()
        for n,(raw,_) in content.items():
            p=plain(root/n)
            if not p.is_file() or sha(p.read_bytes())!=sha(raw):raise ValueError('Installed bytes differ: '+n)
        subprocess.run([sys.executable,str(root/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py'),'--code-root',str(root)],check=True,cwd=root)
    with plain(root/'.genos-code-replacement.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.action=='undo':
            if args.backup is None:parser.error('--backup required for undo')
            backup=plain(args.backup).resolve(strict=True)
            if json.loads((backup/'receipt.json').read_text())['root']!=str(root):raise ValueError('Backup belongs to another checkout')
            rollback(backup)
            return
        dependencies()
        if args.action=='check':
            install(root,archive.parent,apply=False,archive=archive)
            # Compile/package checks above and existing dependency checks are read-only.
            print('MAIN138_CHECK_OK')
            return
        if args.action=='apply':
            backup=install(root,archive.parent,apply=True,archive=archive)
            verify()
            print('MAIN138_CODE_APPLIED BACKUP='+str(backup))
            return
        verify()
        if args.action=='stage':
            names=sorted(set(content)|{row['path'] for row in required})
            subprocess.run(['git','-C',str(root),'add','-f','--pathspec-from-file=-','--pathspec-file-nul'],input=('\0'.join(names)+'\0').encode(),check=True)
            print('MAIN138_STAGED_ONLY_REVIEW_BEFORE_COMMIT')
        elif args.action=='gate-code':
            subprocess.run([sys.executable,str(root/'06_TOOLS/COMMANDS/genos_release_gate.py'),'--code-zip',str(archive),'--deploy-root',str(root),'--code-only'],check=True,cwd=root)
        else:
            print('MAIN138_INSTALLED_HASHES_OK')

if __name__=='__main__':
    import subprocess
    os.umask(0o077)
    if sys.version_info<(3,11):raise SystemExit('Python3.11+ required; select GENOS_PYTHON')
    delivery_main()
'''.replace('__ZIP__',archive.name).replace('__SHA__',archive_sha)
# A literal NUL list separator is produced by Python at execution time.
wrapper=wrapper.replace("'\\\\0'", "'\\0'")
run='''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
task_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
task_log_dir="$task_dir/main138-install-logs"
mkdir -p -- "$task_log_dir"
task_log="$task_log_dir/$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$task_log") 2>&1
trap 'task_rc=$?; printf "MAIN138_EXIT=%s LOG=%s\\n" "$task_rc" "$task_log"' EXIT
export MAIN138_RUN_PATH="$task_dir/MAIN138_FULL_ORACLE_20261104_R1_RUN.txt"
export PYTHONDONTWRITEBYTECODE=1
"${GENOS_PYTHON:-python3}" - "$@" <<'MAIN138_INSTALL_PY'
'''+original+wrapper+'\nMAIN138_INSTALL_PY\n'
runpath=H/(NAME+'_RUN.txt');runpath.write_text(run)
subprocess.run(['bash','-n',str(runpath)],check=True)
ast.parse(original+wrapper,feature_version=(3,11))
guide='''MAIN138 전체 서빙 코드 덮어쓰기 — 개발계 GENOS / Oracle

첨부 파일
1) MAIN138_FULL_ORACLE_20261104_R1.zip — MAIN138 서빙 코드와 Oracle 점검 도구
2) MAIN138_FULL_ORACLE_20261104_R1_RUN.txt — 완전한 Bash 실행본
3) GUIDE.txt — 이 안내
4) ENVIRONMENT.txt — 추가/유지/제거할 환경설정
5) SHA256SUMS.txt — 첨부파일 해시

이 메일의 ZIP+RUN을 한 쌍으로 사용한다. 이전 MAIN136/MAIN138_ORACLE_VECTOR ZIP의 안내만으로 덮어쓰지 않는다.
메일 첨부에서 JavaScript를 제외하는 기존 선호에 따라 app.js 1개는 기존 파일을 유지한다.
그 파일의 SHA-256이 MAIN138과 같은지 먼저 확인하며 누락/불일치면 덮어쓰기 전에 중단한다.
엔진 pin을 임의로 바꿔 통과시키지 않는다. 이 ZIP은 서빙525 중524파일+점검3파일, JS1개 기존 의존성이다.
원문/검색/벡터 데이터, 비밀키, .env, .venv, .git, 기존 DB는 첨부하지 않는다.
PeCab/pyarrow 설치와 requirements 수정은 이번 실행에 없다.

업로드 위치와 작업 위치
GENOS 코드스페이스에서 ZIP과 RUN.txt를 같은 실제 TRANSFER/업로드 폴더에 그대로 올린다.
ZIP을 풀지 않아도 RUN이 검증해서 적용한다. 적용 대상은 실제 push할 기존 Git checkout이다.
아래 두 경로는 현장의 실제 절대경로로 한 번 지정한다. 예시 문자열을 그대로 사용하지 않는다.

export MAIN138_TRANSFER_DIR='실제 ZIP과 RUN이 있는 폴더 절대경로'
export MAIN138_DEPLOY_ROOT='실제 기존 Git checkout 절대경로'
export GENOS_PYTHON=python3

GENOS_PYTHON은 해당 코드스페이스에서 사용할 Python3.11 이상 실행파일 경로로 바꿀 수 있다.
실행 중인 개발 서버/자동 동기화를 멈춘 상태에서 다음을 순서대로 실행한다.

bash "$MAIN138_TRANSFER_DIR/MAIN138_FULL_ORACLE_20261104_R1_RUN.txt" check --root "$MAIN138_DEPLOY_ROOT"
bash "$MAIN138_TRANSFER_DIR/MAIN138_FULL_ORACLE_20261104_R1_RUN.txt" apply --root "$MAIN138_DEPLOY_ROOT"
bash "$MAIN138_TRANSFER_DIR/MAIN138_FULL_ORACLE_20261104_R1_RUN.txt" status --root "$MAIN138_DEPLOY_ROOT"

완료 표시: MAIN138_CHECK_OK → ENGINE_PREFLIGHT PASS → MAIN138_CODE_APPLIED → MAIN138_INSTALLED_HASHES_OK.
apply는 목록에 있는 전체 서빙코드를 덮어쓰고 기존 파일을 09_ARTIFACTS/BACKUPS/code-replacement 아래 보존한다.
목록 밖 파일을 일괄 삭제하지 않는다. 로그는 업로드 폴더/main138-install-logs에 남는다.

Git 반영과 배포 확인
git -C "$MAIN138_DEPLOY_ROOT" diff --check
git -C "$MAIN138_DEPLOY_ROOT" diff --stat
bash "$MAIN138_TRANSFER_DIR/MAIN138_FULL_ORACLE_20261104_R1_RUN.txt" stage --root "$MAIN138_DEPLOY_ROOT"
git -C "$MAIN138_DEPLOY_ROOT" diff --cached --stat
git -C "$MAIN138_DEPLOY_ROOT" commit -m "Apply MAIN138 Oracle development vector serving"
bash "$MAIN138_TRANSFER_DIR/MAIN138_FULL_ORACLE_20261104_R1_RUN.txt" gate-code --root "$MAIN138_DEPLOY_ROOT"

stage는 이 전달본 파일만 추가한다. 기존에 staging된 다른 작업이 있으면 commit 전에 함께 확인한다.
gate-code는 committed checkout과 ZIP+기존JS의 일치만 확인한다. Oracle전용이므로 NFS generation 검사와 다르다.
통과한 commit을 현장의 기존 push/배포 절차로 새 코드서빙 revision에 반영하고 ENVIRONMENT.txt 값을 저장한다.
실제 질의는 워크플로우 테스트 화면에서 HEALTH→원문→RAG_SEARCH→일반질문 순서로 확인한다.
RAG_SEARCH200만으로 벡터 실행을 판정하지 말고 아래 직접 점검과 vector_publication 기록을 확인한다.

Oracle 벡터 점검 (터미널에 같은 개발계 환경변수가 설정되어 있어야 함)
export MAIN138_DOC_ID='권한 있는 실제 Oracle 문서ID'
cd "$MAIN138_DEPLOY_ROOT"
"$GENOS_PYTHON" 06_TOOLS/COMMANDS/oracle_vector_probe.py --document-id "$MAIN138_DOC_ID" --metadata-only

모델 호출 없이 게시ID·모델프로필·필요한 GENOS_EMBED_PROFILE_SHA256을 출력한다.
적재 모델과 같은 GENOS 모델인 것을 확인한 후 ENVIRONMENT.txt의 MODEL/PROFILE_SHA256을 저장한다.
"$GENOS_PYTHON" 06_TOOLS/COMMANDS/oracle_vector_probe.py --document-id "$MAIN138_DOC_ID" --question "확인할 실제 질문"

정상 표시는 VECTOR_QUERY_COMPLETED/embedding_calls=1이며 후보수와 문서/원문ID를 확인한다.
후보0건이나 모델불일치는 별도 원인 확인 대상이다. 실제 원문/인용은 워크플로우 질문으로 대조한다.

중단/다시 실행/원복
정상 apply를 다시 실행하면 같은바이트를 확인해 ALREADY INSTALLED가 나온다.
진행중 강제중단이면 출력된 BACKUP/RECOVERY 폴더를 보존한다. 재실행이 복구를 요구하면 아래 undo후 apply한다.
export MAIN138_BACKUP_DIR='해당 실행이 출력한 백업 폴더 절대경로'
bash "$MAIN138_TRANSFER_DIR/MAIN138_FULL_ORACLE_20261104_R1_RUN.txt" undo --root "$MAIN138_DEPLOY_ROOT" --backup "$MAIN138_BACKUP_DIR"
원복 전후 파일을 임의로 수정하면 안전하게 중단하며 그 변경을 덮어쓰지 않는다.
이미 배포했다면 이전 Git commit/코드서빙 revision/환경설정도 현장 절차로 복원한다.

검증 범위
로컬 MAIN138 서빙525파일과 결속. 실제 임시 Oracle에서 원문·검색·벡터SQL·기록재조회 통과, 임베딩은 고정 시험값.
GENOS 실제 모델/현장배포 미확인. 추가 기존Gold 실임베딩 재검사는 자원보호 중단으로 전체 미완료다.
로컬 MAIN포인터·기존 Oracle 게시/원문은 이 메일 준비로 바뀌지 않는다.
'''
(H/'GUIDE.txt').write_text(guide)
(H/'ENVIRONMENT.txt').write_text('''MAIN138 개발계 추가 환경설정

이번에 추가/확인할 핵심 값
DP=oracle
GENOS_ORACLE_TABLE_MAPPING=development_g19_1
GENOS_RAG_INITIAL_SEARCH=vector
GENOS_EMBED_MODEL=<Oracle 벡터 적재모델과 동일한 GENOS serving 모델명>
GENOS_EMBED_PROFILE_SHA256=<metadata-only 결과에 출력된 프로필 SHA256>

PROFILE_SHA256은 임의로 만드는 값이 아니다. 같은 적재모델·revision·차원·COSINE/l2 설정임을 확인한 뒤 사용한다.
Dataiku Mesh ID와 GENOS serving명이 다른 경우에도 실제 모델/설정 동일성을 확인해야 한다.
vector는 벡터 실험모드, keyword는 기존 키워드모드. 모델/프로필 불일치는 명시 오류로 중단한다.

기존 값 유지/없을 때만 설정
DP_QUERY_CHANNEL=<현재 개발계 검색 게시 채널, 보통 main이나 실제값 확인>
  또는 DP_QUERY_RELEASE_ID=<실제 검색 게시ID>. 두 항목을 동시에 채우지 않는다.
GENOS_RAG_IMPLEMENTATION=legal-agent-unified-v6
ORACLE_ORDS_BASE_URL / ORACLE_ORDS_SCHEMA / ORACLE_ORDS_CLIENT_ID / ORACLE_ORDS_CLIENT_SECRET
  기존 ORDS 접속/인증 값 유지. client secret은 첨부/회신에 적지 않는다.
GENOS_BASE_URL / GENOS_EMBED_SERVING_ID / GENOS_EMBED_KEY / GENOS_EMBED_TENANT_ID
  기존 임베딩 serving 설정 유지. 직접 모델 URL 방식이면 GENOS_EMBED_URL을 사용한다.
GENOS_GATEWAY_API_PREFIX=none
  GENOS gateway 기본값이다. 직접 호환 모델 URL의 기본 prefix는 /v1이다.
GENOS_RUNTIME_DIR=/__oracle_agent__/runtime
  Oracle 논리 runtime의 기본값이다. 이미 다른 논리경로/namespace로 운영중이면 그대로 유지한다.
  경로나 GENOS_ORACLE_AGENT_NAMESPACE를 바꾸면 기존 실행기록과 다른 저장영역을 보게 된다.

기존 답변 LLM 설정과 로그 설정은 유지한다. PeCab/pyarrow용 추가 환경변수는 없다.
옛 DP_RELEASE_ID/DP_CACHE_DIR 로컬복원 방식은 제거한다. GENOS_GENERATION은 Oracle 게시 선택값이 아니다.
설정은 코드스페이스 시험환경과 새 코드서빙 revision 양쪽에 적용해야 하며 터미널 export만으로 서빙설정이 바뀌지 않는다.
값을 변경한 뒤 새 프로세스/리비전으로 확인한다.
''')
binding={'to':'hyungjininfocz.son@partner.samsung.com','from':'fromson99@gmail.com','active':active,
 'serving_files':525,'attachment_code_files':len(files),'existing_required_files':manifest['required_files'],
 'original_zip_sha256':sha(source.read_bytes()),'email_zip_sha256':archive_sha,'field_deployed':False}
(H/'HANDOFF.json').write_text(json.dumps(binding,ensure_ascii=False,indent=2)+'\n')
(H/'SHA256SUMS.txt').write_text('\n'.join(sha(p.read_bytes())+'  '+p.name for p in (archive,runpath,H/'GUIDE.txt',H/'ENVIRONMENT.txt'))+'\n')
print(json.dumps({'directory':str(H),'zip_bytes':archive.stat().st_size,'code_files':len(files),'existing_js':list(excluded)},ensure_ascii=False))
