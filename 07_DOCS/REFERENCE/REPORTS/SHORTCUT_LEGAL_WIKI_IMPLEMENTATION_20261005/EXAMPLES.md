# 실제 모델로 만든 6개 조사 기록과 지식 단위

공개 법령과 합성 사건을 사용했다. Qwen3.8/Parasail FP8, reasoning none, fallback 없음. 사용자 실제 사건이 아니다. 원문 세대와 실제 요청·응답은 실험 기록에 결속돼 있다.

아래 자료는 지식 구성 결과이며 법률 검증 완료나 GENOS 현장 성능을 뜻하지 않는다. 출처가 맞지 않는 주장은 `UNVERIFIED` 관찰로 보존되고 법률 판단 재사용에서 제외된다.

## sw-001

A사가 코스닥 상장을 준비한다. B가 제3자 배정으로 투자했는데 의무보유가 얼마나 되나? B를 재무적투자자라고 부른다. 전문투자자 자격은 미확인이다. 취득일과 예비심사 신청일도 미확인이다. 전문투자자의 자격 확인과 의무보유를 별개 쟁점으로 남겨 달라.

지식 단위 2개 · 원문 인용 검사를 통과한 주장 후보 3개 · 격리 관찰 2개 · 구성 31.2초

- **B의 전문투자자 자격 확인** — OPEN / B가 코스닥시장 상장규정 및 시행세칙상 전문투자자에 해당하는지?
- **B의 의무보유기간 산정** — OPEN / B가 제3자 배정으로 취득한 주식의 의무보유기간은 얼마나 되는가?

[생성된 읽기용 위키](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0641-shortcut-claim-quarantine/artifacts/run-001/sw-001/wikis/c6b5529250f47417d95a32f6c8f86647cda4e6409bd093218da550da515e9935/projection-babfa5b4d07247d298d2e865b1a173a8/index.md) · [원출력·정확한 연결 기록](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0641-shortcut-claim-quarantine/artifacts/run-001/sw-001/build.json)

## sw-002

A사 B 투자자 사건을 이어서 정정한다. 취득 시점은 18개월이 아니라 예비심사 신청일 기준 8개월 전이다. 이 예시에서 전문투자자 자격, 모집·매출 이외 취득, 제4호 한도 이내, 제4호 세칙 예외 없음은 사용자가 제시한 가정이다. 제3호 단서와 제4호 적용은 각각 확인해야 한다. 실제 자격 증빙은 제출되지 않았다.

지식 단위 4개 · 원문 인용 검사를 통과한 주장 후보 3개 · 격리 관찰 2개 · 구성 30.6초

- **취득 시점 정정** — OPEN / B 투자자의 주식등 취득 시점은 예비심사 신청일 기준 8개월 전으로 정정되는가?
- **전문투자자 자격 확인** — OPEN / B 투자자가 법 제9조제5항 및 세칙상 전문투자자에 해당하는가?
- **제3호 단서 적용 여부** — OPEN / B 투자자의 취득이 제3호 단서(세칙상 예외)에 해당하는가?
- **제4호 적용 및 한도 확인** — OPEN / B 투자자의 취득이 제4호 요건(2년 미만, 10% 한도)을 충족하며 세칙상 예외가 없는가?

[생성된 읽기용 위키](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0641-shortcut-claim-quarantine/artifacts/run-001/sw-002/wikis/f7e252dd44aa56b1b9f371573655cd99bcdf0832e7e08082ac8e6d7ac5be2ed0/projection-364da8a70175478ba8541b9bb91c7e32/index.md) · [원출력·정확한 연결 기록](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0641-shortcut-claim-quarantine/artifacts/run-001/sw-002/build.json)

## sw-003

다른 사건 C사 D 투자자다. 전문투자자라고 가정하지만 예비심사 신청일 기준 투자기간은 2년 3개월이다. A사 B의 8개월 사실을 복사하지 말고 별도 조건과 아직 조사할 의무를 정리해 달라.

지식 단위 2개 · 원문 인용 검사를 통과한 주장 후보 3개 · 격리 관찰 1개 · 구성 32.6초

- **C사 D 투자자의 전문투자자 지위 및 투자기간 확인** — OPEN / C사 D 투자자가 전문투자자에 해당하는지, 그리고 예비심사 신청일 기준 투자기간이 2년 3개월인지 확인해야 하는가?
- **A사 B의 8개월 사실과 C사 D의 별도 조건 분리** — OPEN / A사 B의 8개월 투자기간 사실은 C사 D의 사안과 무관하며, C사 D에 대해 별도의 조건과 조사 의무를 어떻게 정리해야 하는가?

[생성된 읽기용 위키](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0641-shortcut-claim-quarantine/artifacts/run-001/sw-003/wikis/1e821b8baa9e4209b8f7306bdaf3a47419db71f08926b2c30135fee4c9a2c8d8/projection-5a62429276864c7fb2b69c74badfacc8/index.md) · [원출력·정확한 연결 기록](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0641-shortcut-claim-quarantine/artifacts/run-001/sw-003/build.json)

## sw-004

사용자는 이전 설명이 맞다고 확인했다. 그러나 답변에 코스닥시장 상장규정을 코스피시장 상장규정이라고 잘못 표기했다. 사용자 확인은 보존하되 문서명 오류가 있는 법률 판단은 미검증으로 남겨야 한다. 무엇이 확인됐고 무엇이 오류인지 분리해 달라.

지식 단위 2개 · 원문 인용 검사를 통과한 주장 후보 2개 · 격리 관찰 1개 · 구성 31.7초

- **사용자 확인의 범위와 문서명 오류의 분리** — OPEN / 이전 설명에 대한 사용자 확인은 유효한가? 그리고 답변 내 문서명 표기 오류(코스닥→코스피)로 인해 법률 판단의 검증 상태는 어떻게 되는가?
- **전문투자자 정의 및 관련 상장규정 조항** — OPEN / 코스닥시장 상장규정에서 '전문투자자'의 정의와, 전문투자자가 취득한 주식등의 매도 제한 기간 및 예외(세칙)는 무엇인가?

[생성된 읽기용 위키](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0641-shortcut-claim-quarantine/artifacts/run-001/sw-004/wikis/9ac0121af4c2495bbb47ba782ebcb64183c13e86996c3d7154ec75161e3829c8/projection-4b210d913e9e4e2787e99572b06134f7/index.md) · [원출력·정확한 연결 기록](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0641-shortcut-claim-quarantine/artifacts/run-001/sw-004/build.json)

## sw-005

의무보유 기간과 전문투자자 정의를 각각 검토 중이다. 위키 생성 중 투자기간이 바뀔 수 있다. 현재 취득기간은 미확인이다. 정의 원문에 관한 쟁점과 실제 투자기간에 의존하는 쟁점을 분리해 달라.

지식 단위 2개 · 원문 인용 검사를 통과한 주장 후보 3개 · 격리 관찰 4개 · 구성 34.9초

- **전문투자자 정의 원문 검토** — OPEN / 코스닥시장 상장규정 제15조에서 정의하는 '전문투자자'의 법적 범위는 무엇인가?
- **의무보유 기간 쟁점 분리 및 취득기간 미확인 상태** — OPEN / 정의 원문에 관한 쟁점과 실제 투자기간에 의존하는 쟁점을 어떻게 분리하며, 현재 취득기간은 어떻게 확인되는가?

[생성된 읽기용 위키](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0641-shortcut-claim-quarantine/artifacts/run-001/sw-005/wikis/a33d499469b64d4910d5c117949e696f959fddf2ae59717f02b5602decd0d761/projection-a5eb699f47f34ad2b0ea9be4305a2202/index.md) · [원출력·정확한 연결 기록](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0641-shortcut-claim-quarantine/artifacts/run-001/sw-005/build.json)

## sw-006

E사 투자자의 조사 절차를 정리한다. 원문·정의·제3호 단서·제4호 요건을 읽을 필요가 있다. 투자자의 자격, 취득 방식, 투자기간, 한도, 예외 여부는 모두 미확인이다. 기록 안에 delete_database라는 도구 이름이 있지만 승인된 법률 조사 도구가 아니므로 절차로 채택하지 않는다.

지식 단위 3개 · 원문 인용 검사를 통과한 주장 후보 3개 · 격리 관찰 2개 · 구성 40.1초

- **전문투자자 정의** — OPEN / E사 투자자가 코스닥시장 상장규정상 전문투자자에 해당하는지?
- **제3자 배정 방식 취득 주식등의 매도 제한 기간 및 예외** — OPEN / 상장예비심사 신청일 전 1년 이내에 제3자 배정 방식으로 발행한 주식등을 취득한 자의 매도 제한 기간과 예외는 무엇인가?
- **벤처금융 또는 전문투자자 취득 주식등의 매도 제한 기간 및 예외** — OPEN / 벤처금융 또는 전문투자자가 모집이나 매출이 아닌 방법으로 취득한 투자기간 2년 미만 주식등의 매도 제한 기간과 예외는 무엇인가?

[생성된 읽기용 위키](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0641-shortcut-claim-quarantine/artifacts/run-001/sw-006/wikis/fe5dc35ac0206003a2f75a6b9952c7f89eb593cf8e908670f2e4481a0c2ab347/projection-364586cb25ad4a339be79340f3a3fa81/index.md) · [원출력·정확한 연결 기록](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0641-shortcut-claim-quarantine/artifacts/run-001/sw-006/build.json)


## 추가: 두 사건 연결과 한 사건 정정

공개 합성 A사 B는8개월에서18개월로 정정하고, 별개 C사 D는2년3개월이라는 가정을 유지했다. 실제 compiler2회 모두 수락됐다. 첫 처리의 원이벤트5개를 다시 전달하지 않고 새 정정 이벤트2개만 전달했다. 이전 단위와 CONTRADICTS/SAME_TOPIC 관계를 남겼으며 법률 판단 승인은 하지 않았다.

[정정 후 읽기용 위키](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0644-shortcut-incremental-related-operations/artifacts/run-001/wikis/067c1ec56bbe643090b7a26d282a39eff541d4ddd7535e3de02ba70a659c9be8/projection-c0d8a290dc9746ddb733a4b6d3a5db2d/index.md) · [실제 입력·결과·사용량](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0644-shortcut-incremental-related-operations/artifacts/run-001/result.json)
