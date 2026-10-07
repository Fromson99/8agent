"""Standalone read-only field checker; no checkout application or build interruption."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'08_DEPLOYMENT/GENOS/handoffs/navigation_diagnostic_20261002_r1'
STEM='GENOS_NAVIGATION_DIAGNOSTIC_20261002_R1'
GUIDE='''GENOS navigation 병목 관찰 검사기 R1
진행 중인 R8 구축 터미널은 그대로 두고 새 Terminal에서 실행합니다.
ZIP과 같은 이름 실행 TXT를 ~/DEV/TRANSFER에 함께 올립니다.
  cd ~/DEV
  export GENOS_DIAG_RUN=financial-risk-success-20261002-index-r8
  bash TRANSFER/GENOS_NAVIGATION_DIAGNOSTIC_20261002_R1.txt
R9 실행 중이면 GENOS_DIAG_RUN=financial-risk-success-20261002-index-r9로 지정합니다.
GENOS_DEV 기본 $HOME/DEV / GENOS_DATA_ROOT 기본 $GENOS_DEV/01_DATA.

약 30초 동안 5초마다 7회 관찰합니다. Python3.11 이상 표준 라이브러리만 사용합니다.
같은 사용자/checkout/명시 run의 알려진 build 실행기만 선택합니다. 프로세스 신호/종료 없음.
원본 코드, SQLite, 데이터 generation, CURRENT, 모델 설정을 수정하지 않습니다.
도구 자체와 진단 파일은 LOGS/<선택run>/bottleneck-check/<시각-PID>/에 저장합니다.

LIVE: PID·CPU 사용(core)·프로세스 상태·커널 대기 위치·read/write 카운터 변화.
DB BYTES: navigation 및 journal/WAL 크기 변화.
LAST PHASE / LAST COMPLETED SQL: 기존 로그에서 마지막 완료된 SQL 번호와 실측 시간.
현재 SQL은 마지막 완료 번호와 단계로 추정하며, 스택을 수집하지 않아 확정하지 않습니다.
PID가 없으면 run 설정을 확인합니다. 종료한 작업을 실행 중이라고 보고하지 않습니다.
CPU 1.0 core 전후면 계산 처리 신호, 낮은 CPU와 저장장치 대기는 I/O 병목 후보입니다.
카운터는 NFS 처리속도 실측이 아닙니다. 한 신호만으로 원인을 단정하지 않습니다.

현장 설치 term_links.py의 SQL을 AST로 읽어 빈 메모리 DB에서 실행 계획을 확인합니다.
진행 DB는 조회 전용으로 색인 메타데이터와 SQL9 EXPLAIN만 확인합니다.
SQL9 UPDATE는 실행하지 않습니다. 행수 COUNT/원문 조회/전체 근거 스캔/성능 비교 없음.
ANALYZE, integrity_check, VACUUM, checkpoint, DB 복사, 파일 해시 전체 스캔도 하지 않습니다.
busy timeout 100ms, 조회 0.3초 예산, 하위 진단 프로세스 최대 2초.
읽기 잠금은 잠깐 걸릴 수 있으며, 잠기면 UNAVAILABLE로 생략합니다. 활성 WAL은 조회하지 않습니다.
설치 코드 AST가 예상 구조와 다르면 오류를 진단 파일에 기록하며 구축은 건드리지 않습니다.

파일: run.log / summary.txt / samples.jsonl / report.json /
code-query-plans.json / db-metadata.json. 모든 결과는 GENOS 안에 남깁니다.
외부로 진단 파일을 반출할 필요 없습니다. 마지막 summary와 LIVE 화면 사진으로 확인 가능합니다.
문서 내용·용어 이름·전체 명령행·환경변수 값은 수집하지 않습니다.
선택 경로/run/PID/코드 SHA/SQL 실행계획 등 운영 메타데이터는 기록합니다.

이 도구는 관찰/조회만 수행하며 병목 수정·재구축·서빙 인증은 하지 않습니다.
GENOS 현장 동작은 내부 실행 전까지 미확인입니다.
'''

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    payload={'genos_navigation_diagnose.py':(ROOT/'06_TOOLS/OFFLINE/genos_navigation_diagnose.py').read_bytes(),
             'GUIDE_UTF8.txt':GUIDE.encode()}
    manifest=dict(schema_version='genos-readonly-navigation-diagnostic-v1',files={n:hashlib.sha256(b).hexdigest() for n,b in payload.items()})
    payload['CODE_MANIFEST.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    archive=OUT/(STEM+'.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for n,b in payload.items():z.writestr(n,b)
    sha=hashlib.sha256(archive.read_bytes()).hexdigest()
    script='''#!/usr/bin/env bash
set -Eeuo pipefail
TASK_DEV="${GENOS_DEV:-${HOME}/DEV}"
TASK_DATA="${GENOS_DATA_ROOT:-$TASK_DEV/01_DATA}"
TASK_RUN="${GENOS_DIAG_RUN:-financial-risk-success-20261002-index-r8}"
[[ "$TASK_RUN" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$ ]] || { echo 'Invalid GENOS_DIAG_RUN'; exit 2; }
TASK_LOG="$TASK_DATA/LOGS/$TASK_RUN/bottleneck-check/$(date -u +%Y%m%dT%H%M%S)-${BASHPID}"
mkdir -p "$TASK_LOG"
exec > >(tee -a "$TASK_LOG/run.log") 2>&1
finish() { task_status=$?; printf 'DIAGNOSTIC FINISHED status=%s output=%s\\n' "$task_status" "$TASK_LOG"; }
trap finish EXIT
printf 'DIAGNOSTIC START run=%s output=%s\\n' "$TASK_RUN" "$TASK_LOG"
TASK_ZIP="$(dirname "$(realpath "$0")")/__STEM__.zip"
python3 -u - "$TASK_ZIP" "$TASK_LOG/payload" <<'VERIFY'
import ast,hashlib,json,pathlib,sys,zipfile
if sys.version_info<(3,11):raise SystemExit('Python3.11 or later required')
p=pathlib.Path(sys.argv[1])
if hashlib.file_digest(p.open('rb'),'sha256').hexdigest()!='__SHA__':raise SystemExit('ZIP hash mismatch')
with zipfile.ZipFile(p) as z:
 m=json.loads(z.read('CODE_MANIFEST.json'))
 if len(z.namelist())!=len(set(z.namelist())) or set(z.namelist())!=set(m['files'])|{'CODE_MANIFEST.json'}:raise SystemExit('Inventory mismatch')
 for name,sha in m['files'].items():
  if name not in {'genos_navigation_diagnose.py','GUIDE_UTF8.txt'}:raise SystemExit('Unexpected archive member')
  if hashlib.sha256(z.read(name)).hexdigest()!=sha:raise SystemExit('Member hash mismatch')
  if name.endswith('.py'):ast.parse(z.read(name),feature_version=(3,11))
 z.extractall(sys.argv[2])
print('ARCHIVE VERIFIED; no checkout files applied',flush=True)
VERIFY
python3 -u "$TASK_LOG/payload/genos_navigation_diagnose.py" --dev "$TASK_DEV" --data-root "$TASK_DATA" --run-id "$TASK_RUN" --output "$TASK_LOG" --samples "${GENOS_DIAG_SAMPLES:-7}" --interval "${GENOS_DIAG_INTERVAL:-5}"
'''.replace('__STEM__',STEM).replace('__SHA__',sha)
    runnable=OUT/(STEM+'.txt');runnable.write_text(script)
    subprocess.run(['bash','-n',str(runnable)],check=True)
    guide=OUT/'GENOS_NAVIGATION_DIAGNOSTIC_R1_GUIDE_UTF8.txt';guide.write_text(GUIDE)
    record=dict(files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (archive,runnable,guide)},
                code_manifest_sha256=hashlib.sha256(payload['CODE_MANIFEST.json']).hexdigest(),
                readonly=True,build_interrupted=False,field_execution='unverified')
    (OUT/'HANDOFF.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n');print(json.dumps(record))

if __name__=='__main__':main()
