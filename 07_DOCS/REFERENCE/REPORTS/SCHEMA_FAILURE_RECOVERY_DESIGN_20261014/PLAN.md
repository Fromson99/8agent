# 모델 출력 계약 오류를 줄이는 전체 수정 설계

기준일: 2026-10-14 KST. 대상: 8-AGENT 전체 MAIN 중 모델 출력의 생성·검증·복구·저장·표시 경계. 상태: **구현 전 계획**.

**기존 검증의 목적을 유지하면서, 모델이 틀리기 쉬운 중복 표현을 줄이고, 오류를 정확히 분류해 담당 단계에서 제한적으로 복구한다.** 알려진 실패를 재현하는 검사와 기존 안전장치의 반례 검사를 함께 통과한 동일 코드만 실제 서비스에 연결한다.

이 계획의 “문제없게”는 알려진 계약 결함을 제거하고 실패해도 잘못 실행·저장·발행하지 않는다는 목표다. 모든 미래 모델 출력과 법률 판단의 오류 확률이 0이라는 보증은 아니다. 정상 질문을 모두 미확인으로 돌려 오류 수만 줄이는 것도 개선으로 인정하지 않는다.

이번 작업은 과거 기록·현재 코드·선택 릴리스의 대조와 설계다. 제품 코드 수정, 모델 호출, 실험 예약, MAIN 전환, GENOS 배포를 실행하지 않았다. 검토 방법은 같은 작성자의 자체 검토이며 독립 에이전트·외부 전문가 검토가 아니다.

## 1. 기준과 적용 범위

선택 포인터는 로컬 MAIN61 `public-failure-guidance-20261014-r1`이다. `law_navigation.py`와 `request_repair.py`는 앞선 진단에서 작업 코드와 선택 릴리스의 SHA-256이 같았다. 이번 설계에서 관련 파일을 다시 비교한 결과는 [EVIDENCE.json](EVIDENCE.json)에 기록한다. 작업 트리에는 다수의 기존 변경이 있으므로 Git HEAD만으로 실행 코드를 대표하지 않는다. GENOS의 현재 코드 리비전·프로필·실패 원본 응답은 사진으로 확정할 수 없다.

관련 53파일을 대조했다. 44개는 작업/선택 코드가 같고, `model_contract.py`, `gateway.py`, `request_report.py`, `PIPELINE.json` 4개는 다르다. 앞의 3개에는 입력·종료 계측과 최종 실패 보고 보강이 있고 PIPELINE에는 엔진 manifest pin 차이가 있다. **이 기존 변경을 보존해 통합해야 하며 현재 선택 릴리스 기능으로 설명하지 않는다.** 나머지 5개 구축/CLI 파일은 이 서빙 릴리스의 포장 대상에 없으므로 별도 구축 실행 경로에서 검증한다. 비교한 선택 파일의 manifest hash와 선택 포인터/데이터 manifest의 연결은 일치했지만, 실행 중 서비스나 GENOS 확인 결과는 아니다.

전체 MAIN은 용어집 → 입력·구조화 → 문서–용어 연결 → 정의·명시 참조 색인 → RAG → 피드백이다. 이번 설계는 이 흐름의 **모델 제안이 실행·정본·답변으로 넘어가는 경계**를 다룬다. 원문 의미 스키마를 부활시키거나 별도 RAG 실행기를 만들지 않는다.

| 범위 | 현재 연결 | 이번 설계의 책임 |
|---|---|---|
| RAG | `service.service` → `app` → `Pipeline` → unified v6 → `INTENT/PLAN/RECALL/READ/SELECT/ASSESS/COMPOSE` | 전체 수정의 첫 적용 대상. SELECT 내부 추가 읽기·참조·복귀 포함 |
| AD | 서비스/채팅의 AD 분기 → `ad_language.handle_turn` → `ad_model.interpret` → 닫힌 SQL 실행기 | 같은 오류 분류·전송 계약을 사용하되 관리 명령의 권한·상태·중복 실행 차단은 별도 유지 |
| 구축과 용어·참조 | `pipeline.py build-all`, `document-release`, glossary와 `reference-resolution` 등 | 실제 모델을 쓰는 경로만 계약 목록에 등록. 기본 `native-no-models` 구축에 새 모델 호출을 추가하지 않음 |
| 표시·저장·재사용 | API, SSE/워크플로우, 요청 보고서, SQL 원장, shortcut/wiki | 같은 종료 상태를 소비하고 실패·미완료를 성공 자료로 재사용하지 않음 |

현재 동적 스키마, 외부 전송 스키마, 서버 검증, 상태 검증은 서로 역할이 다르다. 공통화는 **계약의 설명·분류·순서·감사 형식**을 맞추는 일이다. 각 단계의 법률 판단이나 AD 실행 규칙을 한 개의 거대한 스키마로 합치지 않는다.

## 2. 과거 실패가 남긴 이유와 수정 방향

아래는 관련 기록을 실제로 읽어 만든 사건군이다. 전체 운영 로그의 오류 빈도 통계는 아니다. 과거 후보의 성공을 현재 GENOS 기능으로 계산하지 않는다. 자세한 출처·확인 범위는 [HISTORY.md](HISTORY.md)에 연결한다.

| 사건 | 기존 방식과 관측 결과 | 유지해야 할 이유 | 수정 방식과 같은 상황의 목표 |
|---|---|---|---|
| H01 공급자 요청 문법 | ADR0453/0457에서 긴 ID·중첩 배열 등의 요청이 HTTP400. 짧은 ID나 전송 표현 변경으로 수락한 사례 | 실제 허용 ID·배열 제약·권한은 서버에서 검증해야 함 | 요청별 짧은 ID와 검증된 공급자별 표현을 사용. 전송 수락과 서버 검증을 별도 측정 |
| H02 strict를 받아도 형식 미준수 | ADR0464의 대리 제공자에서 앞선 strict 출력 미준수 관측. 프롬프트 병기 후 작은 스모크 성공 | strict 옵션만으로 서버 검증을 대신할 수 없음 | 제공자·서빙 리비전별 지원 계약을 명시. 실제 내부 모델 확인 없는 호환 선언 금지 |
| H03 이유와 실제 선택 불일치 | ADR0661은 기존 choices의 제외 이유가 채택으로 연결되는 문제를 출발점으로 함 | 이유를 남기는 목적과 명시적 채택 상태를 보존 | 선택을 명시 상태로 받고 실제 실행 receipt와 표시를 결속. 자유문장의 부정어로 상태 추정 금지 |
| H04 READ와 DEFER 충돌 | ADR0661/0663에서 같은 경로 READ_PARENT와 DEFER가 보정 뒤에도 함께 출력돼 실패 | 읽기 요청과 근거 채택은 다른 행위 | 이미 적용된 READ와 DECIDE 분리를 유지. 같은 원천의 허용 행동으로 메뉴·생성 형식·검증기를 구성 |
| H05 부분 교정의 성공과 한계 | ADR0664는 수정 필드만 반환해 성공. 이후 ADR0676은 sparse 수정이 행동·근거를 따로 바꾸는 문제를 기록 | 잘못된 원결정의 일부를 무심코 상속하면 안 됨 | 현재 control 경로의 전체 객체 교정을 기본 유지. 부분 교정은 8절의 좁은 별도 후보로만 검토 |
| H06 불가능한 메뉴·잘못된 근거 | ADR0665~0667에서 자동 채택, 미열람 제외, preview 근거, 행동/대상 분리 등을 수정 | 실제 읽음·모델 전달·채택·발행을 각각 증명해야 함 | 잘못된 조합을 모델에 제시하지 않고 같은 규칙으로 서버에서 재검증 |
| H07 oneOf·uniqueItems 호환 | ADR0668은 배타 행동 anyOf, ADR0670은 전송 사본에서 uniqueItems 제거로 해당 호출 수락 | 전송 제약 제거는 원래 검증 제거가 아님 | 의미 보존 변환과 제약을 서버로 옮기는 변환을 구분·기록. 서버 중복/범위 검증 필수 |
| H08 빈 화면의 DECIDE | ADR0696은 본문 없는 구조 메뉴에 DECIDE가 나타난 문제를 수정 | 행동이 현재 상태에서 실행 가능해야 함 | 빈 후보·자료 미전달·과거 자료만 존재하는 경우의 허용 행동 검사 유지 |
| H09 출력 길이·스트림 완료 | ADR0678은 HTTP200 length를 전송 장애로 오분류. 10월13일 현장 기록은 종료 사유와 DONE 처리 문제 | 수신 성공·출력 완성·판단 채택은 별개 | `OUTPUT_INCOMPLETE`, 공급자 거절, JSON 오류를 구분. 잘린 JSON을 이어 붙여 성공시키지 않음 |
| H10 재개와 반복 예산 | MAIN50 기록과 ADR0718/0723~0725에 stale retry, 동일 gap 반복, 부분 배치 재개 결함 | 같은 요청의 deadline·사용량·완료 receipt가 살아 있어야 함 | 이미 통합된 epoch/정확 대상/부분 재개를 보존하고 공통 복구 규약에 연결 |
| H11 다른 조문의 부재 증명 | MAIN50 기록은 다른 조문 읽기로 부족 대상을 NOT_AVAILABLE 처리한 사례 | 조사 실패나 무관한 자료는 대상 부재의 증거가 아님 | 실제 target·버전·범위·완료 receipt 검증을 필수 회귀 항목으로 유지 |
| H12 조건·예외의 구조 오류 | MAIN50 기록의 조건 ID/root 오류, ADR0702 예외 상태 모순, ADR0746 인용 재작성 문제 | AND/OR·조건·예외·원문 효과를 유지해야 함 | 현재 중첩 조건·서버 ID·v8 source_ref 방식을 보존. 모순을 없애려고 조건·예외를 삭제하지 않음 |
| H13 스키마 축소의 역효과 | ADR0729의 문법 문자 감소만으로는 ADR0730의 공개 판정 기준을 충족하지 못함 | 적은 글자 수가 적은 실제 토큰·높은 완료율을 보장하지 않음 | 새 간결 출력은 후보로 비교. 문자 수·토큰·완료·의미 회귀를 별도 평가 |
| H14 원문 부족과 사실 질문 | 10월13일 사진의 MISSING_SOURCE와 REQUEST_FACT 충돌. MAIN60 좁은 보정 반영 | 법령 확보를 사용자 사실 부족으로 떠넘기지 않음 | 기존 `source_gap_actions` 보존. MISSING_FACT의 법적 의미까지 자동 재분류하지 않음 |
| H15 이번 중복/공백 사유 | 10월14일 사진은 `duplicate branch or missing reason` → 판단 미확정 → 조사 미완료. 로컬은 두 원인 모두 재현 | 상충 결정의 임의 선택·빈 이유 창작은 금지 | 중복/공백/상충을 별도 코드·위치로 보고. 같은 항목당 한 판단을 생성하는 계약 후보 검증 |
| H16 AD·구축의 별도 경로 | AD에도 전송 uniqueItems 변환이 필요했던 인계 기록. PDF 후보의 구조 검사와 최종 검수 불일치 기록 | 공통 helper 수정만으로 모든 모델 경로가 바뀌지는 않음 | AD·참조 해소·PDF 검수의 실제 호출 경로별 적용/미적용을 추적 |
| H17 테스트/소비자 결함 | 과거 fixture가 최신 메뉴·SQL·응답을 가정하지 못함. 배선 누락으로 승격이 거절된 기록 | 단위 통과·화면 표시·실제 저장은 다른 증거 | 오래된 검사를 버리지 않고 보장하려던 행동을 현행 API 검사로 재작성. 동일 코드·pin 검사 필수 |

H15 사진의 두 원인 중 어느 것이 현장에서 발생했는지는 아직 미확정이다. 기존 완전 동일 중복 제거가 현장에서도 활성인지도 리비전 확인이 필요하다. 이 불확실성을 “중복을 더 넓게 지우면 해결”이라는 결론으로 바꾸지 않는다.

## 3. 바꾸지 않을 안전장치

| ID | 보존할 불변조건 | 이 조건을 만든 이유와 반례 |
|---|---|---|
| I01 | 원문 ID·버전·span·해시·ACL을 실행 전과 발행 전에 확인 | 문법상 ID가 맞아도 다른 팀·다른 판본·변조 원문이면 실행 불가 |
| I02 | 모델에 실제 전달된 원문과 단순 획득·preview를 구분 | 읽기 캐시·검색 카드만 보고 근거를 채택하는 문제 방지 |
| I03 | READ는 자동 ADOPT가 아님. DEFER/EXCLUDE는 의미 있게 유지 | 과거 제외 설명이 실제 채택으로 연결된 회귀 방지 |
| I04 | 필요한 명시 참조를 추적하고 미해결 범위를 표시 | 모든 링크를 강제 탐색하거나 필요한 예외·위임을 생략하지 않음 |
| I05 | 행동·target·허용 범위·현재 presentation·revision 결속 | 오래된 메뉴의 유효했던 ID도 현재 실행 권한을 뜻하지 않음 |
| I06 | 부족 대상은 정확한 문서·판본·범위에 결속 | 다른 조문 읽기·통신 실패·불완전 색인은 부재 증거가 아님 |
| I07 | 법률 의미와 사용자 사실은 모델 제안·검증 대상으로 유지 | 서버가 의무/허용, AND/OR, 적용 주체나 부족 사실을 만들어 채우지 않음 |
| I08 | 완전 동일 항목만 사전 허용 규칙으로 보정 | 같은 branch_id라도 상태·근거·쟁점·사유가 다르면 임의 병합 금지 |
| I09 | 한 결정의 모델 수정 담당은 한 곳, 총 예산은 요청에 종속 | gateway와 단계의 중첩 재시도·재시작 예산 초기화 방지 |
| I10 | 원제안·변경·거절·실행·발행 이력은 별도 보존 | 나중에 성공해도 실패 원문을 삭제하거나 승인 결과처럼 재기록하지 않음 |
| I11 | 이미 송신한 미완성 답변에 새 답변을 이어 붙이지 않음 | 사용자에게 보인 텍스트와 저장된 정본의 불일치 방지 |
| I12 | 실패·제한 답변·성공·재개 가능을 소비자까지 구분 | HTTP200/안내 문구 변경만으로 해결·성공 처리하지 않음 |
| I13 | 실패·부분 결과의 shortcut/wiki 승격은 기존 정책을 통과해야 함 | 실패를 빠른 성공 경로로 학습해 다음 요청에 전파하지 않음 |
| I14 | 구 계약과 과거 기록은 원래 버전으로 해석 | v5~v8 판단·이전 checkpoint에 새 의미를 소급 적용하지 않음 |
| I15 | 외부 공개·모의 검증과 GENOS 내부 검증을 구분 | 내부 질문·자료 반출 승인 확대와 외부 성능의 현장 전용 방지 |

## 4. 목표 구조와 실제 연결

기존 실행 순서와 저장소를 유지한다. 다음 `ContractSpec`, `DecisionBinding`, `ValidationIssue`는 **제안 이름**이며 현재 API가 아니다.

```text
기존 단계가 현재 view와 ContractSpec을 준비
  → 서버 소유 DecisionBinding을 원장에 고정
  → 요청별 handle과 공급자별 전송 스키마 생성
  → 기존 단일 전송과 물리 호출 원장
  → 완료 상태 확인 → 엄격 JSON 해석 → wire 검증/handle 복원
  → 안전한 객체 구조 확인·원래 위반 수집 → 허용 보정 → 전체 정본 구조 재검증
  → 필드 관계 → 원문/권한/버전 → revision/소비자 검증
  → 유효하면 기존 단계 commit → 최종 발행/표시
  → 실패하면 분류·한도에 따라 같은 단계에서 수정 또는 명시 종료
```

### 4.1 한 계약에서 파생시키되 검증 책임은 구분

`ContractSpec`에는 역할·버전, 정본 출력 구조, 모델이 작성할 필드, 서버에서 결속할 필드, 허용 메뉴 생성 규칙, 교차 필드 규칙, 보정 allowlist, 복구 담당, 소비자 버전을 둔다. 우선 기존 `decision_schema`, `assessment_schema` 등을 감싸는 명세와 검사로 도입한다. 모든 생성기를 한 번에 다시 쓰지 않는다.

동적 `offered-actions`는 현재 허용된 행동을 만드는 한 곳에서 산출한다. 모델 입력, 전송 스키마, 서버 validator는 같은 산출물의 hash와 버전을 참조한다. 원문 검증·ACL·commit CAS는 JSON 스키마 밖에 그대로 남는다. JSON 통과를 법률 의미 통과로 간주하지 않는다.

처음부터 정본 validator의 첫 예외로 종료하면 `uniqueItems`에 걸린 완전 동일 중복을 보정하지 못할 수 있다. 입력 크기·중첩 한도와 타입 안전성을 먼저 확인하고, 원래 위반을 기록한 뒤 해당 위반이 명시 allowlist에 속할 때만 순수 보정을 수행한다. 보정 후에는 정본 검사를 생략하지 않는다. 보정 불가 오류·권한/변조 실패는 이 경로로 우회하지 않는다.

### 4.2 모델이 작성할 것과 서버가 결속할 것

| 필드 성격 | 처리 |
|---|---|
| 검색어, 근거 선택, 채택/보류/제외, 판단 사유, 쟁점 연결, 조건·예외 의미 | 모델 작성. 원문·허용 집합·필드 관계 검증 필수 |
| 요청 ID, schema/메뉴 hash, principal, 데이터 세대, 원래 deadline, 물리 attempt, 소비자 계약 버전 | 서버 원장·호출 closure에서 결속. 모델 출력으로 덮어쓸 수 없음 |
| 제공 action handle에 유일하게 매핑된 tool kind·target identity | 서버가 검증된 메뉴에서 복원 가능. 자유 텍스트로 target을 추정하지 않음 |
| 원문 인용, norm source_ref의 실제 본문 | 현재 v8 receipt에서 복원·재검증. 모델이 인용문을 다시 작성하게 하지 않음 |
| 중첩 조건의 내부 노드 ID·root 연결 | 현재 코드 생성 유지. 모델이 선택한 ALL/ANY/UNKNOWN과 조건 본문은 보존 |
| coverage/disposition의 결정 가능한 일관성 | 기존 승인 계산·보정 범위 유지. 누락 gap을 제거하거나 미검증 claim을 만들어 충족시키지 않음 |

모델이 `expected_state_version`을 반복 출력하지 않는 후보를 만들더라도 stale 검증은 약화하면 안 된다. 응답을 수락하는 callback이 저장된 `DecisionBinding`과 현재 revision을 대조하고 commit 직전에 다시 확인한다. 이전 응답을 새 view로 재포장하는 동작은 금지한다.

### 4.3 출력 간소화 후보

첫 구현에서는 현재 객체를 유지하고 오류 분류·검증 정합성을 먼저 고친다. 그다음 다음 두 표현을 별도 동결 후보로 비교한다.

1. **현재 배열 유지 후보:** 행 수 상한, 공백 사유 검사, branch별 단일 결정 규칙을 명시하고 오류 위치를 구체화한다. 기존 codec·소비자 변경이 작다. JSON Schema의 `uniqueItems`만으로 branch_id 유일성을 보장할 수 없으므로 서버의 key 검증은 유지한다.
2. **항목별 객체 후보:** `branch_decisions`를 제공된 branch handle을 key로 갖는 닫힌 객체로 받고 각 항목에 판단을 한 번만 작성한다. 작성하지 않은 항목은 `NO_CHANGE` 의미이며 자동 DEFER·EXCLUDE가 아니다. 기존 소비자에게는 검증 뒤 원래 canonical 배열로 변환한다.

두 번째 표현의 합성 예시는 다음과 같다. 실제 wire 명세로 승인된 예시는 아니다.

```json
{
  "kind": "DECIDE",
  "branch_decisions": {
    "B1": {
      "status": "ADOPT",
      "issue_refs": ["Q1"],
      "basis_refs": ["E1"],
      "reason": "Q1의 요건을 설명하는 전달 원문이다."
    }
  },
  "reason": "읽은 원문을 현재 요구의 근거로 채택한다."
}
```

여기에는 선행 조건이 있다. 현재 `NavigationReferences`는 객체 key를 ID로 복원하지 않는다. **key 위치 전용 codec과 원시 JSON 중복 key 감지**를 함께 구현해야 한다. 일반 `json.loads`의 마지막 값 덮어쓰기를 이용해 중복을 숨기면 안 된다. reason·원문·일반 객체 key는 변환하지 않는다. 요청에 제공하지 않은 key, 같은 canonical ID로 복원되는 별칭 충돌은 거부한다.

공급자의 optional properties 지원·문법 크기·빈 메뉴·큰 메뉴·동적 key 지원을 해당 모델로 확인한 뒤만 두 번째 표현을 선택한다. 지원이 부족하면 검증된 첫 번째 표현을 릴리스에서 명시 선택한다. 실패 요청 중간에 표현이나 모델을 몰래 바꾸지 않는다. **모든 요청에 행동 선택용 모델 호출을 하나 더 넣는 2단계 생성은 기본안에서 제외**한다.

## 5. 오류 분류와 단일 복구 담당

| 제안 분류 | 예 | 복구 담당·행동 | 실행/저장 경계 |
|---|---|---|---|
| REQUEST_SCHEMA_UNSUPPORTED | 공급자가 지원하지 않는 키워드·복잡도 | 어댑터의 검증된 projection을 배포 전에 확정. 실행 중에는 운영 오류로 기록 | 같은 요청의 무작위 스키마 완화·모델 fallback 금지 |
| OUTPUT_INCOMPLETE | length, 정상 종료 없는 불완전 출력 | 해당 단계. 실제 종료/usage/상한을 분리 기록; 허용된 단일 재작성만 | 부분 JSON을 실행하지 않음. content_filter/거절은 정책에 맞게 별도 종료 |
| OUTPUT_JSON_INVALID | 구문, 중복 key, 비표준 수치 | 해당 단계 또는 gateway 중 사전 지정한 한 곳 | 근거·필수 필드 추정 보충 금지 |
| OUTPUT_SHAPE_INVALID | 타입·required·enum·추가 필드 | 역할별 정본 schema와 필드 경로로 교정 | 미지 enum의 유사값 치환 금지 |
| DECISION_CONFLICT | 중복 branch, READ/DEFER, 공백 사유 | 탐색/판단 담당 단계. 허용 보정 후 또는 같은 view로 수정 | 다른 근거·상태·쟁점을 임의 병합하지 않음 |
| EVIDENCE_CONTRACT_INVALID | 다른 branch 근거, preview 인용, 잘못된 span | 단계에서 오류가 난 선택을 수정 가능하되 허용 집합은 동일 | 출처 변조·ACL/세대 문제와 분리. 실패 선택을 채택하지 않음 |
| STATE_OR_BINDING_INVALID | stale revision, principal/model/hash 불일치 | 상태/실행 소유자. 모델 수정 호출 없음 | 결과 차단, 이력·checkpoint 유지 |
| TOOL_OR_TRANSPORT_FAILURE | 일시적 도구 장애, 429, 결과 불명 | 물리 전송은 gateway, 도구 복구는 기존 도구 소유자 | 확실한 미수락·멱등 조건만 제한 재시도. unknown을 실패 전 미실행으로 간주하지 않음 |
| PUBLICATION_FAILURE | 저장 충돌, 송신 후 실패 | 기존 발행 소유자 | 같은 검증 결과의 멱등 발행만 복구. 새 답변 덧붙이기 금지 |
| IMPLEMENTATION_FAILURE | 내부 TypeError/KeyError, fixture 불일치 | 코드/검사 담당 | 모델 출력 오류로 포괄 처리해 재시도하지 않음 |

`ValidationIssue`의 제안 필드는 `code`, `path`, `related_paths`, `rule_id`, `stage`, `subject_handle`, `repairability`, `expected_constraint`, `binding_hash`다. 내부 원본 ID·자료는 원장에 남고 모델 교정에는 같은 요청의 허용 handle만 쓴다. 예를 들어 현재 단일 문구를 `DUPLICATE_BRANCH_DECISION`의 두 배열 위치와 `BLANK_DECISION_REASON`의 reason 위치로 분리한다. 서로 다른 판단은 `CONFLICTING_BRANCH_DECISIONS`로 구분한다.

구문/타입이 깨진 객체에는 후속 필드 검사를 무리하게 수행하지 않는다. 안전하게 검사 가능한 독립 충돌은 한 번에 수집하되, anyOf의 모든 가지 실패 문구를 그대로 보내지 않는다. 선택한 discriminant와 관련 필드의 최소 원인을 보낸다. 권한/변조 오류 뒤에는 추가 정보가 새지 않도록 중단한다.

기존 `ProposalError` 등 예외와 공개 오류 코드는 초기 이행에서 유지하고 내부 diagnostics만 버전으로 확장한다. `investigation_diagnostics`, `readable_log`, `request_report`, AD 보고서가 새 필드를 읽도록 함께 연결한다. 알려진 입력 검증만 typed validation 오류로 만들고 코드 버그를 잡는 포괄 `except`를 추가하지 않는다.

## 6. 보정 allowlist와 원장

현재 보정 규칙을 보존하고 추가 규칙은 각각 이름·버전·입출력 불변조건·반례 검사를 갖춘다.

| 허용 범위 | 동작 | 금지 범위 |
|---|---|---|
| 완전 동일한 중복 행 | 현재 `deduplicate_decision` 유지; 원본 보존, 제거 hash 기록 | 사유만 다름, 서로 다른 근거·쟁점·판본, ADOPT/EXCLUDE 충돌의 합치기 |
| 같은 요청의 가역 handle | 정확한 mapping으로만 복원 | 부분 문자열 검색·다른 view ID 재사용·숫자/법령 조문 변환 |
| 명시 source_ref의 원문 복원 | v8의 검증된 receipt 사용 | 비슷한 문구 인용, 원문 요약을 정확 인용처럼 처리 |
| 원문 gap의 REQUEST_FACT | 기존 `source_gap_actions`가 보존하는 gap을 RESEARCH로 연결 | source/fact 자체를 의미 추정으로 변경, gap 삭제 |
| 파생 상태·구조 메타데이터 | 기존 승인 경로의 보수적 coverage, 조건 내부 ID 생성 | 법적 요건의 AND/OR 변경, 예외 없음 단정, 사용자 사실 창작 |

보정은 순수 함수이며 입력을 바꾸지 않는다. `raw_proposal_hash → normalization_rules/changes → normalized_hash → validation → committed_hash`를 기존 event/model_attempt 저장에 연결한다. 같은 보정의 재적용은 변화가 없어야 한다. 전체 응답을 보고서마다 복제하지 않고 원장 경로·hash를 참조한다.

공백 사유는 값을 만들어 채우지 않는다. 길이가 긴 사유·답변·원문을 `maxLength`에 맞춰 잘라내는 방식도 사용하지 않는다. 길이 상한과 필요 내용이 충돌하면 생성할 불필요 메타데이터를 줄이거나 동일 의미의 재작성을 요청하며, 필수 원문·요건·예외는 유지한다.

## 7. 재시도·재개·부분 성공 계약

### 7.1 현재 책임을 보존해 명시화

| 경로 | 현재 확인 | 목표 |
|---|---|---|
| 탐색 | `bounded_source_session.structured`의 gateway schema repair 0, `Investigation.request_decision`이 교정 1회 | 동일 담당 유지. 구조화 오류·보정과 영속 예산을 연결 |
| ASSESS | `CompletionExecution` 최초+교정 1회; gateway 중복 교정 차단 | v5~v8별 준비/검증을 보존하며 같은 결정의 owner를 고정 |
| 명시 참조 선택 | `unit_relations._navigate`가 후검증 실패를 1회 재판단하고, `source-reference-*`는 탐색의 gateway repair 0 override에 포함되지 않음 | 원래 객체·필드·scope·적용 여부 검사 전체를 한 owner로 묶고 gateway의 동일 결정 교정을 끔. 최초 invoke도 같은 복구 경계에서 처리 |
| COMPOSE | rich narrative 검증·송신 경계가 별도; ASSESS와 같은 복구 루프라고 볼 수 없음 | 실제 writer/stream owner를 목록화. 이미 송신한 경우 새 생성 연결 금지 |
| 기타 RAG 역할 | gateway validator와 단계 후검증이 공존 | 역할마다 담당을 확정. 도메인 후검증이 필요한 역할은 한 담당으로 이전 후 내부 교정을 끔 |
| AD | context 조회 반복 한도는 존재하나 실패한 plan의 schema repair 루프가 아님 | 해석 교정을 context 조회와 분리하되 총 호출·lease는 공유; 검증 전 SQL 쓰기 금지 |
| 참조 해소·PDF | ReferenceGateway, recipe/window 검수 등 별도 owner가 있음 | RAG 횟수의 일괄 적용 없이 기존 문서/배치 예산과 복구 담당을 명시 |

교정 수의 제안 기본은 **한 논리 결정당 1회**이며 기존 단계보다 자동으로 증가시키지 않는다. 총 물리 호출·도구 사용·deadline은 기존 요청 예산에서 차감한다. 새로운 조사 행동은 교정과 구분하지만 새 대상 또는 새 근거가 있어야 하며 전체 예산을 초기화하지 않는다.

명시 참조 경로는 단계 호출 두 번에 각 gateway 형식 교정이 한 번씩 허용되는 조합이면 `2 × (1 + 1) = 4`회까지 가능하다(전송 재시도 제외, 코드상 조건부 계산). 이번 사진에서 네 번 호출됐다는 뜻은 아니다. 기존 wire 교정이 후속 필드 오류를 고칠 기회를 소모하는 문제를 포함해 하나의 결정 예산으로 검증한다.

### 7.2 영속 복구 식별자

기존 `decision_identity(epoch, phase, presentation_id, input_hash)`와 요청 journal을 확장해 schema/codec/메뉴 hash·복구 owner·소비한 교정 횟수를 함께 결속한다. 코드·데이터·principal·원래 deadline은 요청 binding에서 참조한다.

다음 구간을 각각 실패 주입한다: 예약 전, 호출 예약 후 전송 전, 전송 결과 불명, 응답 저장 후 검증 전, 교정 성공 저장 후 단계 commit 전, 도구 일부 완료, 발행 저장 후 화면 송신 전. 예약 후의 crash는 receipt 없다고 자동 재호출하지 않는다. 기존 실행 결과 확인·중복 안전성이 없는 경우 unknown으로 보존하고 중단한다.

같은 요청 재전달은 같은 결과·예산을 사용한다. 같은 request_id에 다른 입력·principal·binding이면 충돌이다. 새 사용자 요청은 기존 세션의 원문·판단을 힌트로 쓸 수 있지만 과거 미완료를 성공으로 취급하지 않는다. 새 요청과 단순 resume를 구분해 기록한다.

### 7.3 최종 상태

검증된 근거·판단이 있는 경우만 기존 제한 답변 경로를 사용한다. 일부 판단을 살리는 경우 해당 주장과 연결된 조건·예외·쟁점·gap의 의존 묶음이 함께 검증돼야 한다. 실패 객체에서 좋아 보이는 문장만 골라 발행하지 않는다.

현재 `bounded_result`는 채택 원문 또는 실제 전달 원문으로 후속 판단을 할 수 있다. 이 기능을 새로 만들거나 모든 READ를 채택하는 기능으로 바꾸지 않는다. `adoption_fallback`, DEFER/EXCLUDE, 전달 receipt, 아직 미확인인 범위를 그대로 검증한다. 근거가 없으면 명시 실패/미확정, 실제 사건 사실이 필요하면 구체 사실 질문, 실제 checkpoint가 있을 때만 재개 가능을 표시한다.

## 8. 부분 교정과 출력 길이의 특별 취급

### 8.1 부분 교정은 조건부 후속 후보

현재 control 경로는 `correction_schema`가 전체 결정을 요구한다. ADR0664의 성공만 근거로 sparse patch를 다시 활성화하지 않는다. 우선 전체 결정 재작성으로 오류 안내를 개선한다.

후속으로 검토한다면 원제안이 정본 구조를 통과하고, discriminant·action·target·메뉴·state revision이 동일하며, 교체 범위가 의존 묶음 전체일 때만 허용한다. 예를 들어 단일 branch 행을 고치더라도 그 행의 상태·근거·쟁점·사유를 한 객체로 교체해야 한다. 행동 종류나 FINISH 여부가 바뀌면 전체 객체를 재작성한다. patch 삭제/중복 지정/알 수 없는 위치는 거부하며, 적용 후 모든 검증을 다시 실행한다. 이 기능은 교정 한도를 늘리지 않는다.

### 8.2 길이 오류

입력 크기 초과, 요청의 출력 상한 도달, 종료 원인 미상, content filter, 스트림 프레이밍 실패를 나눈다. 실제 usage가 없으면 토큰을 문자 수로 환산해 확정하지 않는다. GENOS의 context limit은 확인된 서빙 설정만 사용한다.

먼저 반복 ID·서버 메타데이터·중복 스키마·불필요 설명을 줄인다. 원문 인용·사용자 요구·예외를 누락시키는 자동 축약은 금지한다. 상한 변경은 알려진 모델 한도와 총 예산 안에서 사전에 정의한 정책으로만 한다. 모든 실패에 max_tokens를 무조건 늘리거나 같은 길이의 실패 요청을 반복하지 않는다. 분할 처리가 필요한 경우 각 조각의 처리 범위·누락·완료 상태와 최종 원자적 채택을 설계한 별도 후보로 검증한다.

## 9. 파일별 변경 지도와 이행

아래 파일은 별도 표시가 없으면 `02_BACKEND/semantic_runtime/legal_agent/` 기준이다. 제안 신규 모듈은 기존 계층 내부에만 두며 별도 실행기를 추가하지 않는다.

| 변경 지점 | 구현할 책임 | 소비자·이행 |
|---|---|---|
| `law_navigation.decision_schema/validate/repair_contract/request_decision` | 중복/공백/상충 진단, 동일 메뉴에서 형식·검증 파생, 교정 owner | 기존 SELECT 결과와 investigation checkpoint; canonical 출력 우선 유지 |
| `request_repair.deduplicate_decision/decision_identity`, `completion_budget` | 보정 감사, 동일 결정·예산·재개 결속 | 기존 SQL event와 checkpoint, 재개 버전 검사 |
| `navigation_input.NavigationReferences`, `numbered_references`, `relations_repository.reserve_attempt` | 요청별 codec과 왕복 검사; 객체 key 후보는 명시 위치만 확장 | 원장에서 재구성한 mapping과 실제 wire view 대조를 함께 버전 변경 |
| `model_contract`, `wire_schema`, `local_gemma`, `transport`, `model_stream` | 완료·JSON 분류, 공급자 projection, actual payload 계측 | 법률 RAG·AD 공유 경로와 외부 adapter; 내부/외부 설정 분리 |
| `gateway.ModelGateway.request/generate` | typed validation 오류, repair owner, 물리 예산, stale 응답 차단 | `bounded_source_session.structured`, reference gateway, 다른 protocol 소비자 |
| `request_entry`, `investigation_contracts`, `source_selection`, `unit_relations.schema/validate/_navigate` | 역할별 허용 메뉴·후검증·담당 목록 | INTENT·SELECT·명시 참조 흐름. 별도 의미 규칙은 유지 |
| `completion_execution`, `completion_contracts`, `completion_v5`~`completion_v8` | gap/coverage/사실/조건 검증 진단 정합성 | 현재 v8 기본과 v5~v7 과거 reader/재사용; 기존 보정·정본 유지 |
| `corrected_memory`, `repository`, `unified_runtime` | 검증·상태 commit 경계, 중복 요청·중단 복원 | 현재 request/goal/stage/attempt 원장. DB 변경 시 버전 이행 필요 |
| `narrative_answer`, `answer_stream`, `unified_publication`, `shortcut_cases` | 검증된 주장·송신·발행·재사용 상태 일치 | API, chat, workflow, shortcut/wiki; 실패를 성공 캐시에 넣지 않음 |
| `investigation_diagnostics`, `readable_log`, 상위 `request_report`/`app` | root cause부터 최종 상태까지 같은 식별자 | 기존 공개 안내는 간결하게 유지; 운영 보고서에는 상세 원인 |
| 상위 `ad_model`, `ad_language`, `ad_store`, `ad_request_report` | AD plan 실패 분류와 단일 교정·내부 모델·lease 검증 | 기존 닫힌 SQL 실행기와 AD consumer; 공개 모델 대체 금지 |
| `lawrag/pipeline/reference_resolution`, `semantic_runtime/reference_resolution_protocol` | 참조 observation·권한·후보 집합 검증과 복구 | 기존 batch journal·새 generation; 승인 정책을 조용히 변경하지 않음 |
| `lawrag/core/llm`, `structure/recipe_runtime`, `recipe_output`와 실제 window owner | 숨은 문법 fallback·물리 호출 계수·완료/검수 계약의 명시화 | 모델 검토 구축만 대상. 기본 모델0 구축·원문 불변성 유지 |
| `workflow_tiers_policy.profile`, `law_candidates.validate_policy`, 선택 엔진 manifest, `PIPELINE.json`, release manifest | contract/codec/validator 버전과 코드 pin 연결 | profile은 현재 코드가 unknown key와 enum을 거절. 새 설정은 이 validator와 선택 프로필을 함께 버전 이행 |

새 wire가 기존 canonical 상태로 무손실 변환되는 초기 변경은 원문·용어집·색인 재구축을 요구하지 않는다. 반면 checkpoint·event·cache key가 바뀌면 해당 runtime 계약 버전과 이행이 필요하다. 저장 판단의 법률 의미가 바뀌는 변경은 이 계획의 형식 개선과 분리한다.

구 checkpoint는 원래 코드/계약으로 완료시키거나 이력 보존 후 새 요청으로 명시 재시작한다. 구 상태를 새 버전으로 자동 라벨 변경하지 않는다. 부분 배포 중 한 요청이 두 codec/validator를 섞어 쓰지 않게 시작 binding을 고정한다. cache key에는 계약·codec·모델·권한·source binding을 포함하며, 과거 캐시는 삭제보다 새 namespace로 분리한다.

## 10. 검증 계획

### 10.1 과거 사건을 회귀 자산으로 만들기

원본 요청·응답·선택 코드/데이터/프로필·schema·오류·교정·최종 상태를 하나의 사건 ID로 연결한다. 같은 요청의 최초 실패와 수정 실패를 별도 사용자 요청으로 중복 집계하지 않는다. 사진만 있는 사례는 `PHOTO_ONLY`, 코드 재현은 `SYNTHETIC_REPRO`, 과거 원장은 `HISTORICAL_RUN`, 현재 실제 API 확인은 `CURRENT_API`로 구분한다.

원본은 바꾸지 않고 test fixture는 별도 hash·출처 참조로 생성한다. 내부 자료가 포함된 원본은 해당 환경에서만 사용한다. 외부용 fixture는 명시적 합성 데이터이며 원본의 법률 의미·현장 품질 검증을 대신하지 않는다. 이미 본 실패 사례는 회귀 세트이며 holdout이 아니다.

### 10.2 필수 검사 행렬

| 검사군 | 반드시 확인할 행동 | 보존 대상 |
|---|---|---|
| 정상·빈 메뉴·최소/큰 메뉴 | 유효 출력 수락, 추가 정상 모델 호출 없음, 불가능한 도구 미제시 | I02~I05 |
| 중복·공백·상충 | 정확 중복만 무호출 보정; 다른 사유/근거/쟁점/상태는 정확 진단·제한 교정 | I07~I10 |
| JSON·별칭 | 중복 JSON key, unknown handle, alias collision, 숫자/본문 변환 없음 | I01/I05/I08 |
| schema projection | canonical과 전송 표현의 동등/상위집합 관계를 명시; 제거한 제약은 서버에서 거부 | I01~I05 |
| READ·참조·FINISH | preview 채택·미열람 제외·cross-group scope·무근거 FINISH 차단 | I02~I06 |
| 조건·예외·사실·gap | AND/OR/UNKNOWN·효과·사용자 사실 유지; source gap을 사실 질문으로 바꾸지 않음 | I06/I07 |
| 재시도 성공/실패/예산 | 최초+허용 교정만 실행; 오류 종류 변경·새 임의 ID로 예산 초기화 불가 | I09/I10 |
| 중단·재개·동시성 | 최초 deadline·physical counts·완료 receipt 유지, stale CAS 거부 | I05/I09/I14 |
| 부분 도구 성공 | 완료된 target 재실행 방지, 실패 target은 미확정, 부재 판정 금지 | I06/I09 |
| 스트림 | DONE/EOF/length/filter/빈 content/unknown 완료 구분, 송신 후 실패에 대체답변 연결 금지 | I11/I12 |
| 발행·재사용 | 저장 실패 뒤 성공 화면 금지, 제한/실패 shortcut·wiki 오승격 금지 | I10~I13 |
| AD | 미검증 명령 실행0, 범위/owner/lease/CAS 유지, context 조회·교정 총예산 공유 | I01/I05/I09 |
| 구축 | 문서/창별 검수 책임, 원문·좌표 보존, 부분 검수로 전체 승인 금지 | I01/I10/I14 |
| 버전·배선 | v5~v8와 실제 사용 protocol별 검사, 같은 pin의 API·저장·표시 일치 | I12/I14/I15 |

`test_main50_request_repair`, `test_completion_boundary_adr0679`, `test_model_decision_repair`, `test_genos_wire_schema`, `test_genos_model_stream_completion`, `test_navigation_input_compaction`, `test_native_completion_consumer_adr0680`, `test_unified_memory_recovery`, AD·발행 관련 기존 검사를 출발점으로 삼는다. 전체 경로의 최신 검사 목록은 구현 시작 시 actual imports로 확정한다.

앞선 이번 사진 진단에서 관련 검사 6개는 통과했고 구 검사 1개는 `articles` 입력을 기대하는 fixture 때문에 실패했다. 이것을 제품 장애가 해결됐거나 전체 회귀가 통과했다는 증거로 쓰지 않는다. BL-010의 기존 복구4개 실패도 원래 의도를 현행 API에서 검증해야 한다. 기존 실패와 신규 실패를 분리하지만 새 변경의 필수 경계 검사가 실패하면 “원래 실패”를 이유로 면제하지 않는다.

### 10.3 실제 모델 검증

형식·프롬프트·모델 효과 비교는 새 ADR을 선점하고 두 표준 문서를 끝까지 읽은 후 실행한다. 현재 MAIN과 구현 후보를 동일 source/profile/budget 조건으로 묶고, 바꾼 단계 외에는 고정한다. 후보 구현·호출 전에 reservation, 정확한 부모 arm, snapshot/register/freeze를 완료한다. 결과를 본 뒤 만든 후속 후보는 새 ADR로 분리한다.

검증은 단계별로 나눈다: 합성 결정론 계약 → 공급자 문법/codec 호환 → 과거 실패 회귀 → 새 공개 질문 비교 → 같은 코드의 실제 로컬 서비스 → GENOS 내부 워크플로우. 별도 성능/정답 비교와 역사적 로그 재평가는 모두 ADR 범위다. 이번 설계에서는 실행하지 않는다.

외부 모델은 현행 정책의 Qwen3.8 / `qwen/qwen3.8-27b`, OpenRouter Parasail FP8, reasoning none, fallback 없음이다. 공개 승인 source 범위를 확인한다. `risk_cm` 105문항은 question_only이며 외규 표시·기존 질문 존재를 외부 반출 승인 또는 미사용 holdout의 증거로 쓰지 않는다. GENOS 내부 모델 결과는 별도로 측정한다.

### 10.4 통과 기준과 지표

| ID | 구분 | 기준·분모 |
|---|---|---|
| T01 | 목표 | 선언한 계약 행렬의 각 정상/복구/중단 검사 통과. 미검사 항목을 통과로 세지 않음 |
| T02 | 목표 | 동결 검증 범위에서 새 권한·인용·해시·상태·잘못된 실행/발행 위반 0건 |
| T03 | 목표 | 정상 동등 입력에 계약 공통화 자체가 추가하는 모델 호출 0회. 의미상 필요한 추가 조사는 별도 기록 |
| T04 | 목표 | 재개·중복 요청에서 허용 교정 및 물리 예산 초과 0건 |
| T05 | 목표 | 알려진 중복·공백·행동/상태 오류를 독립 코드와 위치로 식별. 원인 불명은 unknown으로 유지 |
| T06 | 목표 | 동일 코드·profile·schema/codec·source binding으로 후보/작업/선택 릴리스/API 일치 |
| T07 | 목표 | 비교에서 정상 완료를 미확정/부분 답변으로 바꿔 형식 오류만 감소시키는 회귀를 숨기지 않음. 알려진 필수 정상 사례의 새 실패는 수정 후 검증 |
| N01 | 조건부 계산 | 참조 선택의 단계 호출2 × (각 최초1 + gateway 형식 교정1) = 물리4회 가능. 전송 재시도 제외, 실측 아님; owner 통합 검사로 검증 |
| M01 | 관측 예정 | 최초 계약 실패 결정 수 / 전체 논리 결정 수, 역할·오류 종류별 |
| M02 | 관측 예정 | 교정 후 유효 결정 수 / 교정 시도한 결정 수. 자동 보정·미시도·예산 소진을 별도 집계 |
| M03 | 관측 예정 | 최종 성공·제한·사실질문·실패 / 사용자 요청 수; 같은 요청의 교정 횟수를 분모로 섞지 않음 |
| M04 | 관측 예정 | 실제 physical calls, provider input/output usage, 요청 wall time과 p50/p95, 비용. 실패 포함/정상 쌍을 둘 다 제시 |
| M05 | 관측 예정 | 조건·예외·적용대상·요구 누락·인용 의미 오류. 실행 성공/정확 인용과 별도 판정 |
| U01 | 미산정 | 전체 오류 감소율·GENOS 성공률·절감 비용·개발 인일·달력 일정. 대표 로그·내부 모델 측정 후 산정 |

세부 법률 정답100%를 새 MAIN 필수 조건으로 추가하지 않는다. 일반화 부족·의미 판단 오류는 별도 원장과 후속 ADR로 다루며, 심각한 권한·인용·상태·실제 배선 문제는 계속 차단한다. 구체 표본 수, 통계 기준, 허용 의미 회귀, 지연·비용 한도는 표본·baseline을 정한 뒤 **첫 호출 전에** 동결한다. 빈 기준으로 실행/승격을 시작하지 않는다.

`순 호출 절감 = 제거된 중복 교정·무진행 호출 − 새로 필요한 교정·조사 호출`이다. `시간 절감 = 기존 요청 시간 − 후보 요청 시간`으로 같은 환경의 쌍에서 계산한다. 동적 schema 컴파일·JSON 검사 비용도 포함한다. 손익분기는 없어진 낭비와 추가 정당한 처리 비용이 같을 때다. 객체 key 수가 큰 schema는 입력 비용을 늘릴 수 있고, 상세 오류를 너무 많이 보내면 교정 출력도 길어질 수 있다. 문자 수 절감을 토큰/시간 절감률로 바꾸지 않는다.

### 10.5 기존 검사에서 이어갈 위치

아래는 후속 구현의 검사 진입점이며 이번 설계에서 새로 실행한 결과가 아니다. 이름에 과거 ADR이 있어도 현행 경로를 검증하는지 먼저 확인한다.

| 현재 검사 | 확장·보존할 책임 |
|---|---|
| [test_main50_request_repair](../../../../05_TESTS/CONTRACTS/test_main50_request_repair.py), [test_law_navigation_one_repair_adr0663](../../../../05_TESTS/CONTRACTS/test_law_navigation_one_repair_adr0663.py) | 완전 동일 중복만 보정, 같은 presentation 교정 예산, 중단 후 재개. 구 fixture는 보장 행동을 유지해 갱신 |
| [test_completion_boundary_adr0679](../../../../05_TESTS/CONTRACTS/test_completion_boundary_adr0679.py) | length/filter와 권한·binding 구분, 단일 전체 교정, source/fact 경계 |
| [test_navigation_input_compaction](../../../../05_TESTS/CONTRACTS/test_navigation_input_compaction.py), [test_genos_wire_schema](../../../../05_TESTS/CONTRACTS/test_genos_wire_schema.py) | 원문·허용 집합·스키마 의미 보존. 제안 key codec·중복 JSON key·별칭 충돌 검사는 추가 필요 |
| [test_batch_reference_navigation](../../../../05_TESTS/CONTRACTS/test_batch_reference_navigation.py) | 명시 참조의 원래 scope/도구 검사와 추가할 단일 교정 owner·실제 gateway 호출 계수 |
| [test_unified_memory_recovery](../../../../05_TESTS/CONTRACTS/test_unified_memory_recovery.py) | 기존 실패 4개의 재개·발행·재사용 의도를 현행 저장·소비자에서 검증 |
| [test_source_span_norm](../../../../05_TESTS/CONTRACTS/test_source_span_norm.py), [test_ad_language](../../../../05_TESTS/CONTRACTS/test_ad_language.py), [test_recipe_output](../../../../05_TESTS/REGRESSION/core/test_recipe_output.py) | 원문 인용, AD 명령, 구축 검수의 고유 계약 유지 |

첫 탐색·교정 수정 뒤의 로컬 검사 예시는 다음과 같다. 이 묶음만으로 전체 계획을 통과 처리하지 않으며 AD·구축·실제 서비스 검사는 변경 범위에 맞게 별도로 연결한다.

```bash
.venv/bin/python -m pytest -q \
  05_TESTS/CONTRACTS/test_main50_request_repair.py \
  05_TESTS/CONTRACTS/test_law_navigation_one_repair_adr0663.py \
  05_TESTS/CONTRACTS/test_completion_boundary_adr0679.py \
  05_TESTS/CONTRACTS/test_batch_reference_navigation.py
```

## 11. 구현 순서와 완료 조건

| 순서 | 구체 작업 | 완료 산출물·다음 단계 조건 |
|---|---|---|
| P0 기준선과 사건 원장 | 관련 진행 reservation 확인, 실제 선택 코드/데이터/프로필/서비스 binding 기록, 역할별 schema/validator/owner/소비자 목록, 과거 사건과 guard를 매핑 | 사건 목록·불변조건·검사 분모와 미확인 목록. 이미 된 수정을 새로 구현하지 않음 |
| P1 진단·계약 정합성 | 이번 중복/공백부터 typed 오류·독립 충돌 수집·정본 검증 순서 연결. 숨은 코드 오류 분리 | canonical 행동을 바꾸지 않는 검사, root cause가 최종 보고서까지 유지 |
| P2 생성 예방 | 효과 비교가 필요한 후보는 구현 전에 ADR 예약·기준 동결. 허용 메뉴·schema 정합성, 서버 메타데이터 결속, 배열/객체 후보의 codec·JSON 중복키·provider 계약 | 기존 보호 규칙을 통과하는 격리 후보. 무단 scope 확대·근거 누락 없음 |
| P3 복구·재개 | 단계별 owner 명시, 영속 교정 카운터, 상태별 crash/동시성, 제한 답변·발행·shortcut 연결 | 실제 API/저장 소비자에서 실패 행렬 통과. 무한 재호출·중복 쓰기 없음 |
| P4 AD·구축 적용 | AD와 reference/recipe 실제 모델 경로에 공통 진단·projection·owner 계약 연결 | 관리 명령/자료 검수 고유 규칙과 기존 모델0 경로 보존. 적용되지 않은 역할은 명시 |
| P5 분리 검증 | 후보 구현 전 예약·동결한 ADR에 따라 과거 회귀와 새로운 독립 사례 비교. P3/P4에서 추가 효과 비교가 필요하면 해당 후보 착수 전 별도 예약 | 결과·일반화 오류·미실행을 별도 기록. 실패 후보를 사후 수정하지 않음 |
| P6 작업 통합·로컬 MAIN | 최신 작업과 후보를 파일별 통합, 같은 코드·pin으로 재검증, 표준 promotion plan/check/apply | 선택 포인터 및 실제 새 로컬 `service.service`의 HEALTH/검색/질의·로그·저장 확인 |
| P7 GENOS 인계·검증 | 실제 설치 inventory에 맞는 코드/의존성/설정·검사·원복 패키지, 기존 checkout 적용, commit/push, 새 리비전·SSE 재시작 | 워크플로우 테스트 화면에서 내부 모델 정상/실패/재개/표시 확인. 현장 적용 상태를 별도 기록 |

P1의 좁은 진단 수정만 먼저 배포할 수 있으나 그때는 “진단 개선”으로 보고한다. 전체 수정 완료는 P2~P7의 선언한 범위·실제 소비자 검증까지 충족한 상태다. 설계 단계에서 기존 릴리스나 과거 ADR의 통과 기준을 바꾸지 않는다.

실험 최종에는 stable runner의 `adr_structure.py validate --final`과 `graph`를 실행한다. 승격은 Accepted·out-of-sample·decision_eligible·complete인 결과와 hash 고정 `rag_main_promotion.py`의 명시적 `--confirm-main` 절차를 따른다. 과거 전역 graph 오류가 기록돼 있어도 최신 상태를 재검사하고 자동 면제하지 않는다.

GENOS 인계 시 ZIP과 실행 TXT는 사용자가 실제 업로드한 `TRANSFER`를 현재 위치로 둔 상대경로로 안내한다. 현장 명령은 `python3`이며 적용 대상은 기존 `~/DEV`다. ZIP을 풀기 위해 먼저 DEV로 이동시키지 않는다. 구체 파일명은 패키지를 실제 봉인할 때 확정한다. 워크플로우 소비자 변경이 있으면 코드 배포와 별도로 편집기 TXT 반영이 필요하고, 변경이 없으면 불필요한 편집기 교체를 요구하지 않는다. 현장 질의·warmup은 워크플로우 테스트에서만 확인한다.

## 12. 롤백과 완료 보고

새 binding 불일치, 원문·권한·상태 위반, 중복 실행, 실패의 성공 발행, 실패 자료의 shortcut 승격이 확인되면 해당 후보 선택을 중지하고 이전 검증 릴리스로 되돌린다. guard를 끄거나 동일 hash를 새 파일에 다시 쓰지 않는다.

코드·프로필·schema·codec·consumer를 함께 되돌린다. 진행 중 요청은 시작한 버전으로 완료시키거나 checkpoint 보존 후 명시 중단하며, 구 코드가 새 상태를 읽도록 강제하지 않는다. 필요한 DB 변경은 additive 또는 읽기 버전 분리로 설계하고, 되돌릴 수 없는 destructive migration은 이 계획의 기본안에 포함하지 않는다. 원문·완료 세대·실패 원장·과거 릴리스는 보존한다.

완료 기록에는 사건별 해결/잔존 상태, 실제 검사 결과, 의미 오류, 물리 호출/지연, 작업 코드↔검증 후보↔선택 릴리스 지문, 실제 서비스 binding, GENOS 적용/미확인 범위를 적는다. Git main 병합·ADR 완료·데이터 CURRENT·로컬 MAIN·GENOS 배포는 각각 따로 보고한다.

자체 검토의 발견사항과 구현 선행 조건은 [REVIEW.md](REVIEW.md)에 남긴다. 이 계획은 기존 안전장치의 이유를 회귀검사와 변경 책임으로 고정한 설계이며, 실제 코드의 해결 여부는 이후 검증으로 판정한다.
