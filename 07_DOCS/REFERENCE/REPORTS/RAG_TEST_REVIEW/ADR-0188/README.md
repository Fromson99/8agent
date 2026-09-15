# ADR-0188 · 실제 Haiku RAG 기준선

[전체 안내](../README.md)

MAIN generation 5의 `run-006`, 제품·중간 역할과 격리 채점 모두 `claude-haiku-4-5-20251001`입니다. 최종 완료 실행의 6건을 수록했습니다. 사전 점검·중단 실행은 원본 artifacts에 남아 있으나 이 완료 결과에 합산하지 않았습니다.

정답 **3/6 (50.0%)** · decisive 조문 exact recall **2/7 (28.6%)**. 원 ADR은 정확도·회수율·지연 기준 미달로 Rejected입니다.

[6개 질문의 실제 답변·판정 전체](baseline.md)

| 질문 | 당시 판정 | 검색·계측 원인 분석 |
|---|---|---|
| [cm-001](baseline.md#cm-001) | 정답 | 개별 원인 분석 없음. 상세 문서의 채점 근거 참조. |
| [cm-011](baseline.md#cm-011) | **오답** | 원 ADR의 원인 분석: raw B/C/D 후보에는 제29조가 있었으나 선택 단계에서 탈락했습니다. |
| [cm-021](baseline.md#cm-021) | 정답 | 원 ADR의 계측 주의: 답변은 의미상 정답이지만 동일 법령 제57조의 SourceSet 문서 ID와 gold 문서 ID가 달라 exact recall이 낮게 계상되었습니다. |
| [cm-031](baseline.md#cm-031) | **오답** | 원 ADR의 원인 분석: raw assertion 후보에는 제5조가 있었으나 selector가 제외했습니다. |
| [cm-041](baseline.md#cm-041) | **오답** | 원 ADR의 원인 분석: relation raw 후보에는 제383조가 있었으나 relation cap에서 탈락했습니다. |
| [cm-051](baseline.md#cm-051) | 정답 | 개별 원인 분석 없음. 상세 문서의 채점 근거 참조. |

검색 후보가 있었어도 최종 선택에서 필요한 근거가 빠진 사례가 보고되었습니다. 또한 6/6 trace가 봉인 뒤 변경되었고 ontology의 최종 가산 단계 누락이 있어, 원본과 계측용 재봉인 사본을 구분해야 합니다. 문서 ID 불일치를 답변 오답과 동일하게 취급하지 않습니다. 소표본 인샘플·단일 Haiku 채점이므로 일반화 성능이나 채택 근거가 아닙니다.

[원 ADR의 원인 분석과 한계](../../../../../04_EXPERIMENTS/ADR/ADR-0188-rag-main-g5-real-haiku-baseline/README.md) · [완료 실행 원본](../../../../../04_EXPERIMENTS/ADR/ADR-0188-rag-main-g5-real-haiku-baseline/artifacts/run-006.json)
