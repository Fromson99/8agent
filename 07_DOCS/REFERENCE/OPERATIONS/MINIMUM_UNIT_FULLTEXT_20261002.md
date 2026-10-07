# 구조 최소 단위 fulltext — 작업 코드, 2026-10-02

완료된 구조화와 navigation을 재사용하여 fulltext만 다시 만드는 경로다.
GENOS의 실행 중인 R8/R9 코드, 활성 릴리스와 NFS 포인터에는 아직 적용되지 않았다.

## 입력과 색인 단위

입력은 명시한 generation의 `store.sqlite`, `manifest.json`, navigation DB/manifest다.
`source_block.unit_id`에 이미 기록된 소유 구조 ID로 블록을 묶는다. 항·호·목을 다시 파싱하지 않는다.
각 구조가 직접 소유하는 본문만 색인한다. 상위 구조의 전체 하위 본문을 반복 색인하지 않는다.
조/항/호의 도입 본문도 자체 소유 블록이 있으면 별도 검색 대상이다.
소유 구조가 없는 블록은 블록 단위로 보존하고 `unit_id=null`을 남긴다.
항·호·목이 입력에 없다면 이 단계가 새 구조를 만들어 주지는 않는다.
제목은 위치 메타데이터이며 FTS 본문에는 넣지 않는다. PeCab 형태소, OR 검색, BM25 순위를 사용한다.

출력은 `semantic-unit-fulltext-v1` manifest와 `units.sqlite`다.
실제 hit에는 문서 ID, 조 ID, 실제 구조 ID, 소유 블록 ID와 점수가 있다.
`fulltext.open_index/open_bound/cached_open_bound`가 manifest의 명시 schema로 reader를 선택한다.
기존 `semantic-fulltext-v2` 조 단위 색인은 계속 읽을 수 있다.
기존 조 ID 소비자는 `rank()`의 조 ID 투영을 쓰고, 단위 소비자는 `rank_units()`를 쓴다.
워크플로우 탐색 도구의 fulltext 검색은 실제 구조 위치와 그 단위의 `read` 실행안을 반환한다.
형제나 부모의 본문을 기본 hit에 합치지 않는다. 상위 문맥을 언제 추가로 읽을지는 별도 정책이다.
다른 작업의 ADR-0620 후보 snapshot/동결 파일이나 모델 선택 실험은 이 변경으로 수정하지 않는다.

## fulltext만 다시 실행

WSL 로컬:

```bash
.venv/bin/python 06_TOOLS/pipeline.py fulltext \
  --generation /절대경로/완료된/generation \
  --output /절대경로/새로운/unit-generation \
  --granularity unit --workers 2
```

GENOS에는 검증한 코드 반입 후 `~/DEV`에서 위 명령의 Python을 `python3`로 바꿔 실행한다.
기존 R8의 완료된 입력 예시는
`~/DEV/01_DATA/TERM_RELEASES/financial-risk-success-20261002-index-r8/reindex/baseline/generation`이다.
실제 데이터 root를 변경했다면 해당 root의 완료된 generation을 지정한다.
`publish-generation.done` 이전 임시 generation이나 파일명 기준 최신 폴더를 입력으로 선택하지 않는다.

출력은 부모와 다른 디렉터리여야 한다. 구조화·연결·용어집·navigation을 재구축하지 않는다.
새 generation에 기존 source/navigation을 복제하고 fulltext binding과 부모 manifest SHA만 연결한다.
원본을 삭제하거나 CURRENT를 변경하지 않는다. 별도 audit는 기존 부모 build에 보존한다.
이 산출물만으로 release 전체 감사 검증이나 서빙 활성화가 완료된 것은 아니다.
기존 외부 fulltext profile pin이 있으면 새 manifest SHA를 명시적으로 선택하는 인계가 별도로 필요하다.

같은 입력/코드/설정과 같은 출력으로 재실행하면 완료 산출물의 해시를 검증해 재사용한다.
입력이나 코드가 바뀌었으면 새 출력 디렉터리를 사용한다. 실패한 임시 출력은 진단용으로 보존한다.
기존 자료는 자동 삭제하지 않는다. 롤백은 이전 generation/binding을 다시 선택하는 방식이다.

## 로그와 완료 확인

기본 로그 위치는 출력의 형제 디렉터리 `<출력명>.logs`다. `--log-dir`로 따로 지정할 수 있다.
`build.log`에는 stdout/stderr, `progress.jsonl`에는 시각·단계·건수·상태를 기록한다.
5초마다 진행 상태를 출력한다. 색인 단위 총수와 완료 수, 실측 평균 속도로 계산한 잔여 초를 표시한다.
최적화/검증처럼 총 작업량을 측정하지 않은 단계는 `not_measured`로 표시한다.
잔여 시간은 현재 색인 단계의 추정이며 이후 검증 시간까지 보장하는 전체 종료 시각이 아니다.
완료는 `FULLTEXT_STAGE VERIFIED`, 마지막 `FINISHED`, 출력의 `fulltext-stage.json.completed=true`를 함께 확인한다.
실패는 traceback과 `FAILED`를 파일에도 남긴다. 단순 heartbeat만으로 성공을 판단하지 않는다.

전체 native 생성에서도 `term_generation.build_generation(..., serving=True, fulltext_granularity='unit')`를 명시할 수 있다.
기존 호출의 기본값은 article로 유지하여 기존 준비본/조 색인 실행 계약을 보존한다.
standalone `semantic_runtime ... build-fulltext`에도 `--granularity unit --generation PATH`를 연결했지만,
generation manifest까지 결속하려면 위 `pipeline.py fulltext` 경로를 사용한다.

## 확인 범위

모의 구조 입력으로 실제 CLI, 병렬 토큰화, 전량 블록 커버리지, 완료 재사용,
입력/출력 변조 거부, 문서 범위 제한, 실제 워크플로우 검색→목 단위 읽기,
기존 조 단위 검색과 navigation 재사용을 계약 검사한다.
GENOS 내부 실제 자료의 구조 품질, 실제 처리 시간과 최종 서빙 배포는 현장 확인 전 미확인이다.
로컬 엔진 파일 pin 갱신 내역은 동명 `.pins.json`에 남겼으며 데이터 활성 선택을 변경하지 않았다.

## 법령별 탐색 소비자 (2026-10-06 작업 코드)

v6의 `candidate_navigation.mode=law-first-v1`은 명시 선택한 소유 본문 색인을 법령 판본→조→적중 단위로 페이지 조회한다. 최소 저장 단위는 유지하고 선택 후 READ만 부모·형제 subtree와 상위 도입문으로 넓힌다. 기존 unit 색인을 재생성하거나 원문/navigation을 변경할 필요는 없다. 사용자 후속 지시에 따라 필수 연결 미해결도 답변 완료를 허용하며 미해결 상태와 경고는 보존한다. [설정·실행 경로·재개·검증](../REPORTS/LAW_GROUPED_NAVIGATION_DESIGN_20261006/IMPLEMENTATION.md)을 따른다. 작업 코드 프로필과 frozen MAIN/GENOS 적용 상태는 구분한다.
