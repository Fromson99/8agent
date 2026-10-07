# shortcut · legal_wiki 구현 결과

**구현 후보와 실제 예제를 만들었다. MAIN 승격 기준은 통과하지 못해 기존 MAIN을 유지했다. 전체 운영 반영 완료 상태는 아니다.**

새 코드의 지속 기록·사건 연결·정정·지식 구성·조회·조건부 재사용·운영 도구는 격리한 전체 v6 후보 안에서 배선했다. 기존 활성 코드·원문 세대·운영 DB·GENOS는 바꾸지 않았다.

## 바로 볼 자료

- [실제 생성한 공개 합성 사례6개와15개 지식 단위](EXAMPLES.md)
- [추가 실제 사례: 연결된 두 사건과 정정 후 위키](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0644-shortcut-incremental-related-operations/artifacts/run-001/wikis/067c1ec56bbe643090b7a26d282a39eff541d4ddd7535e3de02ba70a659c9be8/projection-c0d8a290dc9746ddb733a4b6d3a5db2d/index.md)
- [기능별 구현·미확인 범위](STATUS.md)
- [실행·이행·검토·복구 경로](OPERATIONS.md)
- [최신 동결 코드와 파일 해시](/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_0644/integrated/candidate.json)
- [실제 모델의 증분 처리 결과](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0644-shortcut-incremental-related-operations/artifacts/run-001/result.json)

## 확인한 결과

| 검사 | 결과 |
|---|---|
| 최신 후보 계약·회귀·프로세스 장애/복구 | **100개 통과** |
| 기존6개 합성 사례의 실제 지식 구성 | **6/6 수락**,15개 단위. 법률 판단 자동 승인 없음 |
| 관련 사건 구성 → 한 사건 정정 | **2/2 수락**. 첫 처리의 원이벤트5개를 다시 보내지 않고 새 이벤트2개만 전달 |
| 원문·조건·권한·도구 계약 | 실패 시 차단/재조사, 검증 영수증 없이 판단 재사용 불가 |
| 최신 ADR 최종 검사 | ADR-0644 `validate --final` 통과 |
| 전체 실험 계보 | 오류 남음. [실제 검사 출력](GRAPH_VALIDATION.txt) 보존 |

실제 모델은 Qwen3.8/Parasail FP8, reasoning none, fallback 없음이다. 공개 원문과 합성 사건만 사용했다. 내부 사건·현재 법령 전체의 정확도·GENOS 현장 성능을 검증한 결과가 아니다.

## MAIN을 유지한 이유

선택 데이터에 맞지 않았던 용어집 코드 문제는 기존 MAIN의 정확한 compiler 해시로 고쳐 실제 실행까지 확인했다. 그 뒤의 회귀 비교에서 다음 결과가 나왔다.

| 실제 법률 답변 비교 | 기존 MAIN | 통합 v6 후보 |
|---|---:|---:|
| 원문 기준 답변 성공 | 3/3 | 2/3 |
| 모델 호출 시도 | 9 | 31 |
| 중앙 응답 시간 | 34.3초 | 87.0초 |
| 확인된 온라인 비용 | $0.0051816 | $0.0175330 |

후보1건은 공급자의429 요청 제한으로 실패했다. 해당 실패 호출의 사용량은 미확인이며 위 비용은 확인된 값만 합산했다. 나머지2건은 원문 기준 평가를 통과했으나, 전체 성공·지연·비용·사용량 확인 기준을 통과하지 못했다. [실제 비교와 실패 기록](/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-0643-shortcut-generation-compatible/README.md).

최신 ADR-0644는 증분 compiler·운영 계약을 보완한 구현 probe다. 이미 실패한 온라인 비교를 새 독립 평가로 바꾸거나 승격 근거로 재사용하지 않았다. 검증 통과 없이 품질 예외 승인으로 MAIN에 넣지 않았다.

현재 로컬 MAIN은 `legal-agent-source-prefix-20260930-r3`이며 시작 시 pointer 해시와 같다. Git main 병합, 제품 MAIN 승격, 저장소 pointer 이행, GENOS 배포 모두 수행하지 않았다.

## 남은 운영 조건

- 통합 v6의 추가 호출·지연을 줄이고, 새 독립 법률 평가에서 품질·비용·지연 기준을 통과해야 한다.
- 현행 stable 승격 구현의 품질 예외 경로를 사용하지 않았다. 정상 품질 gate와 정확한 활성 코드 대비 delta/provenance를 갖춘 승격 계획이 필요하다.
- 실제 보존 기간·법적 보존 의무·삭제 승인·모든 백업 위치는 운영자가 정해야 한다. 현재 도구는 연결 목록을 만들며 파괴적 삭제는 하지 않는다.
- 큰 단일 원기록은 모델 예산을 넘으면 원본을 보존한 채 오류·격리로 남긴다. 모든 크기의 기록을 자동 분절·완결하는 것으로 주장하지 않는다.
- GENOS 내부 모델·내구 디스크·writer 운영·워크플로우 현장 검증은 현재 세션에서 수행할 수 없어 미확인이다.

전체 계보 검사에는 기존 항목 외에 이번 초기 ADR-0638의 run-purpose 메타데이터 오류도 있다. 완료 기록을 덮어쓰지 않았고 후속 정본·개별 최종 검사와 구분했다. 이를 전체 계보 통과로 보고하지 않는다.
