# 현재 상태와 관측 근거

[v4 목차](../ONTOLOGY_V4.md) · [프로토타입 구현](PROTOTYPE_DESIGN.md)

2026-10-23 코드·문서 확인 기준이다. v4는 새 설계이며, 아래 기존 구현의 존재와 기본 활성화를 구분한다. 제품 코드·선택 포인터·완료 실험·v3는 이번 문서 작업에서 수정하지 않는다.

## 선택된 실행과 작업 코드

| 구분 | 확인한 값·상태 |
|---|---|
| 로컬 활성 포인터 | [ACTIVE_RELEASE.json](../../../../01_DATA/ACTIVE/local/ACTIVE_RELEASE.json): generation 103 |
| 선택 릴리스 | output-unlimited-20261023-r1, 코드 목록 420개 |
| manifest | [release.json](../../../../08_DEPLOYMENT/RELEASES/output-unlimited-20261023-r1/release.json); 포인터의 SHA-256과 일치 확인 |
| 선택 데이터 | 01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation; manifest에 결속된 경로이며 이번 작업에서 재구축하지 않음 |
| 품질 상태 | USER_DIRECTED_CUTOVER, quality_certified=false; v4나 읽기 판단 실험의 품질 통과를 뜻하지 않음 |
| 지식 기능 설정 | 작업 코드와 선택 릴리스 모두 management_enabled=false, consumer_mode=off |
| AD 설정 | ad_management.enabled=false. 독립 지식 관리 router와 AD 채팅은 별도 기능 |
| GENOS | 접근·활성화·현장 연결 확인 없음 |

[EVIDENCE.json](EVIDENCE.json)에 확인한 18개 경로의 작업/선택 코드 hash와 문서 근거, v3 16개 파일의 보존 기준을 저장했다. 이는 전체 작업 트리의 기능 동등성 검사나 서비스 실측이 아니다. request_entry·judgment_view·read_judgment·PIPELINE은 작업 코드와 선택 릴리스가 다르다. legal_knowledge의 주요 service·계약·계산기·router·viewer, corrected_memory, basis_links의 확인한 파일은 동일하다. 동일 파일이 있다는 것만으로 해당 기능이 활성 상태가 되지는 않는다.

## 현재 실행 경로

[service.py](../../../../service.py)의 RAG_ASK에서 /v1/rag/ask의 native legal_agent로 들어간다. [request_entry.py](../../../../02_BACKEND/semantic_runtime/legal_agent/request_entry.py)의 prepare/augment 연결은 [knowledge_bridge.py](../../../../02_BACKEND/semantic_runtime/legal_agent/knowledge_bridge.py)를 호출한다.

knowledge_bridge.prepare는 mode가 off이면 지식 조회를 소비하지 않는다. 켜더라도 인증 주체, 승인된 factory, 원문 결속이 필요하다. 현재 호출은 Service.plan에 query와 source binding을 전달하며, facts·context·as_of를 넘기지 않는다. augment는 안내 지식을 legal_review_guidance로 전달한다. 반환 단계 목록을 코드가 실행하는 컴파일러가 아니다.

따라서 현재 설정을 켜는 일만으로 대화에서 축적한 온톨로지가 현재 사건의 조건을 계산하고 경로를 자동 실행하게 되지는 않는다. 지식 회수와 실제 실행 계획 소비 사이의 연결을 추가해야 한다.

사용자 추가 요구에 따라 조문 도착 경로도 확인했다. unit_reading.read의 검증된 원문 반환, law_navigation.Investigation의 읽기 상태/관계 화면, unit_relations.catalog의 근거 있는 READ 선택지, relations_tools의 기존 관계 큐를 새 경로의 연결 지점으로 삼는다. 기존 기능을 합쳐 목적별 경로를 컴파일하고 동일 계획에서 설명·원문 묶음을 제공하는 전체 소비 경로는 아직 미구현이다. [추가 코드 지문](SOURCE_ENTRY_EVIDENCE.json)의 5개 경로는 초기 EVIDENCE.json과 별도이며 law_navigation·unit_relations는 작업/선택 코드가 다르다. [구체 변경 지도](SOURCE_ENTRY_COMPOSITION.md)를 따른다.

## 기존 기능의 활용 범위

| 확인한 코드 | 현재 제공하는 기능 | v4에 필요한 확장 |
|---|---|---|
| [judgment_view.build](../../../../02_BACKEND/semantic_runtime/legal_agent/judgment_view.py) | 현재 head·허용 원문을 투영, 단계별 판단·이유·출처와 실행/재사용 표시. 작업 코드에는 읽기 판단 원장 연결 | 실제 사용자 표시 이벤트·정정 대상·전후 그래프 결속 |
| [corrected_memory.Memory](../../../../02_BACKEND/semantic_runtime/legal_agent/corrected_memory.py) | 질문·범위·facts·제시 방식 변경, 사건 revision·변경 이벤트·재진입 | 원문/지식 객체를 정확히 고치는 typed 변경 명령과 시나리오 분리 |
| [basis_links.service](../../../../02_BACKEND/semantic_runtime/basis_links/service.py) | 원문 연결 제안·새 revision·검토 승인/반려/철회, expected revision/view hash | 다양한 의미 관계와의 정본 소유권·참조 연결 |
| [basis_links.chat](../../../../02_BACKEND/semantic_runtime/basis_links/chat.py) | AD의 명시적 목록·번호 승인/반려/취소, 표시 목록 결속 | 자유 대화에서 임의 온톨로지 정정을 수행하는 기능과 구분 |
| [legal_knowledge.Service](../../../../02_BACKEND/lawrag/legal_knowledge/application/__init__.py) | 초안·의존 검증·검토 기록·게시·롤백·feedback 후보 | 대화 후보 생산·정정 변환·시나리오 및 실행 소비 연결 |
| Service.impact | 현재 게시 묶음에서 참조 ID의 직접 의존 검사. scope= CURRENT_RELEASE_DIRECT_DEPENDENCIES | 여러 단계의 역의존, 정확한 revision별 사용 영향, 재계산 |
| [planning.assemble](../../../../02_BACKEND/lawrag/legal_knowledge/application/planning.py) | 범위·시점·조건·부족 입력을 포함한 안내 계획 | typed 입력/출력·실제 도구·실행 receipt를 갖는 계획 |
| [ontology.evaluate](../../../../02_BACKEND/lawrag/legal_knowledge/ontology/__init__.py) | 제한된 연산·타입·단위 검사, TRUE/FALSE/VALUE/UNKNOWN/CONFLICT | 검토된 원문 값 및 사건 입력의 안정된 결속, 그래프 결과 소비 |
| [관리 router](../../../../02_BACKEND/lawrag/api/routers/legal_knowledge.py)와 [viewer](../../../../02_BACKEND/lawrag/api/viewer/legal_knowledge/app.js) | 객체·초안·게시·feedback·직접 영향·안내 preview | 판단에서 정정하는 UI, 시나리오·전후 그래프 |

[contracts.py](../../../../02_BACKEND/lawrag/legal_knowledge/contracts.py)는 FIELD, METHOD, APPLICATION, WIKI_LINK, SHORTCUT_LINK의 다섯 kind를 지원한다. REF는 기존 CONCEPT·DEFINITION 등을 참조할 수 있다. STEP은 id·label·capability·after이며 노드별 실행 입출력 계약은 없다. FIELD는 값의 타입·단위 차원·목적을 정의하지만 독립적인 원문 기본값 객체를 제공하지 않는다.

현재 _feedback은 원래 요청이 검증된 사실인지 확인되지 않은 PROPOSED 후보를 저장한다. 피드백을 받았다고 지식이 자동 수정·게시되는 것은 아니다. _prepare_publication의 사람 검토 기록도 법률 정답 인증이 아니다.

[repository](../../../../02_BACKEND/lawrag/legal_knowledge/adapters/repository.py)는 불변 revision과 head/CAS를, [Oracle 어댑터](../../../../02_BACKEND/lawrag/legal_knowledge/adapters/oracle.py)는 주입된 연결·테이블 매핑을 사용한다. 실제 Oracle 연결/운영 테이블 생성이 완료됐다는 근거는 이 코드에 없다. 기존 로컬 case journal을 GENOS의 목표 저장 방식으로 삼지 않는다.

## 최근 실제 실패가 보여주는 요구

[ADR-1037 결과](../../../../04_EXPERIMENTS/ADR/ADR-1037-uncapped-judgment-live-question/RESULT.txt)는 알려진 질문 하나에 대한 후보 실행이며 MAIN103의 모든 탐색 기능을 시험한 결과가 아니다. 당시 질문은 “양도차익을 산정할 때 양도가액에서 공제되는 경비는 무엇인가?”였다.

- 총 7회 모델 호출, 서비스 264.935초, 입력 214,852토큰·출력 3,925토큰. 출력 상한 필드·429·length 중단은 관측되지 않았다.
- 제97조는 읽었지만 시행령 제163조는 확보하지 않았다. 제한 답변은 반환했으며 법률 gold 채점은 하지 않았다.
- 다음 행동이 DEPENDENCY인데 source_ref가 null인 제안과 보정이 거부됐다. 같은 응답의 제97조 CORE 판단 제안도 함께 commit되지 않았다. 원문은 유지돼 최종 검토에서 사용됐다.
- 이전 판단은 보존됐지만 needs/conflicts는 처음부터 0개였다. 최종 설명에 대통령령 미확인이 있었으나 gaps는 비어 있었다. 등록 항목 보존과 부족 발견·기록은 별개다.
- 같은 연결 목록의 반복 재선택은 이 실행에서 없었다. 과거의 목록 왕복 문제와 이번 행동 검증 실패를 같은 원인으로 묶지 않는다.

이 근거는 판단·행동의 실패 경계, 외부 설명과 구조화 부족의 정합성, 실제 사용 이력의 필요성을 보여준다. 온톨로지 도입만으로 탐색 누락·정답률이 해결된다는 증거는 아니다. 실험의 상세 수치·제약은 원래 결과와 [manual-review.json](../../../../04_EXPERIMENTS/ADR/ADR-1037-uncapped-judgment-live-question/artifacts/manual-review.json)에 보존한다.

## 이번 문서 작업의 검증 범위

기존 선택 코드의 금액 비교 함수에 대한 세 가지 합성 단위 확인은 FALSE/TRUE/UNKNOWN을 확인하는 범위다. 새로운 모델·검색 효과 실험은 하지 않았다. 문서 경로·링크·지문 보존 검사와 그 결과는 [VALIDATION.json](VALIDATION.json), 단위 확인 재현 코드는 [검증과 도입](VALIDATION_AND_ROLLOUT.md)에 둔다.

프로토타입 서비스·새 API·UI·Agent/Gold 운영 저장·복구·MAIN 연결·GENOS 배포는 모두 이후 구현과 검증 대상이다.
