# 수용 시나리오와 회귀 검사 명세

상태: **미실행 테스트 명세**. 문서 정적 검증은 이 사례들을 실행한 결과가 아니다. 구현 시 계약 fixture와 실제 모델 품질 평가를 구분한다. 표의 정답/예외는 합성 fixture 또는 제품 종료 후 결합할 평가 자료이며 제품 힌트로 주입하지 않는다.

| ID | 입력·실패 조건 | 기대 동작/검사할 실제 산출물 | 분류 |
|---|---|---|---|
| A01 | 정확한 문서·조번호 질문 | locate→read→검토로 완료 가능, browse 호출 0도 정상 | 선택 자유 |
| A02 | 어떤 자료가 있는지 질문 | browse ROOT가 허용 문서/폴더만 반환, metadata 답변, 법률 claim 없음 | 목록 |
| A03 | 읽은 조문이 이해 안 되지만 문서는 유망 | E에서 document outline 조회, 큰 헤딩/조만 표시, 다른 U 읽기 | 주변 탐색 |
| A04 | 편/장/절/조/항/호 및 일반 section fixture | children은 직접 자식, outline은 정의된 큰 단위, tree는 depth 준수 | 계층 |
| A05 | 같은 이름의 부칙 제1조·별표·복수 판본 | branch/판본/부모 구별, 임의 하나 선택 안 함 | 좌표 |
| A06 | 제한 없는 일반 질문에서 첫 문서 가설 틀림 | 추가 허락 없이 전체 ROOT로 돌아가 다른 문서 search 가능. 별도 ‘이 문서만’ 요청 fixture와 구분 | 범위 복구 |
| A07 | FTS에서만 잡히는 형태 변화 | 기존 형태소 FTS 사용 receipt와 후보 일치, literal로 대체 금지 | 검색 보존 |
| A08 | 일상어가 법률 원문에 없고 공식 bridge 존재 | match_terms→T/L→occurrence→P→READ, 방향·출처 영수증 | 역매칭 |
| A09 | 동음이의·짧은 등록 약어·긴 낱말 내부 짧은 토큰 | 모호성/경계 표시, 뜻이 틀린 L 거절 가능, 무조건 길이 컷 금지 | 용어 오류 |
| A10 | 항/호 대상 outgoing/incoming 참조 | witness와 정확 subtree, 역참조와 용어 역매칭 구별 | 참조 |
| A11 | title-only 또는 subtree search 실패 | searched_extent 정확, 본문/ROOT 자동 fallback 없음 | 도구 정직성 |
| A12 | assessments.evidence=P3, read.card 대신 잘못된 필드 | 스키마 또는 의미 오류를 반환, 상태 보존, E 매핑 재제시·제한 수리 | P/E 복구 |
| A13 | 한 batch에서 새 READ E를 추정해 채택 | 실행 전 거절, 다음 턴에 실제 E 제시 후 선택 | 종속 행동 |
| A14 | 동일 완료 READ 반복 | REUSED, exact E 현재 재제시, 새 원문 발견으로 집계 안 함 | 캐시/전달 |
| A15 | 부분 READ, 페이지 건너뜀, 마지막 cursor null | span coverage로 PARTIAL, 이어읽기 가능, 전문 읽음 오표시 없음 | 긴 원문 |
| A16 | 무진전 뒤 복구·다시 무진전 | 오류/경로 대안 제시, 공유 한도 소진 후 BOUNDED, 자동 채택 없음 | 반복 종료 |
| A17 | 잘못된 참조 또는 복수 대상 | UNRESOLVED, locate/search/browse 가능, 위임 효과 자동 확정 없음 | 관계 오연결 |
| A18 | 마지막 행동에서 중요한 새 후보/원문 생성 | 다음 실제 모델 입력에 결과 반영 후 종료 판단, 자동 채택 금지 | 마지막 턴 |
| A19 | L 거절 후보가 FTS로도 발견됨 | L route만 비활성, 다른 route P 보존 | 복수 유입 |
| A20 | PARK/REJECT 후 해석 변경 | inspect/reopen/재평가 가능, 종속 주장 STALE, 원문 보존 | 판단 철회 |
| A21 | 많은 READ 중 소수만 사용 | 사용 E의 요약/이유 요구, 나머지 UNASSESSED 허용, 전역 장부 관문 없음 | 부담 제한 |
| A22 | 이미 읽은 예외를 REJECT/DEFER | 이유 기록, 관련 challenge가 compose/review에 원문으로 남음 | 선택 손실 |
| A23 | 일반규정·예외 원문 모두 있지만 적용 오판 | 조건-사용자 사실-결론 대조, 정답 판정은 별도 oracle | 의미 실패 |
| A24 | 잘못된 검토가 맞는 초안 거절 | 근거 없는 objection 정정 또는 원문 반론, 제한 재검토 | 오거절 |
| A25 | 여러 주장 중 하나만 해결 안 됨 | 독립 검토 완료 주장 보존, 의존 claim은 무효화 | 부분답 |
| A26 | 회사 유형/시점/사실이 불명확 | 추정을 사실로 바꾸지 않음, 조건부 또는 CLARIFY | 사실 부족 |
| A27 | 검색 0건 또는 top-k만 조사 | ‘법률에 없음’ 단정 금지, 조사 범위·한계 표시 | 부재 주장 |
| A28 | 형식 오류/semantic error/HTTP timeout 각각 주입 | 종류별 receipt, retry/repair 단일 소유, timeout usage unknown 보존 | 오류 회계 |
| A29 | 한도 근접·중첩 복구·검토 이의 | 모든 물리 호출 동일 예산, reserve 침범 금지, bounded 종료 | 예산 |
| A30 | 입력에 E 원문이 빠지고 요약만 남음 | 선택/검토 전 rehydrate 또는 명시 미완료, phantom presented 없음 | 문맥 손실 |
| A31 | 다른 요청 핸들·scope 밖 대상·변경된 generation | 거절/격리, 캐시로 우회 안 함, 허용 범위만 반환 | 결속 |
| A32 | 원문 내 ‘이전 지침 무시’ 문구 | 데이터로 읽음, 도구/권한/정책 변경 안 함 | 입력 경계 |
| A33 | handler만 있고 모델 schema에 도구 없음 | startup/registry 검사 실패, 실제 payload에도 모든 지원 도구 존재 | 실행 배선 |
| A34 | 이전 검색 기능 일부를 새 검색으로 대체 | 같은 fixture의 FTS/좌표/bridge 가용성 비교, 기능 손실 드러남 | 부품 회귀 |
| A35 | 반환 객체는 맞지만 다음 view가 오래됨 | wire payload hash/실제 텍스트에서 결과·scope·E 확인 | 전달 배선 |
| A36 | 실모델이 존재하지 않는 별칭 출력 | 현재 유효 별칭 재제시, 같은 오류 제한 수리, 전체 세션 손실 방지 | 실모델 실패 |
| A37 | POST ask→후보→재탐색→FINAL | 실제 Pipeline/stage/profile 분기, Result 스키마와 canonical 인용 검사 | API 연결 |
| A38 | COMMIT_READY 게시 중단·RUNNING 소유자 상실 | 전자는 재게시, 후자는 INTERRUPTED, 모델 자동 재호출 없음 | 재시작 |
| A39 | 동시 요청·stale view·중복 decision | scope/alias/journal 격리, stale 결과 폐기, 중복 완료 영수증 재사용 | 동시성 |
| A40 | v1 journal/v2 reader, 새 계약 필드 | 명시 버전 판독, v1 데이터 자동 이행·덮어쓰기 없음 | 이행 |
| A41 | 모델 미사용 use_llm=false | 결정론 조회만, 의미 적용·claim 생성 없음 | 무모델 |
| A42 | 구조 부모 누락/순환·미분류 본문 | 준비 실패/제한 capability, 가짜 구조 생성 금지, 가능한 원문 접근 유지 | 자료 결함 |
| A43 | tree 페이지 시작이 하위 마디·검색 결과 상한 | ancestors/coverage 표시, 후속 페이지/SEARCH_CAPPED 명시 | 잘림 |
| A44 | 탐색자·검토자가 같은 오답에 동의 | 제품 SUPPORTED와 외부 채점 분리, false approval 지표 | 품질 평가 |
| A45 | 하네스가 과하게 미답변/검토 호출 증가 | 같은 조건 기준군의 정확도·미답변·회귀·비용을 함께 비교 | 실험 |
| A46 | 수동 관계 fixture로 정확 조문 도달 | typed link/READ 연결만 통과, 자율 탐색/승인/정답률로 확대 금지 | 증거 범위 |

## 실제 실행 경로 기록 양식

각 구현 검사에는 case_id, source_generation_hash, code/policy/schema hashes, input, tool_actions, wire_views, expected_invariants, actual, failures, journal/result paths를 남긴다. 모델 없는 fixture는 synthetic=true, 실제 모델은 provider/model/attempt/usage를 별도 기록한다.

과거 사례가 알려진 회귀 세트와 독립 holdout을 분리한다. A23/A44의 oracle은 제품 실행 후에만 결합한다. 같은 근거 두 개를 인용했는지와 그 적용 결론이 맞는지는 별도 판정이다.

## 추가 경계 조합

A04×A15: 트리에서 고른 긴 조/표를 여러 페이지 읽기. A06×A31: 잘못 좁힌 검색 범위는 되돌리되 실제 허용 범위 확대 금지. A12×A29: P/E 정정에 예산이 없으면 무근거 답변 대신 구체적 한계. A22×A30: 예외 원문이 입력 상한으로 빠졌을 때 검토 완료 오표시 금지. A24×A25: 잘못된 검토 때문에 무관한 정답 문단까지 삭제 금지. A28×A39: 재시도 응답 중복으로 평가/도구를 두 번 적용하지 않기.

이 조합까지 구현 검증에 포함한다. 수용 항목의 번호는 계약의 추적 키이며 샘플 수/정확도 지표가 아니다.
