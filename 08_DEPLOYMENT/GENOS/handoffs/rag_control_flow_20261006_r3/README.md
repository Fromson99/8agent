# RAG 적중 단위 조사 루프 수정 및 GENOS 인계 R3

감사 F01~F12와 coverage 반복 처리를 수정했다. 기본 단위는 검색에 걸린 최소 구조화 단위다. 미리보기 → 선택 → 필요한 범위만 읽기 → 새 근거로 충분성 확인을 유지한다. 실제 적용 필수 조건이 미확보되면 충분하다고 종료하지 않는다.

최종 발송본은 **GENOS_RAG_CONTROL_FLOW_20261006_R3**다. 코드 ZIP은 progressive reading R1의 정확한 바이트에 열거한 15개 파일의 수정을 반영했다. 기존 compact 용어집 reader·AD R2·판단 표시를 보존한다. R1/R2는 발송하지 않은 중간 검증본이다.

| 감사 | 반영 내용 | 검증 |
| --- | --- | --- |
| F01 | 연결 그룹 큐 및 reference ID 커서. 연결 계속하기와 신규 검색 분리 | 20개 메뉴 분할·reference SQL 다음 페이지·pending 시 재검색 거부 |
| F02 | 채택 span이 바뀌면 확장 원문 제시 후 충분성 재검토 | 새 일반 제한을 두 번째 review에서 확인 |
| F03 | source ID 대신 검증한 span fingerprint로 스캔 상태 관리 | 이미 스캔한 원문의 확장에서 신규 필수 연결 확인·읽기 |
| F04 | 현재 deferred/unresolved 집합으로 보류 계산 | 첫 pending 이후 해소된 탐색의 완료 확인 |
| F05 | 세션 읽기 예산 및 단조 증가 action sequence 유지 | 동일 세션 재진입에서 ID 충돌 및 예산 초기화 방지 |
| F06 | 질문·witness·정책·끝점에 결속한 결정 재사용 | 같은 탐색 연속 실행에서 기존 판단 재호출 없음 |
| F07 | 검증된 기존 구간 투영·재사용과 문자 구간 차집합 READ | 1페이지 읽은 뒤 전체 4블록 확장은 신규 3페이지만 읽음; 부분 블록 이어읽기 |
| F08 | source별 추가 묶음 round-robin | A1·B1·A2 순서 유지 |
| F09 | 신규 미리보기 우선, 이전 채택 상태 유지, 실제 표시 행만 선택 스키마에 제공 | 문맥 경계에서 다음 후보 제시 및 전체 묶음 감사 기록 보존 |
| F10 | 초기 그룹 크기는 exact 메타데이터만 계산, offer/문자 길이 캐시 | 미열람 후보의 상위 범위 미계산 |
| F11 | SELECT의 timeout을 RuntimeModel까지 전달 | 실제 전달 제한 시간 확인 |
| F12 | 질문·상태·코드·세대·READ 입력에 결속한 내부 진행 및 페이지 근거 저장 | JSON 직렬화 뒤 수락한 FOLLOW 재개; 실제 새 HTTP 세션 재시도에서 triage/연결 판단 재호출 없음 |
| 추가 | 페이지별 coverage 구간 합집합을 점진 갱신 | 기존 완료/부분 범위·canonical 경계 검사 |
| 추가 | 워크플로우 AD 필드를 API/서명 계약과 일치시킴 | 워크플로우→service 정규화→서명 검증 및 AD 계약 |

발송 ZIP에서 복원한 코드에서 RAG·도구·숏컷·AD 관련 계약 **169개 PASS**, 적용·재실행·원복·변조 거부 및 Git/ZIP/generation 게이트 모의 검사 **16개 PASS**다. 13개 알려진 predecessor 상태를 다뤘다. Python 3.11 문법과 실행 TXT bash 문법을 확인했고 ZIP의 JavaScript 멤버는 0개다. 근거는 `CANDIDATE_TESTS.xml`, `DELIVERY_TESTS.xml`, `HANDOFF.json`이다.

기존 v3 관리 API/응답 형식·AD 진입 전 관리 허용을 가정한 과거 전체 검사와 현재 숏컷 v4/AD 계약의 차이는 중간 R1 로그에 보존했다. 최종 169개는 이번 변경 실행 경로·현재 도구/AD 계약·숏컷 확정/재사용·중단 재개를 검증한 범위이며 저장소 전체 테스트 통과를 뜻하지 않는다. 외부 LLM 지연·정답 품질 비교 실험을 실시하지 않았다.

원래 감사 보고서와 결함 재현 기록은 변경하지 않았다. 상세 실행 및 원복은 [GUIDE_UTF8.txt](GUIDE_UTF8.txt)를 따른다. 현장에서는 기존 `~/DEV`에 backup/apply하고 실제 generation으로 verify, commit 후 gate, push, 코드서빙 리비전 배포, 워크플로우 편집기 전체 교체, 워크플로우 테스트 질의를 별도로 확인한다.

기존 NFS generation/캐시/CURRENT와 로컬 frozen MAIN을 변경하지 않았다. 실제 GENOS generation·commit·코드서빙 리비전·내부 모델 응답 시간은 미확인이다. 반입 ZIP 검증을 현장 배포 성공으로 보고하지 않는다.
