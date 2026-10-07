"""Prepare the existing optimization bytes plus a prepared-input OFF rebuild launcher."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / '08_DEPLOYMENT/GENOS/handoffs/pipeline_optimization_20261002_r1/payload'
OUT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/pipeline_optimization_20261002_r2'
STEM = 'GENOS_PIPELINE_OPTIMIZATION_20261002_R2'
HELPERS = ['genos_optimized_rebuild.py', 'genos_rebuild_logging.py',
           'genos_meaning_variants.py', 'genos_meaning_recover_r1.py']

GUIDE = '''GENOS 준비본 재사용·최적화 OFF 재구축 R2 / 2026-10-02

이번 실행에서는 이 R2 ZIP/TXT를 사용합니다. 이전 최적화 R1/복구 R1~R3는 보관합니다.
R1 최적화의 11개 코드 바이트를 그대로 사용하며 준비본 재사용·명시 참조·지속 로그를 연결했습니다.
사진에서 완료된 구조화/원문/용어집을 재사용합니다. RAW 변환·구조화·새 용어 의미 검토를 실행하지 않습니다.
의미 검토는 용어 후보의 SAME/DIFFERENT/UNKNOWN과 관계를 LLM으로 검토하는 별도 단계입니다.
현재 OFF 구축은 이를 생략하지만 기존 용어집의 정의·관계·과거 검토 산출물은 그대로 사용합니다.
명시 참조는 '다른 규정 제N조'와 같은 원문 참조를 연결하는 별도 작업으로 기존 내부 모델 경로를 유지합니다.

같이 올릴 파일: GENOS_PIPELINE_OPTIMIZATION_20261002_R2.zip / 같은 이름의 .txt
  cd ~/DEV
  export GENOS_PREPARED_RUN=financial-risk-success-20261001-r3
  export GENOS_OPTIMIZED_RUN=financial-risk-success-20261002-opt-r2
  bash TRANSFER/GENOS_PIPELINE_OPTIMIZATION_20261002_R2.txt

기본값(위 두 run 값도 기본값입니다):
  GENOS_DEV=$HOME/DEV                         코드 checkout
  GENOS_DATA_ROOT=$GENOS_DEV/01_DATA          준비본/로그/출력 data root
  GENOS_PREPARED_RUN=financial-risk-success-20261001-r3   읽을 준비 run
  GENOS_OPTIMIZED_RUN=financial-risk-success-20261002-opt-r2   새 출력 run
  GENOS_REFERENCE_BATCH=8                    명시 참조 요청 묶음(1..32)
  GENOS_REFERENCE_CASES=10000                한 advance의 사례 한도(1..10000), 완료까지 반복
  GENOS_LOG_INTERVAL=5                       무출력 구간 생존 로그 간격(초, 0 초과)
  GENOS_OPTIMIZED_SHARED_ROOT=/nfs-root/diamo/8-agent/term-releases
      공유 발행 대상. 빈 문자열로 설정하면 로컬 새 출력까지만 생성합니다.
  GENOS_OPTIMIZATION_ZIP                     ZIP 위치를 바꿀 때만 설정

기존 입력은 run의 plan/source/draft/selection/내부 모델 profile 해시·원문 범위를 확인해 읽습니다.
source는 TERM_RELEASES/$GENOS_PREPARED_RUN/sources/store.sqlite,
용어집은 같은 run의 glossary-draft입니다. 입력 파일을 임의 최신 경로로 고르지 않습니다.
새 출력: TERM_RELEASES/$GENOS_OPTIMIZED_RUN/meaning-variants/off/serving/generation
새 공유 출력: $GENOS_OPTIMIZED_SHARED_ROOT/$GENOS_OPTIMIZED_RUN-meaning-off/generation
원래 2,121개 선택본이면 실제 확인 문서 수가 2,121로 나와야 합니다. 다르면 입력 선택을 확인합니다.

순서: 지속 로그 시작 → 기록된 이전 worker만 SIGINT·종료 확인 → checkout hash 검사 →
준비본 검증 → 코드/pin 백업·적용 → 새 run 계보 동결 → 연결 → 원문 세대 → 용어집 캐시 →
navigation/감사 색인 → 전문 색인 → 명시 참조 처리/적용 → 검증 → 별도 공유 발행.
오래 걸리는 hash/copy/cache/참조/검증에도 START/RUNNING/DONE/FAILED와 실제 경로를 남깁니다.
내부 모델 자격증명은 마스킹하고 원문/요청/응답 근거 파일은 기존 원장 경로에 남습니다.
RUNNING은 생존 표시입니다. 처리량이 기록되지 않은 구간의 ETA/완료율을 만들어 표시하지 않습니다.

로그는 시작 시 찍힌 $GENOS_DATA_ROOT/LOGS/$GENOS_OPTIMIZED_RUN/optimized-rebuild-r2/<시각-PID>/ 아래:
  run.log       적용/검증/native stdout/stderr/traceback 전체, 터미널에도 즉시 출력
  events.jsonl  START/RUNNING/DONE/FAILED/INTERRUPTED/최종 종료 이벤트
  phases.csv    단계별 상태와 시간
  current.json  현재/최종 상태
  summary.txt   종료 코드와 로그 안내
  payload/      검증해 해제한 ZIP 및 적용/롤백 실행기
실패도 FINISHED status=...를 남깁니다. 도중 source/hash drift는 성공 처리하지 않습니다.

기존 결과를 삭제할 필요는 없습니다. 새 run으로 분리해 예전 index를 자동 선택하지 않습니다.
RAW/STRUCTURE/sources/glossary-draft/검토 원장/기존 plan/완료 세대/실패 scratch는 보존합니다.
기록된 worker만 boot ID/PID 시작시각 확인 후 중단하며 120초 내 종료하지 않으면 적용 전에 멈춥니다.
모르는 foreground 작업은 해당 터미널에서 정상 중단한 뒤 실행합니다. 일괄 kill/rm을 하지 않습니다.
구 코드에서 빠진 navigation_storage는 이 ZIP의 검증된 파일만 새로 추가할 수 있습니다.
그 외 예상 밖 파일 변화는 FILE_DRIFT로 중단합니다. core와 engine/pipeline pin의 백업/영수증이 남습니다.

사전 검사(기존 worker가 끝난 상태에서):
  bash TRANSFER/GENOS_PIPELINE_OPTIMIZATION_20261002_R2.txt check
이전 기록 worker 중단만:
  bash TRANSFER/GENOS_PIPELINE_OPTIMIZATION_20261002_R2.txt stop-old
재실행은 동일 TXT/ZIP/입력/새 run 설정으로 합니다. 완료한 navigation 뒤 전문 색인이 실패하면
checkpoint를 검증해 전문 색인부터 재개합니다. 완료 결과는 검증해 재사용합니다.
실행 코드·입력·설정이 바뀌었으면 기존 plan을 고치지 말고 또 다른 GENOS_OPTIMIZED_RUN을 사용합니다.
코드 롤백은 로그의 backup 경로로:
  python3 /로그경로/payload/APPLY.py --rollback /DEV/.genos-pipeline-optimization-backups/실제시각

새 generation·공유 파일 발행과 Git push·CURRENT·서빙 revision·workflow 반영은 별도입니다.
이 TXT는 활성 포인터/서빙/workflow를 바꾸지 않습니다. 실제 검색/warmup은 workflow 테스트 화면에서 확인합니다.
로컬 합성 계약 성공은 GENOS 실행·품질·시간 단축을 보증하지 않습니다.
'''

SCRIPT = r'''#!/usr/bin/env bash
set -Eeuo pipefail
task_action="${1:-build}"
TASK_DEV="${GENOS_DEV:-${HOME}/DEV}"
export GENOS_DATA_ROOT="${GENOS_DATA_ROOT:-$TASK_DEV/01_DATA}"
export GENOS_PREPARED_RUN="${GENOS_PREPARED_RUN:-financial-risk-success-20261001-r3}"
export GENOS_OPTIMIZED_RUN="${GENOS_OPTIMIZED_RUN:-financial-risk-success-20261002-opt-r2}"
task_log_run='invalid-run'
if [[ "$GENOS_OPTIMIZED_RUN" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$ ]]; then task_log_run="$GENOS_OPTIMIZED_RUN"; fi
TASK_LOG_DIR="$GENOS_DATA_ROOT/LOGS/$task_log_run/optimized-rebuild-r2/$(date -u +%Y%m%dT%H%M%S)-${BASHPID}"
mkdir -p "$TASK_LOG_DIR"
exec > >(tee -a "$TASK_LOG_DIR/run.log") 2>&1
task_heartbeat_pid=''
finish() {
  task_status=$?
  if [[ -n "$task_heartbeat_pid" ]]; then kill "$task_heartbeat_pid" 2>/dev/null || true; fi
  printf 'FINISHED status=%s log=%s\n' "$task_status" "$TASK_LOG_DIR"
  printf '전체 종료 코드: %s\n전체 출력: %s/run.log\n' "$task_status" "$TASK_LOG_DIR" >> "$TASK_LOG_DIR/summary.txt"
  exit "$task_status"
}
trap finish EXIT
trap 'printf "FAILED line=%s\n" "$LINENO"' ERR
trap 'exit 130' INT
trap 'exit 143' TERM
printf 'START UTC=%s action=%s prepared=%s new_run=%s log=%s\n' "$(date -u +%FT%TZ)" "$task_action" "$GENOS_PREPARED_RUN" "$GENOS_OPTIMIZED_RUN" "$TASK_LOG_DIR"
[[ $# -le 1 ]] || { echo 'Usage: bash SCRIPT.txt [build|check|stop-old]'; exit 2; }
[[ "$GENOS_PREPARED_RUN" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$ ]] || { echo 'Invalid prepared run ID'; exit 2; }
[[ "$GENOS_OPTIMIZED_RUN" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$ ]] || { echo 'Invalid output run ID'; exit 2; }
case "$task_action" in build|check|stop-old) ;; *) echo 'Unknown action'; exit 2 ;; esac
[[ "$GENOS_PREPARED_RUN" != "$GENOS_OPTIMIZED_RUN" ]] || { echo 'Use a NEW output run ID'; exit 2; }
[[ -d "$TASK_DEV/02_BACKEND" ]] || { echo "Missing DEV checkout: $TASK_DEV"; exit 2; }
export PYTHONUNBUFFERED=1
run_stage() {
  local task_label="$1"; shift
  local task_started=$SECONDS
  local task_rc=0
  printf 'STAGE %s START\n' "$task_label"
  (while sleep "${GENOS_LOG_INTERVAL:-5}"; do
      printf 'STAGE %s RUNNING elapsed=%ss remaining=not_measured\n' "$task_label" "$((SECONDS-task_started))"
   done) &
  task_heartbeat_pid=$!
  if "$@"; then task_rc=0; else task_rc=$?; fi
  kill "$task_heartbeat_pid" 2>/dev/null || true
  wait "$task_heartbeat_pid" 2>/dev/null || true
  task_heartbeat_pid=''
  printf 'STAGE %s END status=%s elapsed=%ss\n' "$task_label" "$task_rc" "$((SECONDS-task_started))"
  return "$task_rc"
}
exec 9>"$GENOS_DATA_ROOT/LOGS/$GENOS_OPTIMIZED_RUN/optimized-rebuild-r2/launcher.lock"
flock -n 9 || { echo 'This output run has an active launcher'; exit 1; }
TASK_ZIP="${GENOS_OPTIMIZATION_ZIP:-$(dirname "$(realpath "$0")")/__STEM__.zip}"
run_stage verify-extract python3 -u - "$TASK_ZIP" "$TASK_LOG_DIR/payload" <<'VERIFY'
import hashlib,json,pathlib,sys,zipfile
print('PYTHON',sys.executable,sys.version,flush=True)
if sys.version_info<(3,11):raise SystemExit('Python 3.11 or later required')
p=pathlib.Path(sys.argv[1]);digest=hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
if digest!='__ZIP_SHA__':raise SystemExit('ZIP hash mismatch; stopped before code application')
print('ZIP_SHA256',digest,flush=True)
with zipfile.ZipFile(p) as z:
 m=json.loads(z.read('CODE_MANIFEST.json'))
 if len(z.namelist())!=len(set(z.namelist())):raise SystemExit('Duplicate ZIP members')
 if set(z.namelist())!={r['path'] for r in m['files']}|{'CODE_MANIFEST.json'}:raise SystemExit('Inventory mismatch')
 for r in m['files']:
  name=pathlib.PurePosixPath(r['path']);item=z.getinfo(r['path'])
  if name.is_absolute() or '..' in name.parts or name.suffix.lower() in {'.js','.jsx','.mjs','.cjs'}:raise SystemExit('Invalid archive member')
  if (item.external_attr>>16)&0o170000==0o120000:raise SystemExit('Archive symlink rejected')
  if hashlib.sha256(z.read(r['path'])).hexdigest()!=r['sha256']:raise SystemExit('Member hash mismatch')
 z.extractall(sys.argv[2])
 print('ARCHIVE VERIFIED members='+str(len(z.namelist())),flush=True)
VERIFY
task_runner="$TASK_LOG_DIR/payload/06_TOOLS/OFFLINE/genos_optimized_rebuild.py"
task_args=(--dev "$TASK_DEV" --data-root "$GENOS_DATA_ROOT" --prepared-run "$GENOS_PREPARED_RUN" --run-id "$GENOS_OPTIMIZED_RUN" --code-manifest "$TASK_LOG_DIR/payload/CODE_MANIFEST.json" --log-dir "$TASK_LOG_DIR" --reference-batch "${GENOS_REFERENCE_BATCH:-8}" --reference-cases "${GENOS_REFERENCE_CASES:-10000}" --heartbeat "${GENOS_LOG_INTERVAL:-5}")
if [[ "$task_action" == stop-old || "$task_action" == build ]]; then
  run_stage stop-old python3 -u "$task_runner" stop-old "${task_args[@]}"
fi
if [[ "$task_action" == stop-old ]]; then exit 0; fi
run_stage code-preflight python3 -u "$TASK_LOG_DIR/payload/APPLY.py" --dev "$TASK_DEV" --check
run_stage prepared-input-check python3 -u "$task_runner" check "${task_args[@]}"
if [[ "$task_action" == check ]]; then exit 0; fi
run_stage code-apply python3 -u "$TASK_LOG_DIR/payload/APPLY.py" --dev "$TASK_DEV"
task_shared="${GENOS_OPTIMIZED_SHARED_ROOT-/nfs-root/diamo/8-agent/term-releases}"
if [[ -n "$task_shared" ]]; then task_args+=(--shared-root "$task_shared"); fi
run_stage optimized-off-rebuild python3 -u "$TASK_DEV/06_TOOLS/OFFLINE/genos_optimized_rebuild.py" build "${task_args[@]}"
'''


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    old = json.loads((OLD / 'CODE_MANIFEST.json').read_text())
    payload, rows = {}, []
    for row in old['files']:
        if row['role'] == 'code':
            content = (OLD / row['path']).read_bytes()
            assert hashlib.sha256(content).hexdigest() == row['sha256']
            payload[row['path']] = content
            rows.append({**row, 'allow_missing': row['path'] == '02_BACKEND/semantic_runtime/navigation_storage.py'})
    for name in HELPERS:
        path = '06_TOOLS/OFFLINE/' + name
        content = (ROOT / path).read_bytes()
        payload[path] = content
        rows.append({'path': path, 'sha256': hashlib.sha256(content).hexdigest(), 'role': 'code',
                     'allowed_predecessors': [], 'allow_missing': True})
    payload['APPLY.py'] = (ROOT / '06_TOOLS/OFFLINE/genos_optimization_apply_r2.py').read_bytes()
    payload['GUIDE_UTF8.txt'] = GUIDE.encode()
    for name in ('APPLY.py', 'GUIDE_UTF8.txt'):
        rows.append({'path': name, 'sha256': hashlib.sha256(payload[name]).hexdigest(), 'role': 'handoff'})
    manifest = {'schema_version': 'genos-pipeline-optimization-r2',
                'base_code_manifest_sha256': hashlib.sha256((OLD / 'CODE_MANIFEST.json').read_bytes()).hexdigest(),
                'files': rows, 'prepared_input_reuse': True, 'meaning_review': 'SKIPPED', 'activated': False}
    payload['CODE_MANIFEST.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    archive = OUT / (STEM + '.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name, content in payload.items():
            assert Path(name).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}
            z.writestr(name, content)
    zip_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    script = OUT / (STEM + '.txt')
    script.write_text(SCRIPT.replace('__STEM__', STEM).replace('__ZIP_SHA__', zip_sha))
    subprocess.run(['bash', '-n', str(script)], check=True)
    guide = OUT / 'GENOS_PIPELINE_OPTIMIZATION_R2_GUIDE_UTF8.txt'
    guide.write_text(GUIDE)
    receipt = {'zip_sha256': zip_sha, 'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                             for p in (archive, script, guide)},
               'code_manifest_sha256': hashlib.sha256(payload['CODE_MANIFEST.json']).hexdigest(),
               'field_applied': False, 'field_built': False, 'serving_verified': False}
    (OUT / 'HANDOFF.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
