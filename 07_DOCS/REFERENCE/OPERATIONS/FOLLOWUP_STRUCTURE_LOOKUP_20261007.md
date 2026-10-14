# 후속 구조 조회와 명시 조문 원문 읽기

2026-10-07 사용자 사진에서 자본시장법 제6조 「금융투자업」을 찾는 동안
`NEXT_ARTICLES`로 별표·부칙 후보를 반복 탐색하고 제370조를 읽는 흐름이 보였다.
사진에는 현장 배포 리비전·선택 generation·실제 도구 인수가 없으므로 현장 원인을
하나로 확정하지 않는다. 현장 서비스에 접근하거나 내부 질문을 외부 모델에 보내지 않았다.

2026-10-07 작업 코드의 후속 조사에 저장된 구조를 직접 조회하는 도구를 연결했다. 초기
수정은 일반 코드 수정과 모의 계약 검사였다. 이후 2026-10-08 세 항목 통합 감사와
보조 모델 실험은 아래 ADR-0688 기록을 따른다.

## 실행 연결

기존 `service.py → /v1/rag/ask → legal-agent-unified-v6 → SourceRecall →
law_navigation.Investigation`을 사용한다. 별도 검색 실행기나 데이터 색인을 만들지 않는다.

- `SEARCH_STRUCTURE`: 허용 문서 전체 또는 제시된 법령 안에서 법령명·약칭·조문 번호·
  저장 제목을 조회한다. 법령을 선택한 도구에서는 `제6조`만으로도 조회할 수 있다.
- `OPEN_STRUCTURE` / `NEXT_STRUCTURE`: 해당 법령의 본문 조문 목차를 저장 순서로
  페이지 조회한다. fulltext에 적중하지 않은 조문도 제공한다.
- 조회 결과의 `READ_ARTICLES`: 해당 조·항·호의 subtree 전체를 기존 원문 읽기로
  확보한다. 빈 도입 마디는 실제 자식 본문에서 시작하되 요청한 subtree를 유지한다.
- `READ_PARENT`: 긴 원문은 기존 페이지와 정확한 span으로 계속 전달한다. 읽기와
  채택은 구분하며 자동 채택하지 않는다. 원문 해시·권한·scope·저장·복귀·재개를 유지한다.

조회 결과는 `structure_catalogue`이고 `navigation_hint_only=true`,
`citation_eligible=false`다. 위치·목차를 본문 근거로 쓰지 않는다. 같은 본문 좌표가
중복되거나 원문 결속이 유일하지 않으면 실행할 READ를 제공하지 않는다. 이름 없는
조문 번호의 여러 법령 후보는 명시 문서–조문 일치로 승인하지 않는다. 부칙·별표·범위
질문을 본문 제6조로 치환하지 않는다. 현재 도구의 본문 목차 외 범위는 기존 탐색과
명시 참조 도구를 사용한다.

새 fulltext 재검색어에 명시 문서–조문 쌍이 있으면 그 구조 위치도 독립적으로 보존한다.
구조 조회는 fulltext 재검색 횟수를 쓰지 않으며, 기존 설정의 search_rounds를 별도의
구조 조회 한도로 사용한다. 전체 요청·모델·도구 예산은 그대로 적용된다.

## 이름과 선택 세대

`ReverseMatcher`가 저장된 `document_role`·`raw_role`도 보존한다. 본문 법령명 조회에서
동일 법령명을 달고 등록된 별표/서식 문서를 본문 법령으로 함께 해소하지 않는다.
여러 실제 본문 판본의 모호함은 계속 보존한다. 별칭을 모델 추측으로 새로 만들지 않는다.

로컬 선택 generation `term-source-3b667f54bb11d9477888`의 기존 약칭 projection은
26문서를 포함한다. 약칭 파일은 존재했지만 작업 코드 및 MAIN45의 frozen PIPELINE에는
이전 두 세대의 약칭만 연결돼 있었다. 작업 PIPELINE의 기존 8개 문서 탐색 설정에
현재 세대의 약칭 파일과 SHA를 추가했다. `document_aliases.load`의 generation/store/
projection SHA 검증을 그대로 사용한다. GENOS에서는 해당 현장 세대에 저장된 XML
`official_abbreviation` 또는 정확히 결속된 projection이 필요하다.

선택된 로컬 원문·navigation의 실제 파일 SHA를 확인한 뒤 작업 reader에서
`자본시장법 제6조`를 조회했다. 본문 문서 `5be4de51a89dc664`, unit `59`,
source `article:742307f0f2c891e2e8e9a49c`, 제목 「금융투자업」으로 유일하게 해소됐다.
본문은 38블록·2,387자이며 모델 및 fulltext 호출은 0회다.
[확인 기록](../../../../09_ARTIFACTS/AUDITS/20261007-followup-structure-lookup/LOCAL_SOURCE_CHECK.json).

## 전체 원문과 문맥

원문을 주지 않는 정책이 아니다. 법률 전문 전체를 한 모델 입력에 넣는 대신 필요한
조·항·호의 원문을 읽고 정확한 블록/span으로 전달한다. v6 작업 프로필의 읽기 페이지는
12,000자, 전체 context 한도는 100,000자다. 위 제6조는 한 읽기 페이지보다 작다.
이전 bounded 구조 선별에서는 준비한 전체 JSON이 문맥 예산보다 크면
`STRUCTURE_CONTEXT_LIMIT`를 남기고 fulltext 확장으로 넘어가는 경로도 있다.
이번 구조 도구는 조문 subtree를 기존 페이지 읽기로 전달한다. 전체 법률 전문을
한꺼번에 모델에 넣도록 바꾸거나 문맥 한도를 제거하지 않았다.

## 검증과 적용 상태

새 도구 계약 15개에서 구조 조회·본문 역할·좌표 중복·권한·목차 페이지·재개/복귀·
긴 원문 전체 페이지·빈 도입 마디·후속 검색 좌표·모의 native API의 답변 게시를 확인했다.
관련 기존 계약61개도 통과했으며 제외한18개의 과거 검사와 통합 지문은
[검증 기록](../../../../09_ARTIFACTS/AUDITS/20261007-followup-structure-lookup/VALIDATION.json)에 남긴다.
넓은 과거 검사에는 응답 fixture의 채택 status 누락, bounded proposal 계약 불일치,
WORKSPACE activation receipt SHA 불일치가 있어 전체 통과로 보고하지 않는다.

변경한 런타임 파일의 기존 엔진 선언 30개와 PIPELINE 해시를 함께 재결속한다.
전체 preflight의 별도 `nfs_data_probe.py` 변경/pin 불일치는 이 수정 범위에서 덮어쓰지 않는다.
실제 내부 모델의 도구 선택 품질·현장 원문 존재·현장 배포·워크플로우 성공은 미확인이다.

작업 코드와 설정을 수정했으며 로컬 MAIN45 포인터·frozen release·원문 세대·CURRENT는
전환하지 않았다. GENOS 반입 때는 기존 checkout에 이 런타임과 엔진/PIPELINE의 정확한
결속을 함께 적용·검증하고, commit/push 후 새 코드서빙 리비전을 배포한다. 질의 검증은
워크플로우 테스트 화면에서 수행한다. 이 도구 변경만을 위해 원문 재구축이나 워크플로우
Python 수정이 필요한 것은 아니다. 실제 현장 명령은 `python3`를 사용한다.
원복은 변경 전 코드·엔진/PIPELINE과 이전 코드서빙 리비전으로 함께 복귀한다.

## 2026-10-08 현재 문서 구조와 필드 조회 보완

사용자 정정의 핵심은 법률 전문 제공량이 아니라 현재 문서의 형태를 제시하고 제6조로
바로 이동하는 것이다. 이전 조문 목록 도구에 더해 v6 후속 조사 모델의 각 법령 카드에
`document_structure`를 연결했다. fulltext 후보·법령 창·구조 조회·원문 읽기 창에서
해당 문서의 실제 계층 종류, 번호 표기 예시, 본문/부칙 등의 저장 분기, 현재 상위 경로와
직계 하위 항목을 제공한다. 이 값은 현재 generation의 `source_unit`과 parent 관계로
만들며, 원문 본문이나 임의로 만든 표준 계층을 넣지 않는다. 불변 세대의 문서별 구조
요약은 기존 prepared_structure 캐시에 결속해 재사용한다.

- `BROWSE_STRUCTURE`: 제시된 위치의 직계 하위 항목, 상위 또는 문서 루트로 이동한다.
  하위 항목이 많으면 같은 노드의 다음 구조 페이지를 제공한다.
- 법령 카드의 `SEARCH_STRUCTURE`는 `structure_filter`로 `coordinate`, `title`,
  `coordinate_scope`를 받는다. 현재 문서를 바인딩한 target에서
  `{"coordinate":"제6조","title":"","coordinate_scope":"body"}`로 직접 조회한다.
  이때 `queries=[]`다. 제목도 지정하면 두 조건을 모두 만족해야 한다. scope가 비면
  body를 사용하며 부칙 제6조를 암묵적으로 대신 선택하지 않는다.
- 편·장·절 등의 조회 결과는 그 위치를 열어 하위 구조를 탐색할 수 있다. 원문 읽기는
  기존의 유일한 본문 조·항·호 좌표/source 바인딩을 통과한 항목에만 제공한다.
- 조회 실패는 빈 결과와 이유를 보존하고 현재 문서·위치·구조와 재조회 도구를 유지한다.
  fulltext로 자동 전환하지 않는다. `RESEARCH`는 모델이 별도로 선택하는 본문 검색이다.
- 구조 위치·페이지와 필드 조회 기록도 SQL 재개·RETURN_TO·완료 progress 계약에
  포함한다. 목차/구조를 읽은 것만으로 본문 열람·채택·인용이 되지 않는다.

같은 로컬 원문과 navigation 파일의 SHA를 확인하고 공개 법령 한 문서의 실제 저장
행만 읽는 점검에서 `자본시장법 제6조` 및 위 필드 조회가 `unit 59`의 「금융투자업」으로
해소됐다. 실제 경로는 `제1편 총칙 → 제6조 금융투자업`이며 직계 하위 항목은 10개다.
조문 페이지를 순서대로 넘기거나 모델/fulltext를 호출하지 않았다. 실서비스의 모델 선택
성능을 평가한 결과는 아니다.
[원문 구조 확인과 재현 스크립트](../../../../09_ARTIFACTS/AUDITS/20261008-document-structure-navigation/LOCAL_SOURCE_CHECK.json).

후속 구조 계약27개(모의 native API의 문자열/필드 조회와 원문 게시 포함), 관련 기존
계약61개가 통과했다. 이전 검사18개 제외와 별도 `nfs_data_probe.py` 엔진 pin 불일치는
유지·기록한다. 변경한 런타임4개와 기존 엔진30개/PIPELINE만 새 코드 SHA로 재결속했다.
[검증 및 코드/데이터/선택 릴리스 지문](../../../../09_ARTIFACTS/AUDITS/20261008-document-structure-navigation/VALIDATION.json).
이는 작업 코드 통합 상태다. 로컬 MAIN45의 frozen release/활성 포인터와 GENOS 현장
리비전을 교체하지 않았다. 새 데이터 재구축 없이 기존 v6 조회/선택/READ 경로를 사용한다.

## 2026-10-08 세 항목 수정·고정 코드 감사 (ADR-0688)

1. 구조 조회의 번호·제목·분기, 조회 결과·실패 원인, 현재 경로를 행동 이력·재개·복귀·
   진행 이벤트와 GENOS workflow 표시 소비자에 연결했다. 목차는 계속 탐색용이며 원문
   열람·근거 채택으로 표시하지 않는다. 진행 표시는 허용 문서에 결속한다.
2. 같은 문서·정규화 검색식에서 새 원문 없이 Fulltext 페이지 행동3회가 되면 해당
   문서의 추가 페이지 행동을 숨기고 번호·제목 조회/목차/현재 READ를 제공한다. 과거
   메뉴 복귀도 우회하지 못한다. 실제 새 원문 span을 전달하면 초기화하며 같은 내용의
   재전달, 다른 문서·검색식은 별도로 처리한다. 저장 구조가 없는 문서는 제한하지 않고
   그 이유를 표시한다.
3. 문서 없음/모호, 좌표 없음/중복/형식 오류/결속 미해결, 제목·분기 불일치, 원문
   없음/중복을 구분한다. 실패의 설명과 다음 탐색 방법을 제공하고 현재 목차를 유지한다.
   실패 후 문서·분기를 임의 치환하거나 Fulltext로 자동 전환하지 않는다.

[ADR-0688 사전 기준·실제 결과](../../../../04_EXPERIMENTS/ADR/ADR-0688-followup-structure-observability-recovery/README.md):
동결 후보 신규18개와 기존88개 검사106개 통과. 정확히 같은6개 수정 파일을 현재 작업
코드에 통합한 뒤 소비자·native API 포함45개를 다시 확인했다. 모델 보조 실험은 합성
4시나리오×2arm, Qwen3.8 / Parasail FP8 / reasoning none / fallback 없음8호출이다.
3시나리오는 양쪽 모두 원문 전달 성공, 조문 부재 사례는 양쪽 모두 upstream
finish_reason=error/content=null로 확인 불가였다. 실패 응답과 미보고 비용·usage를
보존했으며 성공이나 품질 개선으로 계산하지 않았다. 실제 로컬 자본시장법 제6조는
동결 후보에서 Fulltext 없이 unit59 / 제1편→제6조 / 금융투자업을 직접 해소했다.

작업 코드 통합 완료. 선택 MAIN45/generation45와 GENOS 배포는 변경하지 않았다.
활성화 receipt drift와 구 엔진의 nfs_data_probe pin 차이는 별도 기존 문제다.

ADR-0688 자체 `validate --final`은 통과했다. 전역 graph 생성 검사는 다른 과거 ADR의
기존 오류8개 때문에 exit1이며 전체 계보 통과로 보고하지 않는다. 해당 기록은
[graph 검사 영수증](../../../../04_EXPERIMENTS/ADR/ADR-0688-followup-structure-observability-recovery/artifacts/graph-check.json)에 보존한다.
