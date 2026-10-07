# 수정 계획 자체 검토

검토일: 2026-09-20. 작성자와 같은 에이전트의 자체 검토이며 독립 검토가 아니다.

- 대상: PLAN.md
- 대상 SHA-256: `0e1e5e4f2675dab23985f658e754bb11f461b80bcecfeab1c3965f6c53b79777`
- 기준 코드: ADR0476/qwen-autonomous/rev-001. 현재 운영 코드와 별개인 격리 실험 코드.
- 구현 가능성: **조건부 타당**. 저장·제시·호출 계약을 재사용할 수 있으나 새 상태 projection과 회복 정책 구현/검증이 선행 조건이다.
- 예상 수치: 과거 실측 인용은 확인. 개선률·새 비용·일정은 미산정으로 유지. 실제 품질은 미검증.
- 이번 작업: 설계와 자체 검토 문서만 작성. 코드 변경·새 ADR 선점·모델 호출·MAIN 변경 없음.

## 발견사항

| ID | 심각도 | 직접 근거·영향 | 필요한 보완 | 문서 반영 | 구현·검증 |
|---|---|---|---|---|---|
| R1 | 높음 | 카드에 이미 읽음/P→E 연결이 없고 모델은 제목 대조 필요 | 현재 실제 제시 E만 연결하는 읽음 projection | §4 반영 | 미구현 |
| R2 | 높음 | apply_decision은 execute_action 반환값을 다음 view에 싣지 않음; 두 실제 입력 내용 동일 | 행동 결과를 서버 영수증으로 저장하고 다음 직렬화에 포함 | §5 반영 | 미구현 |
| R3 | 높음 | read 완료와 모델 전달 성공은 다름; cached E만 표시하면 미제시 근거 채택 위험 | 현재 view 원문·presentation receipt 검사 유지, 별칭만으로 자격 생성 금지 | §4·7 반영 | 미구현 |
| R4 | 중간 | cursor 없음만으로 전문 읽음을 추정하면 부분 범위를 완료로 오인 | 성공 READ 범위·span 누적 및 PARTIAL 구분 | §4·8 반영 | 미구현 |
| R5 | 높음 | reserve_attempt는 investigate에 finalization_reserve를 제외한 한도를 적용 | 회복도 동일 phase/물리 예산 사용, 요청 전체 1회 상한, 숨은 호출 금지 | §6 반영 | 미구현 |
| R6 | 중간 | 무진전 개수만 비교하면 범위/내용 진전을 놓칠 수 있음 | span·cursor·선택·후보 의미 변경 비교; revision은 진전에서 제외 | §6 반영 | 미구현 |
| R7 | 높음 | 빈 selected면 compose 호출 자체를 건너뜀 | 빈 선택 사유와 bounded 종료를 구분, 자동 채택은 금지 | §6·8 반영 | 미구현 |
| R8 | 높음 | 현재 사례는 첫 입력에 결정 조문이 모두 있음 | 자동 선택/작성과 신규 자율 검색의 검증 분리 | §8 반영 | 후속 표본 미선정 |
| R9 | 중간 | 과거 계약 검사는 scripted 행동만 검증 | 동일 시점 baseline·실모델 전환·독립 의미 검증을 분리 | §8 반영 | 미실행 |
| R10 | 중간 | 입력 필드 추가는 컨텍스트 상한·현재 E 목록에 영향 | 원문 확정 후 E 연결 생성, 전체 전송 요청 경계 검사 | §4·5 반영 | 미구현 |

## 수치 점검

- N1~N4는 아래 metrics/result 원장에서 확인했다. 단회·초기화 포함·provider 보고 비용이라는 범위를 유지했다.
- N5는 관측이 아닌 제안 목표다. 현재 전체 모델 한도는 유지한다.
- N6: `Δcalls=d+r−u`. d+r=u이면 0, d+r>u이면 증가. 비용은 호출마다 토큰이 다르므로 이 식으로 비용 절감률을 계산하지 않는다.
- N7~N8은 미산정이다. 어떤 수정으로도 성공률·비용·일정 향상을 확정하지 않았다.

## 기준 자료 해시

코드는 `02_BACKEND/lawrag/research/candidates/adr_0476/qwen-autonomous/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/` 아래다.

| 자료 | SHA-256 |
|---|---|
| source_first_navigation.py | `7f4ef172d240e467dd308ba78f4d63c40c94a44af85232a9970a5a0989d2c52c` |
| source_first_session.py | `c7dc5ea7a1b99c79621a06e657b7e924d5e47658e388c770f18aa3dc181ce695` |
| source_first_gateway.py | `c345e1c45a5de9980e1691777422e433852e2a9e5ef7bf8f1fd1551ca8cee403` |
| source_first_protocol.py | `ae57673466d9a55c2e840f27d64ede636d26415de809d3d98f89d36c4e8f53ba` |
| ADR0476 artifacts/metrics.json | `3ceeb322d122a556a08b3ed03b9c69df247230b0975f0bbf44ea46954e1b4c72` |
| ADR0476 artifacts/run-001/result.json | `8454d8efea3f317aecae289013a09c639e3001c5388b39afcb8aa252324b4e8a` |

## 남은 판단

다음 입력에 행동 피드백이 없었다는 사실은 확인했지만, 같은 READ를 반복한 모델의 내부 원인은 확정할 수 없다. 수정 후 같은 조건의 비교가 필요하다. 문서 반영만으로 결함 해결이나 운영 인증을 주장하지 않는다. 외부 레퍼런스·GENOS·실제 모델 재호출은 수행하지 않았다.
