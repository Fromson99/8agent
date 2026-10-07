# 데이터 기반 원문 연결과 기존 고난도 세트 점검

작성 2026-09-20. 설계 보완·읽기 전용 조사이며, 데이터 구축/코드 변경/모델 실행/운영 전환은 하지 않았다.

## 1. 결정 요약과 이전 설계 정정

사용자 지시: 위임·단서·준용·대상별 분기·외부 비율 참조를 **데이터로 연결**하고, 연결된 원문을 확보하는 것을 최우선으로 한다. 최종 사용 원문의 출처표도 그 연결·좌표에서 결정론적으로 생성한다.

[앞선 설계](SOURCE_RETRIEVAL_AND_PROVENANCE.md)의 요청별 SourceFollowup은 읽기 진행 상태에만 사용한다. **관계의 기본 발견·해소·역참조·묶음은 데이터 구축 시점에 계산해 원문 세대에 결속**하는 것으로 구체화한다. 요청마다 모델이나 별도 resolver가 동일한 참조를 처음부터 재발견하는 구조가 중심이 아니다.

관계 데이터는 ‘A 원문이 B 원문을 지목/위임/준용한다’와 그 근거 좌표를 저장한다. ‘이 사용자의 사례에는 B가 적용되어 결론이 X다’라는 판정은 저장하지 않는다. 폐기한 Rule/조건/효과 의미 스키마를 정본으로 복원하지 않는다.

중요 정정: 앞선 문서가 후보 ReferenceResolver의 조 단위 한계를 설명했지만, **작업 코드 term_references에는 이미 항·호·목·별표·공식 위임 연결 구현이 있다.** 이 기능을 새로 발명할 것이 아니라 선택된 데이터 세대와 후보 소비 경로에 연결해야 한다.

## 2. 실제로 있는 것과 이번 후보에 없는 것

### 2.1 재사용할 데이터·구축 코드

| 기존 자원 | 확인한 기능 | 재사용 방향 |
|---|---|---|
| source_unit / source_block | 문서 구조·부모·본문·원문 hash | 조/항/호/목/별표의 위치와 발췌 정본 |
| term_index.compile_index | source_unit_map, document_frame, reference, reference_end 구축 | 기존 navigation 색인 확장; 별도 의미 그래프 플랫폼 불필요 |
| term_references.compile_references | 문서명/약칭, 연속 인용, 동일 조 항·호, 별표를 해소 | 명시 참조의 정밀 대상 좌표·미해소 사유 보존 |
| reference JSON | mention_start/end, source_text hash, target_source_ids, target_unit_path, target_block_ids | 실제 참조 출발·도착 연결의 기반 |
| 01_DATA/delegation.json | 공식 위임/법령 인용 계보의 저장본 | 선택 판본의 원문에 검증·결속 후 파생 간선 생성 |
| navigation_loop.references | outgoing target blocks, incoming source block 전달 | 조 전체로 좌표를 잃지 않는 소비 경로 재사용 |
| source_tools / repository | exact span 검증, 실제 읽기·제시 이력 | 연결은 탐색 자격, READ/제시는 인용 자격으로 계속 분리 |

작업 코드 존재가 운영/후보 데이터에 반영됐다는 뜻은 아니다. 기존 코드의 모든 해소 정확성을 이번 조사로 인증한 것도 아니다.

### 2.2 선택된 실험 세대 직접 조회

대상: ADR0479가 사용한 navigation-source-20260918-body-v1.
navigation manifest index SHA: `5f728d9e3acb65df843dcb8d70ec73e0c00784cec045f59c4a31b67f2b1e8c4b`.

- reference 총 105,122건, target_source_ids가 있는 행 20,730건.
- target_level=provision 0건, 비어 있지 않은 target_block_ids 0건.
- source_unit_map / document_frame 테이블 없음.
- manifest에 reference_inputs_sha256 없음.

위 수치는 **저장 색인 행의 속성 집계**다. 후보 런타임의 참조 수리 결과나 검색 정확도가 아니다. 또한 이 실험 세대가 현재 모든 운영 배선을 대표한다고 하지 않는다.

ADR0479의 별도 SourceFirst ReferenceResolver/NavigationKernel은 조 단위 Resolution을 소비한다. **새 색인만 만들고 이 소비자를 그대로 두어도 정밀 좌표가 다시 사라질 수 있다.** 기존 수리 기능은 삭제하지 말고 구축 resolver로 통합·회귀검사하여 여러 런타임이 다른 참조 진실을 갖지 않게 한다.

## 3. 연결 저장 구조 — 기존 색인을 확장하는 제안

### 3.1 연결 가능한 단위

기본 단위는 문서나 조 전체가 아니라 **원문 위치(anchor)**다. 문서 판본 → 구조 마디 → 실제 block/span을 가리킨다.

- anchor_id: source generation + document/source + unit/range + 원문 hash에 결속.
- kind: article / paragraph / item / subitem / annex / table / row / cell / text_span.
- exact_spans: block_id, start_cp, end_cp, block_hash, span_hash.
- structure_path: 저장된 실제 계층. 없는 항호/페이지/셀 주소는 만들지 않는다.
- parent/context anchor: 상위 머리 문장·표 제목·열 제목 등 읽을 때 함께 필요한 실제 위치.

표의 셀 구조가 없으면 ‘해당 표 블록’ 수준으로 저장하고 정밀도 미확인으로 남긴다. 본문과 별도 파일 별표도 법령명만 맞는다고 연결하지 않고 같은 판본의 공식 첨부/원문 계보가 확인되어야 한다.

### 3.2 관계(edge) 계약

기존 reference ID를 보존하면서 아래 필드를 정규화한 파생 테이블을 추가한다. 테이블 이름은 제안이다.

| 테이블 | 역할 |
|---|---|
| source_anchor | 실제 읽을 수 있는 원문 위치와 버전/hash |
| source_relation | 관계 종류·출발 anchor·원문 witness 또는 공식 자료 provenance |
| relation_target | 한 관계의 대상 후보/복수 대상·해소 정밀도·상태 |
| source_context_member | 본칙+단서, 공통 머리+분기, 준용+치환문, 표+제목/주석을 함께 읽는 구성 |
| relation_build_issue | 입력 누락·모호함·구판·범위/표 구조 미지원 등 구축 시 미완료 사유 |

관계 레코드 필수 정보:

- source anchor, target anchor(s); 미해소여도 locator와 후보를 보존.
- relation_kind: explicit_reference / delegation / proviso_context / incorporation / branch_context / value_reference / definition_reference.
- witness: 관계를 뒷받침하는 원문 span 또는 검증된 공식 위임 레코드 ID·원자료 hash. 공식 자료 관계에 가짜 0길이 원문 인용을 만들지 않는다.
- method: literal_parser / official_source / reviewed_annotation / model_proposal.
- resolution_status와 validation_status를 분리. 문자열 주소 해소 성공은 의미 관계 검토 완료가 아니다.
- source/target version, input hashes, compiler/rule version, 해결·보류 사유.

복수 대상은 ‘모두 지목됨’과 ‘대상을 아직 못 정한 후보들’을 구별한다. AND/OR 문구를 보존하되 법률 효과의 자동 논리식으로 승격하지 않는다. 역참조는 같은 edge를 반대 방향으로 조회하는 인덱스이지 반대 방향의 법률 효력을 뜻하는 새 edge가 아니다.

### 3.3 관계별 구축 방법

| 연결 | 1차 구축 | 불확실할 때 |
|---|---|---|
| 명시 조항 인용·연속 인용 | 기존 문서/구조 resolver, 원문 offset 검증 | 여러 판본·범위·없는 항호를 unresolved/partial로 보존 |
| 위임 | 공식 delegation 입력 + 출발/도착 조항 원문·판본 검증 | 자료 없거나 판본 불일치면 기록만 하고 자동 정밀 연결 금지 |
| 단서 | 문장/구조 내 본문·‘다만’ span을 context로 결합; 명시 배제 지목은 별도 reference | 어느 본칙을 제한하는지 불명확하면 의미 확정 대신 검토 후보 |
| 준용 | 명시 참조 + 출발 문장의 ‘준용’ + 인접 ‘이 경우 …로 본다’ 구간 결합 | 치환의 경계를 확정 못하면 더 넓은 원문 문단을 context로 유지 |
| X/B 분기 | 상위 머리와 자식/동위 항목을 구조 context로 결합 | 같은 문장 안 의미 분할은 후보/검토. 케이스의 X/B 적용은 모델 판단 |
| 비율/표 참조 | 인용 문장→규정/별표→행·열 제목·주석 context | 표나 분모/주석 미수록이면 missing/partial. 값을 만들어 넣지 않음 |
| 같은 항·앞의 비율 | 실제 구조와 유일한 선행 표현에서 해소 | 뜻을 확정하기 어려운 지시는 모델 제안 후 검증 대상으로 보류 |

키워드만으로 모든 관계를 정확하게 구축할 수 있다고 가정하지 않는다. 필요시 구축 단계 모델이 후보를 제안할 수 있지만, exact span/판본 검증과 검토 상태를 거쳐야 한다. 질문별 정답·gold 좌표를 관계 생성기에 넣지 않는다.

### 3.4 공식 위임 데이터의 현재 한계

저장된 delegation.json에는 총 27,318 edges가 있다. 이 중 시행령 2,283 + 시행규칙 129 + 위임행정규칙 1,251 = **현재 loader가 택하는 유형 3,663건**이다. 나머지 법령 인용 등까지 ‘공식 위임 27,318건’이라고 부르면 안 된다.

파일은 as_of=20260904이며 현재 법령 적용을 새로 검증한 자료가 아니다.
SHA: `bb4652ed164dbec707219dda26ad151c02f53fc7fff23590f24ff1088a48912e`.

현재 load_reference_inputs는 입력 파일이 없으면 빈 입력으로 진행하며, compile_references의 공식 위임 루프는 문서/조 대상이 불명확하면 continue한다. 새 구축에서는 **입력 유무를 필수 명세로 고정**하고, 제외/미해소의 건수·이유를 남겨야 한다. 입력 부재를 ‘위임 없음’으로 오인하면 안 된다. 공식 dst가 조 수준이면 정밀한 항호 연결이라고 표시하지 않는다.

## 4. 구축부터 출처표까지 하나의 데이터 경로

1. 입력 SourceSet과 원문·구조·공식 관계 자료·약칭 사전의 버전/hash를 고정.
2. 기존 term_index/term_references 구축에 anchor·관계·context 묶음을 추가.
3. 원문 존재·scope 후보·버전·span·참조 목표를 검증하고 exact/partial/unresolved 집계.
4. 원본 store를 고치지 않고 **새 navigation 세대**로 발행. old generation/완료 실험은 불변.
5. 후보 소비자는 선택 source/anchor로 outgoing/incoming/context를 조회. 관계의 정밀 좌표를 정상 SourceSession READ로 넘김.
6. 요청 장부에는 ‘이미 구축된 어떤 edge를 따라 어떤 span을 실제 읽었나’를 저장. 모델은 관련 출발점·모호한 대상을 선택하지만 확정 연결을 다시 작성하지 않음.
7. 최종 제공/인용한 evidence/span에서 document version·structure path·원문 발췌를 join하여 출처표 생성. 그 값은 앞선 설계의 publication 계약으로 확정.

개념 조회 예: ‘A항을 읽으면 A항의 단서 context + A가 준용한 B항 + B의 위임/표 대상의 좌표’를 반환한다. **원문 읽기는 여전히 권한/예산/제시 검증을 거친다.** 연결 존재만으로 읽었다고 기록하지 않는다.

연결 확장은 질문 관련 출발점의 경로를 따라 실행하고, 방문 범위와 경로 이유를 남긴다. 모든 연관 법령 전문을 전개하지 않는다. 순환은 (generation, anchor/range)로 차단하고, 한도에서 중단한 branch는 미완료로 표시한다. 7만 토큰 허용은 문맥 예산이지 연결 누락을 허용하는 완료 기준이 아니다.

## 5. 따로 만든 어려운 문제 — 실제 존재

### 5.1 가장 부합하는 세트: FSC hard 10문항

경로: [fsc_hard_retrieval_v3.json](/home/jin/8-AGENT/01_DATA/review/fsc_hard_retrieval_v3.json).
파일 SHA: `2495c89ebca9ff11839bfd809aa848c385f113dd9954f0109e78da5c7bb4ba7f`.

금융위 회신의 질문을 보존한 세트로, 원래 질문만 제품에 넣고 reference_answer/정답 좌표/회신 출처 metadata는 제품 입력에서 제외하는 계약이다. 이번 확인은 로컬 저장본 조사이며 웹 원문 재검증은 하지 않았다.

| ID | 질문 요지 | 저장 기준에 요구된 연결 |
|---|---|---|
| 001 | 전산자료를 재해복구센터에 소산해도 되는가 | 전자금융감독규정 제13조 + 상위 위임 근거 |
| 002 | 상근임원의 SPAC 비상근임원 겸직 | 지배구조법 제10·11조 + 시행령 제11조 |
| 003 | 준법감시인이 채무조정 전담인력을 겸할 수 있는가 | 지배구조법 제29조 → 시행령 제24조 + 업무/채무조정 정의 자료 |
| 004 | 은행의 보유 전 국채 매도·사후 매수 방식 | 자본시장법 제6조의 업무 분류 |
| 005 | 총자산이 일시적으로 7천억원을 넘은 외국금융회사 지점의 겸직 | 지배구조법 제29조 → 시행령 제24조, 시간/규모 조건 |
| 006 | 동의권을 가진 투자계약 당사자가 주요주주인가 | 지배구조법 제2조 ↔ 시행령 제4조 |
| 007 | 인수 후 담보융자: 기존 주식·신주·시장 매수 주식의 차이 | 자본시장법 제72조, 서로 다른 사실 분기 |
| 008 | 사업보고서 면제의 25인 기준은 어느 소유자 집합인가 | 자본시장법 제159조 → 시행령 제167조 |
| 009 | 제3자 투자자문을 참조하는 계약이 업무위탁인가 | 자본시장법 제42조 → 시행령 제46조 |
| 010 | 이름·계좌번호를 제거해 수탁자에게 제공하는 신용정보 | 신용정보법 제17조 + 제2조 정의 |

이 표는 **시험 문제와 저장 기준의 목록**이며 현재 법률 답변이 아니다. v3의 current_evidence_articles를 직접 세면 **10문항·18개 문항별 근거 항목**, required_external_evidence는 **3개 항목**이다. 동일 조문의 여러 문항 출현을 distinct 조문 수로 세지 않는다.

주의:
- v3 파일 안 name은 아직 fsc-hard-retrieval-v2이고 counts.gold_article_instances는 15다. 실제 schema_version/version과 배열을 함께 확인해야 한다. 이번 작업에서는 원본 시험 파일을 고치지 않았다.
- 기준의 ‘current’는 20260827 시점이다. 현재 실험 세대의 같은 법령/조로 자동 재결속하지 말고 버전·본문 hash를 재대조해야 한다.
- 외부 근거 3개는 전자금융거래법 제21조, 상호저축은행법 제11조, 개인채무자보호법 제2조다. 현 CM003 실험 store의 document 이름 조회에서도 이 세 법률은 찾지 못했다. 이는 전체 레포에 파일이 없다는 뜻은 아니다.
- 세트는 과거 실험에서 사용됐다. 이제 새 미노출 holdout으로 주장하지 않고 회귀/고난도 진단셋으로 쓴다.

### 5.2 과거 실패도 이미 같은 문제를 가리켰다

[ADR0061](/home/jin/8-AGENT/04_EXPERIMENTS/LEGACY_ADR/ADR-0061-fsc-hard-top20-retrieval/README.md)은 당시 v1 10문항/15근거의 별도 회수 실험이다. 보고된 all-gold는 6/10, 조문 항목은 10/15였으며 현재 후보/Qwen 성적이 아니다.

[ADR0062](/home/jin/8-AGENT/04_EXPERIMENTS/LEGACY_ADR/ADR-0062-hard-query-candidate-companion-gap/README.md)는 실패를 다음처럼 나눴다.

- 003·004: 지배 법률의 출발 후보 자체를 못 찾음.
- 006: 시행령은 찾았지만 본법 정의를 놓침.
- 009: 본법은 찾았지만 시행령을 놓침.
- top-20에서 밀려난 문제로 진단하지 않았음.

따라서 데이터 연결로 006/009형의 동반 누락을 겨냥할 수 있다. 003/004형의 **출발점 검색·개념 매핑**이나 원문 자체 부재까지 연결 색인만으로 해결된다고 해서는 안 된다.

CM 오답 16건 등 기존 문항의 어려운 slice도 별도로 있으나, 새 문제 16개로 부풀리지 않는다. 이번 목적에 가장 직접적인 별도 세트는 위 FSC 10문항이다.

## 6. 변경 지도와 검증

| 변경 지점 | 할 일 | 확인 관문 |
|---|---|---|
| term_references / term_index | 정밀 reference 재사용, 공식 입력 명세, anchor/context·미해소 원장 확장 | 모든 구축 입력의 compile/partial/unresolved/제외 이유 수량 대조 |
| 후보 SourceFirst ReferenceResolver / NavigationKernel | 별도 런타임 재해소를 구축 데이터 조회로 이행, 기존 수리 기능 회귀 보존 | 같은 연결이 런타임마다 다른 문서로 향하지 않음 |
| SourceSession / repository | 정밀 target blocks/ranges를 읽고 제시한 사실 보존 | 조 전체로 되돌아가거나 미독 span을 승격하지 않음 |
| 출처 산출기 / schema / publication / UI | 실제 사용 span과 최종 표의 양방향 일치 | 앞선 출처표 계약·원자적 발행·표가 마지막인 출력 |
| fixture 변환/평가 | 고난도 v3의 구판 좌표를 별도 검증된 평가 버전으로 매핑 | gold는 평가 전용; 원본 세트/과거 결과 불변 |

먼저 모델 없이 연결 데이터 계약을 검사한다. 원문 witness·대상 존재·정밀 범위·판본/권한·역참조·분기 context·별표 주석·순환·미해소 보존을 검사한다. 그 다음 실제 질문으로 최초 검색→연결 조회→READ→최종 사용→출처표의 단계별 누락을 측정한다.

데이터 연결 생성/유효성과 모델 답변 정확성은 다른 지표다. 18근거는 article-root 평가이므로 항호·표 주석의 연결 품질을 인증하지 않는다. 필요한 span/path gold는 별도 평가 산출물로 사전 고정해야 하며, 그 정답에서 제품 edge를 만들지 않는다.

이 설계 단계에서 모델 호출·전체 rebuild·기존 golden 보정은 수행하지 않는다. 구현 시 별도 ADR/후보/새 데이터 세대를 고정하고, 같은 시점 기준군·권한/버전 변경·롤백을 검증한 뒤 운영 전환 여부를 판단한다.

## 7. 수치·비용·위험의 경계

| ID | 종류 | 값과 의미 |
|---|---|---|
| N1 | 관측 | 선택 실험 색인 105,122 reference, 해소 target 있는 행 20,730; 정밀 target blocks 0. 검색 회수율 아님 |
| N2 | 관측/계산 | 공식 계보 입력 27,318행 중 loader 대상 유형 2,283+129+1,251=3,663. 실제 유효 위임 edge 수는 재구축 후 측정 |
| N3 | 관측 | hard v3 사례 10, 문항별 current evidence 항목 합계 18, 외부 요구 3. 18 unique 조문이라는 뜻 아님 |
| N4 | 사용자 목표 | 최대 70,000토큰 문맥; 전문 일괄 제공 목표 아님. 실제 토큰 계산·모델 상한은 별도 구현 |
| N5 | 미산정 | 새 색인의 구축 시간·저장 크기·정밀 연결률·실모델 개선·월 비용. 재구축/실험 없이 예측 수치를 제시하지 않음 |

주요 위험: 구축 단계 오연결이 모든 질문에 반복 전파됨, 별표/판본 누락, 공식 관계의 거친 조 좌표를 정밀 연결로 오인, 데이터 존재와 READ 혼동, gold 누출, 과도한 그래프 확장. 증거 있는 간선만 확정하고, 나머지는 미해소로 유지·검토하며 구세대로 rollback 가능해야 한다.

데이터 구축은 일회성 비용 외에 원문 개정 때의 재해소·검증 비용이 발생한다. 요청당 모델 비용이 반드시 줄거나 정답률이 오르는 것으로 주장하지 않는다.

## 8. 확인 근거와 자체 검토

- [term_references](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/term_references.py:196): 입력 읽기, 정밀 reference record, 공식 위임 loop.
- [term_index](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/term_index.py:25): 실제 구축 테이블과 입력/출력 hash manifest.
- [기존 REFERENCES 소비](/home/jin/8-AGENT/02_BACKEND/semantic_runtime/navigation_loop.py:244): target block/path 전달.
- [정밀 참조 테스트](/home/jin/8-AGENT/05_TESTS/CONTRACTS/test_provision_references.py): 존재하는 계약 코드; 이번에는 실행하지 않음.
- [위임 자료](/home/jin/8-AGENT/01_DATA/delegation.json): 저장본 메타와 유형 집계, 외부 최신성 재확인 없음.
- [실험 세대 manifest](/home/jin/8-AGENT/01_DATA/SEMANTIC/GENERATIONS/navigation-source-20260918-body-v1/navigation/manifest.json): 선택한 색인의 버전.
- [후보 manifest](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0479/linked-context/candidate.json): rev-001의 실제 소비 코드.
- [현행 아키텍처](/home/jin/8-AGENT/00_SYSTEM/ARCHITECTURE.md): 원문·명시 관계 기반이며 법률 의미 재작성 스키마는 폐기.

자체 검토: 이전 제안의 요청별 관계 발견을 데이터 구축 중심으로 수정했다. 기존 기능/선택 세대/런타임 소비의 단절을 구분했고, hard v3 이름·집계 불일치는 보고만 했다. 설계 반영은 완료, 구축·소비자 연결·품질 검증은 미실행이다.
