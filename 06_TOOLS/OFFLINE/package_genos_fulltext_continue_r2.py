"""Freeze a standalone fulltext continuation without replacing GENOS checkout code."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'08_DEPLOYMENT/GENOS/handoffs/fulltext_continue_20261002_r2'
STEM='GENOS_FULLTEXT_CONTINUE_20261002_R2'
GUIDE='''GENOS 완료 navigation 재사용 → 최소 단위 fulltext → 검증 R2

R1 대체본: 완료 입력 위치를 검사한 다음 lock을 열어 경로 없음 오류를 먼저 설명합니다.
동일 run에 대해 GENOS_DATA_ROOT, ~/DEV/01_DATA, /workspace/01_DATA만 대조합니다.
다른 run이나 날짜 최신 파일을 자동 선택하지 않습니다. 별도 root/위치는 아래처럼 명시합니다.
  export GENOS_FT_BASELINE=/실제/완료/run/reindex/baseline
완료본이 없으면 AVAILABLE BASELINE (not selected) 목록과 확인 경로를 출력하고 중단합니다.
그 목록의 실제 완료 run을 GENOS_FT_RUN으로 지정하거나 정확한 baseline 경로를 설정합니다.
경로가 없다고 빈 reindex를 만들어서 넘어가지 않고 navigation을 재구축하지 않습니다.
현재 R8 작업에서 navigation DONE, publish-generation.done, fulltext-index-only START를 확인한 경우에 사용합니다.
R8 터미널에서 Ctrl+C로 현재 fulltext 실행을 종료한 뒤 새 터미널에서 실행하세요.
아직 navigation이 미완료이면 중단하지 마세요. 실행기는 완료 baseline/result.json을 요구합니다.
R8와 동시 실행하면 같은 reindex/.lock을 확인하고 중단합니다. 다른 프로세스를 자동 종료하지 않습니다.

ZIP과 실행 TXT를 ~/DEV/TRANSFER에 함께 올립니다.
cd ~/DEV
export GENOS_FT_RUN=financial-risk-success-20261002-index-r8
bash TRANSFER/GENOS_FULLTEXT_CONTINUE_20261002_R2.txt

기본 GENOS_DEV=$HOME/DEV, GENOS_DATA_ROOT=$GENOS_DEV/01_DATA,
GENOS_FT_SHARED_ROOT=/nfs-root/diamo/8-agent/term-releases,
GENOS_FT_NAME=fulltext-unit-r1, GENOS_FT_WORKERS=2. 로컬 .venv 경로는 사용하지 않습니다.
GENOS_FT_RUN은 완료된 navigation이 있는 출력 run입니다. 준비본 run인 financial-risk-success-20261001-r3가 아닙니다.
workers는 환경의 CPU/메모리에 따라 명시 변경 가능하며 자동 확대하지 않습니다.

입력: $GENOS_DATA_ROOT/TERM_RELEASES/$GENOS_FT_RUN/reindex/baseline/generation
출력: $GENOS_DATA_ROOT/TERM_RELEASES/$GENOS_FT_RUN/reindex/fulltext-unit-r1/fulltext-units
완료 기록: 같은 fulltext-unit-r1/continuation.json
로그: $GENOS_DATA_ROOT/LOGS/$GENOS_FT_RUN/fulltext-continue/<UTC시각-PID>/
run.log, events.jsonl, phases.csv, current.json에 시작부터 종료/실패까지 기록합니다.
해결된 절대 경로와 /proc/self/mountinfo의 실제 mount·filesystem·source를 출력하고 완료 기록에 남깁니다.
현재 사진의 baseline은 /workspace/01_DATA/TERM_RELEASES/financial-risk-success-20261002-index-r8/reindex/baseline입니다.
이 workspace 경로가 NFS인지 mount 정보를 보고 판단합니다. 검증 뒤 공유 NFS 새 경로로 발행합니다.
최종 NFS: /nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261002-index-r8/fulltext-unit-r1/generation
같은 fulltext-unit-r1 아래 links/, audit/navigation/, continuation.json, publication.json도 저장합니다.
공유 루트는 실제 마운트되어 쓰기 가능한 기존 디렉터리여야 합니다. 없으면 먼저 확인하고 생성하세요.
  findmnt -T /nfs-root/diamo/8-agent
  mkdir -p /nfs-root/diamo/8-agent/term-releases
실행 전에 공유 경로/쓰기 권한을 확인하며 접근 불가 시 workspace로 자동 대체하지 않습니다.
기존 운영 문서의 공유 볼륨은 /nfs-root/diamo/8-agent이며 새 run이 거기에 발행됐다는 증거는 없습니다.

범위: 저장된 원문·구조화·문서–용어 연결·navigation 재사용. 용어집 구축/의미검토/번역/LLM 호출/navigation 재구축 없음.
항·호·목 등 저장된 마디에 직접 귀속된 본문을 색인합니다. 부모에 자식 본문을 중복 포함하지 않습니다.
마디 ID가 없는 원문 블록은 블록 ID를 최소 단위로 사용합니다. 구조를 새로 추정하지 않습니다.
기존 reindex/fulltext(조 단위)을 덮어쓰지 않습니다. 본 실행은 별도 도구 payload에서 frozen builder를 명시 호출합니다.
~/DEV 제품 코드·engine pin·generation manifest·CURRENT는 변경하지 않습니다.

순서: 완료 navigation/원문 결속 검사 → 최소 단위 fulltext → 건수·블록 범위·검색 smoke 검증 →
감사 DB 전체 SHA 검증 → 입력/코드 최종 결속 → continuation VERIFIED 기록 →
NFS 새 임시 폴더에 원문/구조/navigation/새 fulltext/연결/감사 복사 → 복사 전체 SHA와 결속 확인 →
완료 폴더로 원자적 이름 변경 → shared-publication VERIFIED 기록.
FTS 처리: 완료/전체 최소 단위 건수·진행률·최근/평균 속도·현재 처리 예상 잔여/종료 UTC.
해시 검증/NFS 복사/NFS 복사 검증: 바이트 완료/전체와 속도 및 예상 잔여를 표시합니다.
약 25.5GB 감사 DB는 결속 검사 1회, NFS 보존 복사 1회, 복사본 확인 1회 전체 읽기를 수행하므로 추가 시간이 필요합니다.
감사를 버리거나 불일치 파일을 성공 처리하지 않습니다. 같은 완료 NFS 출력은 hash 검증 후 재사용합니다.
실패한 NFS 임시 폴더는 .fulltext-unit-r1-...로 보존하고 재실행은 새 임시 폴더로 복사합니다.
5초 heartbeat가 나오며 계수 없는 입력 검사/optimize 구간은 ETA 미측정으로 표시합니다.
30초 이상 진전이 없으면 ETA를 중지합니다. 현재 단계 ETA는 전체 완료 시간과 다릅니다.
실행 중이던 기존 R8의 토큰/부분 FTS를 이 최소 단위 색인으로 전환해 이어 쓰지는 않습니다.
이미 완료된 새 출력은 입력/코드/색인/감사 결속을 재검증하고 재사용합니다.
미완료 새 출력은 .incomplete-<시각-PID>로 보존하고 fulltext만 처음부터 다시 계산합니다.
원자료나 기존 navigation은 삭제하지 않습니다. 다른 입력/코드는 GENOS_FT_NAME=fulltext-unit-r2 등 새 이름을 지정합니다.

Python3.11 이상과 현장 R8의 PeCab/SQLite FTS5 의존성을 사용합니다. 새 설치·외부 통신·모델 호출 없음.
ZIP의 SHA 및 전체 파일 목록·각 SHA·Python3.11 문법을 확인한 뒤 실행합니다.
실제 실행 Python·선택 코드 해시·선택 세대 해시·출력 hash를 현장에 기록합니다.

최소 단위 builder는 ADR-0620의 색인 부분입니다. 이 연구 후보 전체는 MAIN 승인되지 않았습니다.
별도 downstream READ 실험은 실제 문서의 조 경계 검사 실패를 기록했으므로 본 색인 생성 통과로 서빙 성공을 주장하지 않습니다.
이번 검사 범위는 index 생성/검색/원문 및 감사 결속이며 답변 품질/워크플로우 E2E/코드서빙 검증은 별도입니다.
NFS 발행은 수행합니다. 서빙 전환·Git push·코드서빙 배포·활성 포인터 변경은 수행하지 않습니다.
공유 generation은 index 단계 산출물이며 용어집 서빙 자산과 새 unit reader의 배포 검증까지 통과한 serving bundle이 아닙니다.
이 경로를 바로 GENOS_GENERATION으로 전환하지 않고 별도 서빙 결속/E2E 작업에서 선택합니다.
원복: 기존 제품 경로와 포인터를 바꾸지 않아 기존 세대를 계속 선택할 수 있습니다. 새 산출물은 검토용으로 보존합니다.
GENOS 현장 실행/속도/완료는 내부 실행 결과 전까지 미확인입니다.
'''


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    payload={
        'genos_fulltext_continue.py':(ROOT/'06_TOOLS/OFFLINE/genos_fulltext_continue.py').read_bytes(),
        'genos_reindex_logging.py':(ROOT/'06_TOOLS/OFFLINE/genos_reindex_logging.py').read_bytes(),
        'unit_fulltext_selected.py':(ROOT/'02_BACKEND/semantic_runtime/unit_fulltext.py').read_bytes(),
        'GUIDE_UTF8.txt':GUIDE.encode()}
    for name,data in payload.items():
        if name.endswith('.py'):ast.parse(data,feature_version=(3,11))
    manifest={'schema_version':'genos-unit-fulltext-continuation-code-v1','candidate_origin':'ADR-0620 index only; not MAIN promotion',
              'files':{n:hashlib.sha256(b).hexdigest() for n,b in payload.items()}}
    payload['CODE_MANIFEST.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
    archive=OUT/(STEM+'.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for n,b in payload.items():z.writestr(n,b)
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    script='''#!/usr/bin/env bash
set -Eeuo pipefail
TASK_DEV="${GENOS_DEV:-${HOME}/DEV}"
TASK_DATA="${GENOS_DATA_ROOT:-$TASK_DEV/01_DATA}"
TASK_RUN="${GENOS_FT_RUN:-financial-risk-success-20261002-index-r8}"
TASK_NAME="${GENOS_FT_NAME:-fulltext-unit-r1}"
TASK_SHARED="${GENOS_FT_SHARED_ROOT:-/nfs-root/diamo/8-agent/term-releases}"
[[ "$TASK_RUN" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$ ]] || { echo 'Invalid GENOS_FT_RUN'; exit 2; }
[[ "$TASK_NAME" =~ ^fulltext-[A-Za-z0-9_-]+$ ]] || { echo 'Invalid GENOS_FT_NAME'; exit 2; }
TASK_LOG="$TASK_DATA/LOGS/$TASK_RUN/fulltext-continue/$(date -u +%Y%m%dT%H%M%S)-${BASHPID}"
mkdir -p "$TASK_LOG"
exec > >(tee -a "$TASK_LOG/run.log") 2>&1
finish() { task_status=$?; printf 'FULLTEXT CONTINUATION FINISHED status=%s logs=%s\\n' "$task_status" "$TASK_LOG"; }
trap finish EXIT
printf 'FULLTEXT CONTINUATION START run=%s logs=%s\\n' "$TASK_RUN" "$TASK_LOG"
TASK_ZIP="$(dirname "$(realpath "$0")")/__STEM__.zip"
python3 -u - "$TASK_ZIP" "$TASK_LOG/payload" <<'VERIFY'
import ast,hashlib,json,pathlib,sys,zipfile
if sys.version_info<(3,11):raise SystemExit('Python3.11 or later required')
p=pathlib.Path(sys.argv[1])
with p.open('rb') as f:
 if hashlib.file_digest(f,'sha256').hexdigest()!='__SHA__':raise SystemExit('ZIP SHA mismatch')
with zipfile.ZipFile(p) as z:
 m=json.loads(z.read('CODE_MANIFEST.json'))
 allowed={'genos_fulltext_continue.py','genos_reindex_logging.py','unit_fulltext_selected.py','GUIDE_UTF8.txt'}
 if set(m['files'])!=allowed or set(z.namelist())!=allowed|{'CODE_MANIFEST.json'} or len(z.namelist())!=len(set(z.namelist())):raise SystemExit('Archive inventory mismatch')
 for name,expected in m['files'].items():
  data=z.read(name)
  if hashlib.sha256(data).hexdigest()!=expected:raise SystemExit('Member SHA mismatch')
  if name.endswith('.py'):ast.parse(data,feature_version=(3,11))
 z.extractall(sys.argv[2])
print('ARCHIVE VERIFIED; standalone tool; product checkout unchanged',flush=True)
VERIFY
TASK_BASELINE_ARGS=()
if [[ -n "${GENOS_FT_BASELINE:-}" ]]; then TASK_BASELINE_ARGS=(--baseline-override "$GENOS_FT_BASELINE"); fi
python3 -u "$TASK_LOG/payload/genos_fulltext_continue.py" --dev "$TASK_DEV" --baseline "$TASK_DATA/TERM_RELEASES/$TASK_RUN/reindex/baseline" --output "$TASK_DATA/TERM_RELEASES/$TASK_RUN/reindex/$TASK_NAME" --log-dir "$TASK_LOG" --workers "${GENOS_FT_WORKERS:-2}" --shared-root "$TASK_SHARED" --run-id "$TASK_RUN" --data-root "$TASK_DATA" "${TASK_BASELINE_ARGS[@]}"
'''.replace('__STEM__',STEM).replace('__SHA__',digest)
    execution=OUT/(STEM+'.txt');execution.write_text(script)
    guide=OUT/(STEM+'_GUIDE_UTF8.txt');guide.write_text(GUIDE)
    subprocess.run(['bash','-n',str(execution)],check=True)
    with zipfile.ZipFile(archive) as z:
        assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
    record={'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (archive,execution,guide)},
            'code_manifest_sha256':hashlib.sha256(payload['CODE_MANIFEST.json']).hexdigest(),'field_execution':'unverified','activated':False}
    (OUT/'HANDOFF.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n');print(json.dumps(record))

if __name__=='__main__':main()
