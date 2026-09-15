# GENOS 한 문서 구조화 시간 진단

이 도구는 설치된 파이프라인 함수를 임시로 감싸 시간을 기록한다. 파일을 교체하거나
모델을 호출하지 않는다. 표준 라이브러리 실행기이며 실제 파서는 현장 설치본을 사용한다.
ADR-0343은 진단 도구와 합성 기능 검사 기록이다. 현장 지연/품질은 아직 측정하지 않았다.

메일 첨부 `genos_structure_timing.py.txt`를 `DEV/TRANSFER`에 올린 후 실행한다.
전체 구조화 작업은 먼저 중단하여 다른 실행의 디스크 부하와 겹치지 않게 한다.

```bash
cd /home/genos/DEV
.venv/bin/python -u TRANSFER/genos_structure_timing.py.txt --from-run external-nfs-001 --rebuild
```

`--from-run`은 기존 `01_DATA/LLM/<run-id>`의 문서별 `plan.json`이 정확히 하나일 때
그 문서를 선택한다. 여러 개이면 자동 선택하지 않고 멈춘다. 명시적으로 선택하려면:

```bash
.venv/bin/python -u TRANSFER/genos_structure_timing.py.txt --document 'law/자본시장과 금융투자업에 관한 법률/자본시장과 금융투자업에 관한 법률 본문.xml' --rebuild
```

정확한 상대 경로는 원래 실행 로그/계획에서 확인한다. 여러 파서 버전의 동일 문서 캐시가
발견되면 후보 경로를 표시하고 멈춘다. 이때 표시된 한 경로를 `--cache`에 지정한다.

`--rebuild`는 기존 캐시의 입력 계획으로 한 문서만 신규 진단 폴더에 구조화한다.
옵션을 빼면 기존 캐시 파일 해시 검증만 한다. 누락된 캐시를 자동 생성하지 않는다.
원문 SHA-256이 기존 영수증과 다르면 실패한다. 원문·기존 캐시·LLM 큐를 수정하지 않는다.

기록 구간:

- 코드 import / 캐시 영수증 탐색 / 코드·파서 지문 / 선택 원문 해시
- DOC 변환 / 형식별 파서 / 구조 검사 / JSON 저장
- source SQLite 생성 / LLM 작업 생성 / 최종 캐시 전체 해시 검증
- SQLite 문서·블록·노드·작업 수, 작업 JSON 총 문자 수, SQLite 바이트

각 구간은 START/END와 벽시계·프로세스 CPU 시간을 기록한다. 대기 중 10초마다 WAIT가
나오며, 같은 WAIT 반복은 재실행이 아니다. 종료 집계에는 호출 수·총 시간·하위 계측을
제외한 자체 시간이 나온다. 상위 inclusive 시간에 하위 시간이 포함되므로 단순 합산하지
않는다. CPU 시간 역시 하위 호출 포함이며 프로세스의 모든 스레드를 포함한다. 자식
프로세스(예: LibreOffice) CPU 시간은 포함하지 않는다.

SHA256/JSON 저장은 호출별 화면 출력 대신 누적한다. 코드 버전에 없는 세부 계측점은
UNAVAILABLE로 표시하고 상위 구간 시간에 남긴다. 총 시간에는 계측/로깅 비용도 포함된다.
source_jobs 자체 시간은 source SQLite 하위 구간 등을 제외한 작업 생성·조립 비용이다.
전수 manifest/전체 원본 inventory는 실행하지 않으므로 그 구간은 이 진단 범위 밖이다.
캐시 영수증 탐색은 여러 캐시의 작은 영수증을 읽을 수 있고 시간도 별도로 기록한다.

결과는 매번 새 디렉터리 `01_DATA/LOGS/structure-timing-<고유값>/`에 저장한다.

- `timing.log`: 사람이 읽는 진행·시간
- `timing.jsonl`: 단계 이벤트
- `summary.json`: 상태·시간·코드/원문 지문·집계
- `scratch/`: --rebuild로 새로 만든 해당 문서 결과

Ctrl+C는 INTERRUPTED와 완료 구간 시간을 저장한다. SIGKILL은 종료 요약을 만들 수 없으며
그때까지 기록한 JSONL만 남는다. 읽기/파싱 실패는 FAILED이지 품질 탈락률이 아니다.
캐시 해시 통과는 법적 의미 정확도/원문 파싱 충실도 판정이 아니다.
