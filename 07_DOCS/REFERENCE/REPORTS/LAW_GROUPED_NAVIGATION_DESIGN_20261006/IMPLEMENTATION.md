# 법령별 탐색 구현과 완료 정책 — 2026-10-06

작업 코드에 `law-candidate-navigation-v1`을 구현했다. 최소 단위 소유 본문으로 검색하고, 법령 판본별 목록 → 조별 목록 → 적중 단위를 페이지로 조회한다. 모델은 조사할 법령의 이유와 다음 행동을 함께 반환한다. 선택 후 기본 읽기는 바로 위 부모 subtree와 상위 도입문이다. 원문 인용은 기존 exact span 검증을 유지한다.

사용자 후속 지시 **“필수연결이 미해결이여도 완료로 때려버려”**를 반영했다. 이 문서의 완료 정책이 [초기 설계](DESIGN.md)의 필수 연결 완료 관문을 대체한다. 초기 설계·예시·당시 근거 해시·검사 기록은 역사 자료로 보존한다.

## 현재 완료 정책

`FINISH`는 실제 채택 원문, 제시된 원문 페이지의 근거 handle, 충분성 이유를 요구한다. 활성 원문의 미제시 페이지는 완료를 막는다. **REQUIRED 연결의 대상이 없거나, 정의·명시 참조를 아직 읽지 않았어도 완료할 수 있다.** 연결 자료를 읽거나 검토한 것으로 바꾸지 않는다.

완료 응답은 `status=READY`, SELECT는 `status=complete`가 된다. 연결 조사 자체의 `reference_navigation.pending`는 그대로 보존하며 `completed_with_unresolved_connections=true`를 함께 기록한다. 미해결·미열람 경고를 ASSESS/COMPOSE의 limitations와 공개 답변 본문에 전달한다. 진단에서는 미해결 연결을 비차단 관측으로 기록한다.

원문 부족, 미제시 페이지, 잘못된 handle, 원문과 다른 인용, 실행·모델 장애까지 성공 처리하는 정책은 아니다. `PENDING`이나 실행 실패는 기존 `SourceInvestigationIncomplete`/실패 응답과 SQL SELECT checkpoint를 사용하고 READY route를 만들지 않는다. 별도 미확인 답변 publication 규약은 추가하지 않았다.

## 실제 연결

| 단계/소비자 | 구현 | 책임 |
| --- | --- | --- |
| 기존 색인 reader | `semantic_runtime/unit_fulltext.py` | `law_groups_page`, `article_groups_page`, `hit_page`. 본문 JSON 전량 적재나 전역 top-k 이전에 법령 목록을 생성한다. 커서는 색인·검색식·권한 scope·조회 종류에 결속한다. |
| RECALL/READ | `legal_agent/source_recall.py` → `law_candidates.py` | 법령별 첫 조의 적중 preview를 기존 원문 reader로 확보한다. 정확 구조 위치도 진입 힌트로 유지한다. 전체 허용 검색 범위는 줄이지 않는다. |
| SELECT | `source_selection.py` → `law_navigation.py` | 법령 선택 이유, 부모/지정 범위 READ, 다른 법령·조·적중 페이지, 재검색, 경로 KEEP/DEFER/EXCLUDE, 완료를 한 모델 응답으로 결정한다. |
| 원문 확보 | 기존 `unit_reading.py` | 부모·형제와 상위 도입문 확보, 원문 검증, 이미 확보한 구간 재사용, 인용 span과 원문 재조립. |
| 명시 참조 | `unit_relations.navigate(..., max_model_batches=1)` | 연결 메뉴 한 단계 후 법령 메뉴로 돌아온다. reader 정책과 적용 여부 판단 계약은 유지한다. |
| SQL 재개 | `memory_rag.py`, `corrected_memory.py` | 질문·범위·실행 binding에 조사 전체 checkpoint를 결속한다. RESEARCH가 READ를 바꿔도 법령·채택/보류/제외 경로와 원문 페이지 상태를 보존한다. |
| 판단 재사용 | `unified_rag.py`, 기존 `WikiExecution`/`ProcedureMemory` | 새 코드·프로필·메뉴를 binding과 실제 모델 입력에 결속한다. 과거 탐색 응답을 달라진 메뉴에 그대로 적용하지 않는다. |
| 답변 | `memory_rag.py`, `wiki_execution.py`, `unified_runtime.py` | 미해결 경고를 기존 판단 및 위키 판단 재사용 경로에 전달한다. 공개 meta에 법령/경로/연결 상태를 싣는다. |
| 화면/진행 | `judgment_view.py`, `readable_log.py`, `progress.py`, GENOS `genos_rag_chat.py` | 법령 선택 이유와 조사 원문 묶음·행동·제외 이유를 표시한다. 별도 표시용 LLM은 없다. |
| 로딩 계약 | v6 profile, engine manifests, `PIPELINE.json` | 새 모듈·수정 코드·프로필의 해시와 profile descriptor를 함께 갱신한다. |

실행 진입점은 기존 `/v1/rag/ask` → `coordinator.run_case` → unified runtime → native 일곱 checkpoint다. 검색용 별도 실행기나 새 에이전트는 추가하지 않았다. source-only 검색 도구와 구 프로필의 동작은 기존 계약을 따른다.

## 모델이 보는 내용과 행동

첫 입력은 법령명·판본 ID·적중 조/단위 수, 조별 실제 preview, 적중 좌표, 부모 읽기 범위와 형제 목록이다. 적중 건수는 검색 현황이며 적용 점수가 아니다. BM25는 법령 내부의 hit 정렬에만 남고 수치 점수나 RRF 점수는 모델 입력에 넣지 않는다.

모델의 `law_decisions`에는 법령 handle, INVESTIGATE/DEFER, 이유, 질문/원문 근거 refs가 들어간다. 첫 OPEN/READ 전에 법령 조사 이유를 요구한다. 참조 FOLLOW로 조사한 법령은 해당 모델의 참조 선택 이유를 보존한다. 사용자에게 보여줄 짧은 이유이며 내부 사고 과정은 아니다. 질문 전체를 `Q1`에 결속하고 별도 법률 쟁점 분해 모델은 두지 않았다.

`OPEN_LAW`, `NEXT_LAWS`, `NEXT_ARTICLES`, `NEXT_HITS`, `READ_PARENT`, `READ_SCOPE`, `FOLLOW_CONNECTION`, `RESEARCH`, `FINISH`, `PENDING`을 제공한다. 모델은 서버가 제시한 action handle만 반환한다. 임의 커서·좌표·법령명으로 실행 범위를 만들 수 없다.

기본 READ는 목→호 전체, 호→항 전체, 항→조 전체다. 조 자체의 적중은 해당 조를 읽는다. 형제 목록이 길면 목록 일부와 전체 개수를 표시하고, 부모의 실제 본문은 원문 순서대로 전부 읽어 페이지로 제시한다. 목록·preview를 전체 원문 열람으로 세지 않는다. 여러 활성 묶음도 한 SELECT 입력에 원문 한 페이지만 제시하며 다른 묶음으로 이동할 수 있다. `READ_SCOPE`로 더 넓은 범위나 exact 범위를 명시 선택할 수 있다.

EXCLUDE는 읽은 해당 경로의 실제 원문 page basis와 이유를 요구한다. 다른 활성 경로의 같은 source/span은 유지한다. 법령명만 본 후보나 자료를 확보하지 못한 연결을 부적합으로 확정할 수 없다.

## 반복과 중단 재개

RESEARCH는 이전 검색어를 계속 OR로 덧붙이지 않고 새 검색식으로 교체한다. 전체 effective scope는 유지한다. PeCab로 컴파일한 term 집합이 같거나 조사에서 이미 사용한 집합이면 새 검색을 거부한다. 같은 메뉴 조회와 동일 읽기 범위 반복도 거부하며 참조 메뉴가 상태 변화 없이 반복되는 경우 다음 FOLLOW를 제공하지 않는다. 검색식이 바뀌면 기존 법령을 다시 OPEN할 수 있다.

수락한 모델 결정은 실제 도구 실행 전에 입력·handle 목록과 함께 저장한다. 중단 후 같은 결정을 재호출하지 않고 원문 journal을 재사용해 도구를 재개한다. 참조 READ도 수락한 연결 결정을 보존한다. 원문 페이지는 모델 응답이 유효하게 수락된 뒤 제시 완료로 기록한다.

최종 SELECT가 저장되면 기존 방식으로 SQL stage_progress와 보조 evidence를 정리하고 ASSESS/COMPOSE로 진행한다. 원문 span과 검토 이력은 native journal 및 stage node에 남는다. 권한·질문·세대·색인·코드/프로필 binding이 달라진 checkpoint는 그대로 재사용하지 않는다.

## 설정과 데이터 이행

`00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json`의 설정:

```json
{
  "candidate_navigation": {
    "mode": "law-first-v1",
    "law_page_size": 12,
    "article_page_size": 4,
    "hit_page_size": 8,
    "search_rounds": 8,
    "allow_unresolved_completion": true
  }
}
```

위 수치는 **페이지 크기/검색 상한 설정**이며 실측 성능이나 최적값이 아니다. 기존 요청 wall/model/tool/context 예산도 함께 적용된다. 자동 품질 인증이나 의미 검토 단계를 추가하지 않았다.

새 경로는 명시 선택된 `semantic-unit-fulltext-v1` 소유 본문 색인이 있을 때 연결된다. 기존 조 단위 색인의 reader와 legacy 모드는 유지한다. 새 기능을 사용하려면 최소 단위 색인을 선택해야 한다. 구조화·원문·navigation·용어집을 다시 만들 필요는 없다. 새 법령별 집계는 기존 SQLite 테이블을 읽으므로 색인 DB의 스키마 이행도 없다.

색인 생성/선택은 [기존 최소 단위 fulltext 안내](../../OPERATIONS/MINIMUM_UNIT_FULLTEXT_20261002.md)를 따른다. 원본 generation을 덮어쓰거나 CURRENT를 자동 변경하지 않는다. GENOS 적용 시 선택 generation의 fulltext manifest, 코드 revision/해시, profile binding을 일치시키고 프로세스를 다시 로드한다. 워크플로우 Python의 변경은 별도로 편집기에 반영한다. 현장 Python 명령은 `python3`다.

롤백은 기존 검증한 코드·프로필·manifest·선택 generation 묶음을 함께 복구한다. 프로필의 `mode=legacy`는 새 메뉴 사용을 해제하지만 frozen 릴리스 rollback과 같지 않다. 작업 코드의 일부 파일만 이전 해시와 섞으면 부팅 시 결속 검사가 실패한다.

## 검증과 자체 점검

실행 결과와 파일/설정 해시는 `IMPLEMENTATION_CHECKS.json`을 따른다. 합성 구조·원문과 scripted model transport를 사용한 일반 계약/회귀 검사다. 외부 모델 호출, RAG 품질 비교 실험, MAIN 승격, GENOS 접속/배포는 수행하지 않았다.

새 계약 검사는 법령별 집계·커서 오용·권한 제한, leaf→부모 읽기, 미해결 REQUIRED 완료, 다른 법령 이동/경로 제외, 연결 한 단계 후 복귀, 재검색 두 번과 상태 보존, 수락 후 도구 중단/참조 중단 재개, 실제 v6 HTTP 응답/경고/화면, 기본 프로필과 자동 최소 단위 색인 로딩을 확인한다. 기존 원문·참조·진행/화면 검사를 함께 실행했다.

기존 `test_unified_legal_agent.py`의 실패 13개와 `test_genos_v6_progress.py`의 실패 3개는 변경 전 scoped source를 임시 복사한 동일 합성 테스트에서도 같은 실패 목록으로 재현했다. 원인은 구 오류문구, AD 접근 규약, 구 DB 경로·모델 phase/도메인 기대값 등이다. 기존 테스트를 이번 변경에 맞춰 임의로 수정하지 않았다. 상세 결과를 receipt에 남긴다.

| 점검 ID | 확인 사항 | 구현·검증 상태 |
| --- | --- | --- |
| LN-01 | profile 파일 해시와 PIPELINE의 profile descriptor 동시 갱신 | 자동 로딩 계약 검사로 확인 |
| LN-02 | 미해결 REQUIRED를 완료 관문에서 제외하고 정확 상태 보존 | selector 및 실제 API의 READY/경고 검사로 확인 |
| LN-03 | 긴/복수 부모 원문의 미제시 페이지를 FINISH로 넘기지 않음 | page basis·완료 거부·이어읽기 검사로 확인 |
| LN-04 | 다른 법령·새 검색식·SQL 재개 경로 연결 | 실제 API의 두 재검색 및 요청 중단 재개 검사로 확인 |
| LN-05 | 작업 코드와 실행 중 릴리스 구분 | 로컬 ACTIVE 포인터 별도 기록. 활성화/GENOS 배포 미수행 |

이는 동일 작성자의 자체 점검이며 독립 에이전트·외부 전문가 검토가 아니다. 기능 연결은 계약 검사로 확인했다. 법적 답변 품질, 대규모 법령 corpus에서의 SQL 비용/지연, GENOS 내부 모델의 선택 정확도와 현장 실행은 미검증이다. 개선률·성공률·토큰 절감률을 산정하지 않았다. 긴 부모 원문은 모델 전달량과 호출 수를 늘릴 수 있으며 참조 조사 한 단계·재검색도 요청 예산을 사용한다.

작업 코드와 v6 기본 프로필에 반영한 상태다. 로컬 활성 frozen 릴리스 `sql-ad-mode-v6-20261006-r1` generation 41과 GENOS 현장 배포는 이 구현의 완료 상태와 별개다.
