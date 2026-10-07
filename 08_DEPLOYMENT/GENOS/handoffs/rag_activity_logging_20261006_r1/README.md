# RAG 행위 로그 인계 R1

RAG 입력·검색·확장 읽기·근거 채택 로그 R1 (2026-10-06)

반입본: GENOS_RAG_ACTIVITY_LOGGING_20261006_R1
기존 RAG control flow R3와 조사 실패 원인 로그를 포함한 누적 코드입니다.
이전 RAG R3 ZIP 대신 이번 GENOS_RAG_ACTIVITY_LOGGING_20261006_R1.zip을 사용합니다.

파일
GENOS_RAG_ACTIVITY_LOGGING_20261006_R1.zip
GENOS_RAG_ACTIVITY_LOGGING_20261006_R1_APPLY.txt
GENOS_RAG_ACTIVITY_LOGGING_20261006_R1_WORKFLOW_PASTE_ALL.txt

로그 변경
에이전트 입력은 핵심 값과 일부 목록으로 짧게 표시하고 출력·행위를 기록합니다.
Fulltext 검색에서 반환한 조·항·호·목 위치를 모두 표시합니다.
확장 읽기 선택의 범위·이유, 실제 읽기 완료·재사용 결과를 각각 표시합니다.
최종 선별에서 실제 채택한 evidence_ids에 해당하는 원문만 근거 채택으로 표시합니다.
묶음 읽기·차집합 READ·다음 후보/참조/읽기 커서 재개를 유지합니다.
데이터의 미해결 참조는 저장된 resolution·해석 사유·문서/조항·참조 ID를 기록합니다.
모델 DEFER/needs_more는 실제 결정과 이유를 기록하며 데이터 상태와 구분합니다.
미처리 메뉴·커서·미스캔 범위와 문맥/횟수/깊이 한도는 실제 사용값과 한도를 기록합니다.
요청 실패에 단계·예외 코드·메시지·발생 파일/행/함수와 모든 중단 사유를 함께 남깁니다.
미평가 근거 현황은 실패 원인과 별도로 표시합니다.
상세 원인이 없는 과거 결과는 '상세 사유 미기록'으로 표시합니다.
화면에서 생략한 상세의 건수와 journal 이벤트 번호를 표시하며 요청 로그에 전체를 남깁니다.
기존 조사 완료 기준·HTTP 종료 동작과 R3 읽기/재개·compact reader·AD를 유지합니다.

현장 적용
ZIP과 실행 TXT를 같은 폴더에 저장합니다.
아래 GENOS_GENERATION은 현재 코드서빙이 선택한 실제 절대경로로 바꿉니다.
기존 checkout ~/DEV에 백업 후 적용하며 각 명령은 시작부터 지속 로그를 남깁니다.
실제 python3 실행 파일과 Python 버전도 기록합니다.

export GENOS_DEV="$HOME/DEV"
export GENOS_GENERATION="/nfs-root/현재_서빙의_실제_generation_절대경로로_교체"
task_script="$(realpath GENOS_RAG_ACTIVITY_LOGGING_20261006_R1_APPLY.txt)"
task_zip="$(realpath GENOS_RAG_ACTIVITY_LOGGING_20261006_R1.zip)"

bash "$task_script" check "$GENOS_GENERATION"
bash "$task_script" apply "$GENOS_GENERATION"
bash "$task_script" verify "$GENOS_GENERATION"

성공 종료 마커: RAG_ACTIVITY_LOGGING_EXIT=0
apply가 출력한 정확한 backup 경로를 보관합니다. 재실행은 적용된 파일을 확인합니다.
알 수 없는 현장 코드/캐시 결속 차이는 기존 파일을 보존하고 중단합니다.

실제 push 대상 checkout에서 검토/commit/gate/push합니다.

cd "$GENOS_DEV"
git diff --check
mapfile -t task_files < <(python3 - "$task_zip" <<'PATHS_PY'
import json,sys,zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    for row in json.loads(z.read('CODE_MANIFEST.json'))['files']:
        print(row['path'])
print('CODE_MANIFEST.json')
PATHS_PY
)
git add -- "${task_files[@]}"
git commit -m "Record precise source investigation and failure causes"
bash "$task_script" gate "$GENOS_GENERATION"
git rev-parse HEAD
git push

게이트가 통과한 commit과 같은 generation을 선택하는 새 코드서빙 리비전을 배포합니다.
이미 R3 워크플로우를 교체했다면 이번 워크플로우 TXT는 동일한 코드입니다.
R3 이전 워크플로우라면 WORKFLOW_PASTE_ALL.txt의 전체 코드로 Python 단계를 교체합니다.
현장 질의 확인은 워크플로우 테스트 화면에서 수행합니다.

새 로그에서 확인할 항목
0. 입력 요약 → 검색된 조·항·호 → 확장 읽기 선택·이유 → 실제 READ/재사용 → 근거 채택
1. SOURCE_INVESTIGATION_INCOMPLETE의 cause_codes와 blockers
2. DATA_REFERENCE면 저장된 resolution·locator·참조 ID·해석 사유
3. MODEL_DECISION이면 실제 모델 결정·이유·적용 판단
4. EXECUTION_LIMIT이면 실제 사용값/한도, UNPROCESSED_WORK이면 미처리 참조/커서
5. ask.failed / RUN_FAILED의 단계·발생 위치와 동일한 세부 사유
6. 화면 요약이 생략한 내용은 해당 journal 이벤트 또는 요청 .log에서 확인

적용/세대 gate/Git push/리비전 배포/워크플로우 적용/실제 질의 성공은 각각 별도 상태입니다.
현재 외부 작업에서는 현장 generation 경로·manifest 해시·push commit·리비전을 확인하지 못했습니다.
로컬 모의 계약 검증을 현장 배포나 데이터 품질 인증으로 표시하지 않습니다.

원복
bash "$task_script" rollback "/apply가_출력한_정확한_backup_절대경로"
배포했다면 이전 코드서빙 리비전과 그때 검증한 generation으로 복귀합니다.
워크플로우를 교체했다면 이전 편집기 코드도 복원합니다.

ZIP SHA-256
956a419489dd8cc3fab57bbef7e6a254b5aa989a76202fe9ce1b05801d890643

외부 검증
ZIP에서 추출한 정확한 코드의 RAG/표시/로그/실패 진단 계약 131개 PASS.
현장 반입·적용·재실행·원복·compact reader/캐시 보존 검사는 DELIVERY_TESTS.xml에 기록합니다.
현장 내부 모델·선택 generation 전체 검증·리비전 배포는 미확인입니다.
추가 모델 호출 없이 로그를 생성합니다.
