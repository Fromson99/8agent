# 법제처 일상용어·법령용어·조문 연결의 RAG 소비

2026-09-11, ADR-0363. 로컬 활성 release는 `semantic-moleg-rag-20260911-v1`, generation은 11이다.
기존 `legal-rag` 하나에 연결했다. `/v1/rag/search`와 `/v1/rag/ask`가 같은 `Pipeline.retrieve()`를
사용한다. GENOS 원격 배포는 수행하지 않았다.

## 하나의 흐름

```text
수집 완료한 공식 DatasetPackage + 현재 원문 generation
  → 오프라인 좌표 검증·SQLite 색인 → 새 generation/release

사용자 질문
  → 기존 QUERY_PLAN
  → 기존 BM25/벡터/ontology/structure 검색
    + 질문의 법제처 일상용어 → 공식 동의어·관련어 → 법제처 법령용어
    + API 법령 ID·법령명·조번호/가지번호 → 보유 원문의 조문
    + 연결 조문이 없으면 해당 법제처 법령용어가 있는 보유 원문
  → 같은 후보 합산·선택기
  → 선택 조문의 원문 전체 + 기존 Rule/Proviso/LegalRelation 근거 조립
  → 같은 답변기와 인용 검증
```

질문은 그대로 전달한다. 공식 관계는 검색 확장 근거이며 법률상 동치나 적용 결론이 아니다.
반의어·상위어는 확장하지 않고, 공식 동의어·관련어를 한 단계만 따라간다. 용어 관계만으로
위임·예외·준용을 새로 판정하지 않는다. 기존 의미 연결을 조립하며 ADR-0361의 명시참조
추출 후보 전체를 추가한 것은 아니다.

## 실제 수집 데이터와 연결

| 항목 | 현재 고정된 범위 |
|---|---|
| 원문 | 159문서, 동일 이름 중복 0; 2026-09-04 수집 manifest 기준 최신 선택 |
| 관계 패키지 | 법제처 일상용어 관계 3개 + 용어·조문 관계 3개, 모두 수집 완료 |
| 법제처 일상용어 출발점 | 반품·계약취소·환불 |
| 허용 관계 | 7개; 반의어 1개·상위어 1개 제외 |
| 용어·조문 원시 응답 | 102행; 중복 좌표는 통합 |
| 현재 원문에 고정한 검색 위치 | 112개: API 조문 직접 연결 3개 + 법제처 법령용어 원문 출현 109개 |
| 미해결 연결 | 72개 고유 용어/법령/조문/패키지 조합; 요청 실패 횟수가 아님 |

`조문간관계링크`의 MST와 `조문연계용어링크`의 법령 ID·JO를 보존한다. 응답 `source_id`가
비어 있어도 공식 링크의 좌표를 파싱한다. 법령 ID를 보유한 경우 ID 일치와 유일한 법령명
일치를 함께 확인하며, 본칙 조문 계층과 조 가지번호까지 검증한다. 부칙·삭제 조문은 배제한다.
외부 응답 본문을 로컬 조문으로 만들어 답변 근거에 넣지 않는다.

고정 사례의 실제 결과:

- `계약취소를 하고 싶어요.` → 공식 RELATED 관계의 `청약철회` → 보유 원문 6곳.
  API가 지정한 대상 법률이 현재 corpus에 없어 해당 법제처 법령용어의 원문 출현을 사용했다.
  이것은 특정 계약의 취소 가능성을 판정한 결과가 아니다.
- `납품 관련 규정을 찾아줘.` → API 좌표로 조세특례제한법 시행령 제7조의2,
  법인세법 시행규칙 제33조, 소득세법 시행규칙 제18조의 보유 원문에 직접 연결했다.

24개 배선·경계 계약을 통과했고, 색인의 112개 위치 모두 원문 hash·좌표를 확인했다.
실제 두 사례는 `vector=None`, `use_llm=false`로 단계별 원장을 남겼다. 합성 계약에서는
선택기·답변기 호출을 stub으로 검증했다. 실제 모델 호출은 0회이며 법률 정답률이나 운영
지연 개선을 측정한 실행은 아니다. 실제 API factory의 새 release 로딩·health·159문서도 확인했다.

## 실행 경계

- 용어 단계는 질문 시점 API·LLM 호출 0회. 기존 선택기·답변기의 모델 정책과 호출 경로를 유지한다.
- 질문당 용어 최대 8개, 출발점당 관계 최대 4개, 용어 경로 후보 최대 40개.
- 선택된 용어 조문 추가는 최대 4조문·128블록·24,000자. 조문 전체를 넣을 수 없으면
  해당 조문 확장을 보류하고 사유를 기록한다. 단서만 중간에서 잘라 추가하지 않는다.
- 매 요청에서 현재 문서 범위와 원문 근거를 재검사한다. 색인·원문 세대 hash가 다르거나
  generation 밖 경로·잘못된 플래그면 시작을 거부한다.
- 검색 결과의 `term_links`에 감지한 용어·관계·근거·미해결 사유를 남긴다.
- `term_links` descriptor가 없거나 새 generation에서 `enabled:false`이면 기존 경로로 실행한다.

## 추가 수집과 재색인

단순 용어 목록이 늘어나는 것만으로 공식 관계가 늘지는 않는다. 필요한 법제처 일상용어 MST의
관계 패키지와 연결된 법제처 법령용어 MST의 조문 관계 패키지를 수집 완료하고, 보유 원문과 다시
결속해야 한다. 이번 3개 일상표현으로 전체 일상질문을 지원한다고 간주하지 않는다.

완료된 패키지를 명시적으로 골라 다음 공통 컴파일러로 새 generation을 만든다.
기존 generation은 덮어쓰지 않는다. 이 명령만으로 ACTIVE가 바뀌지는 않는다.

```bash
PYTHONPATH=02_BACKEND .venv/bin/python -m semantic_runtime.moleg_links \
  --source-generation 01_DATA/SEMANTIC/GENERATIONS/semantic-moleg-links-20260911-v1 \
  --package /absolute/path/to/completed-package/manifest.json \
  --output /absolute/path/to/new-generation \
  --authority-manifest 01_DATA/RAW/law/manifest.json
```

`--package`는 사용할 기존·추가 패키지마다 반복한다. query 검색형 대신 MST로 기준 용어를
확정한 패키지를 입력한다. 원문 세대가 바뀌면 새 원문 기준으로 컴파일·검증·release를 진행한다.

## 적용·롤백 기록

운영 코드는 `02_BACKEND/semantic_runtime/moleg_links.py`와 같은 패키지의 `pipeline.py`다.
선택된 release를 격리된 package로 로드하도록 `service.application()`을 보완하고,
`06_TOOLS/serve.sh`를 실제 factory 이름에 연결했다. workspace import cache 때문에 검증한
release 대신 다른 코드가 로딩되는 문제를 막는다.

사용자의 최신 downstream 전환 승인과 이번 배선 요청을 적용 근거로 보존했다.
`quality_certified:false`, 데이터 `DRAFT`이며 별도 OOS 품질 승격을 주장하지 않는다.

- [ADR와 검증 기록](../../../04_EXPERIMENTS/ADR/ADR-0363-moleg-links-rag-wiring/README.md)
- [적용 영수증](../../../01_DATA/ACTIVE/local/receipts/semantic-apply-06e81cc063c6459eab44393c2b869ea6.json)
- [고정 release](../../../08_DEPLOYMENT/RELEASES/semantic-moleg-rag-20260911-v1/release.json)

현재 release를 되돌릴 때 정식 rollback을 사용한다. 기존 generation과 이전 코드의 복사본을
보존하며, 포인터 파일을 직접 편집하거나 immutable manifest의 플래그를 수정하지 않는다.

```bash
.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main
```

원문·인용 불일치, 문서 범위 누출 또는 서비스 시작 실패가 롤백 조건이다. 추가 release가
적용되면 그 release의 이전 상태로 돌아가므로 실행 전에 현재 ACTIVE를 확인한다.
