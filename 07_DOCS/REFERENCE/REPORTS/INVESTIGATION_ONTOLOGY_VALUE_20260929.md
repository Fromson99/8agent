# 조사 목적 온톨로지 가치 재실험 — 2026-09-29

이번 방식은 불필요한 원문 회수와 모델 입력량을 줄였지만, Fulltext 병목이나 전체 응답 속도를 개선하지 못했다. 원문·비용 절감에 조건부 가치가 있으며 현재 후보의 운영 채택은 보류한다.

실험은 [ADR-0567](../../../04_EXPERIMENTS/ADR/ADR-0567-investigation-ontology-journal/README.md)에 보존했다. 실행 전 journal 연결이 잘못된 [ADR-0566](../../../04_EXPERIMENTS/ADR/ADR-0566-investigation-ontology-value/README.md)은 모델 호출0의 실패로 남기고, 새 ADR에서 연결만 수정했다. 질문·원문·gold·프롬프트·DB 정책은 byte 동일하다.

## 실제로 비교한 것

선택된 로컬 release `legal-agent-structure-catalogue-pecab-repair-20260929-r1`의 SourceRecall/global branch/source_selection/Fulltext와 hash가 일치하는 기준 모듈을 사용했다. 부모 ADR-0565의 SQLite 조사 목적 그래프는 그대로 계승했다.

양쪽에서 같은 합성 corpus 55개 조문, 질문7개, 공통 검색 계획, 실제 FTS5 검색·v5 READ·native 원문 선별·Gemma 답변을 실행했다. 후보는 질문 목적을 Gemma로 판별하는 호출1개를 추가하고, 목적→EXCLUDES→자료 종류 관계를 DB에서 컴파일해 두 회수 분기와 READ 직전에 적용했다. 후보 목적 인식 비용·시간을 모두 포함했다. 모델은 Gemma / Parasail FP8 / thinking off다. arm 순서는 질문마다 교대했고 반복1·재시도0이다.

전체 BoundedSourceSession/Compose API를 실행한 것은 아니다. 양쪽 query plan은 사전 고정했고 의무 계획·기본 Compose를 공통 연구 답변 호출로 대체했다. 따라서 전체 MAIN 서비스의 속도 인증으로 쓰지 않는다. 실제 사용자 로그의 자동 추출·밤 시간 학습은 실행하지 않았으며, 목적·자료 분류·EXCLUDES는 사람이 설계한 합성 온톨로지다. 이는 **유효한 개념 정책이 있을 때 온라인 소비가 이익을 주는지** 시험한 것이다.

## 결과

| 항목 | 기준 | 개념 정책 후보 | 변화 |
|---|---:|---:|---:|
| 전체 원문 조문 회수 | 379 | 235 | 38.0% 감소 |
| 적용규정3질문의 원문 회수 | 162 | 18 | 88.9% 감소 |
| 모델 입력 토큰 | 102,310 | 85,232 | 16.7% 감소 |
| 모델 물리 호출 | 21 | 28 | 목적 인식7회 추가 |
| provider 보고 제품 비용 | $0.01542259 | $0.01268815 | 17.7% 감소 |
| 질문당 평균 관측 시간 | 17.65초 | 22.44초 | 27.1% 증가 |
| 필수 근거·인용·답변요소 기준 | 6/7 | 6/7 | 후보만의 신규 실패0 |
| SQL rank 호출 | 34 | 34 | 동일 |
| SQL이 fetch한 검색 행 | 1870 | 1870 | 동일 |
| 실제 SQL 구간 시간 합계 | 0.0118초 | 0.0111초 | 소형 로컬 자료, 병목 개선 근거 없음 |

비용은 호출이 보고한 값으로 목적 판별과 cache 할인까지 포함한다. 양쪽 cached input은 14,559 / 17,185토큰이다. 장기 평균이나 cache 없는 고정 요금 효과로 해석하지 않는다. 별도의 오프라인 구축·분류·로그 검토 비용은 온라인 비교에 포함하지 않았다.

| 사례 | 읽은 조문 기준→후보 | 시간 기준→후보(초) | 후보 목적 | 되돌림 |
|---|---:|---:|---|---|
| APP-01 | 54 → 6 | 17.15 → 22.87 | APPLICABILITY |  |
| APP-02 | 54 → 6 | 19.10 → 13.99 | APPLICABILITY |  |
| APP-03 | 54 → 6 | 20.27 → 31.08 | APPLICABILITY |  |
| INV-01 | 54 → 54 | 24.49 → 39.20 | MIXED |  |
| PERF-01 | 54 → 54 | 10.34 → 13.92 | PERFORMANCE |  |
| MIX-01 | 54 → 54 | 14.70 → 19.96 | MIXED |  |
| DRIFT-01 | 55 → 55 | 17.53 → 16.09 | APPLICABILITY | current resource classification missing or source version changed |

## 근거 보존과 실패

적용규정3질문에서는 54개에서6개로 줄였다. 단순히 프롬프트에 C 제외를 추가한 것이 아니라 DB 그래프가 만든 scope를 두 native 회수 분기에서 소비하고, READ에서도 제외한 원문·상위 문서의 우회 접근을 차단했다. 실제 native 접근 계약8개가 모두 통과했다. 이 연결은 회수 분기와 READ에만 적용했으며 다른 native 도구 전체 배선은 이번 실험에서 완료하지 않았다.

목록·실적·복합 질문에서는 C를 보존했다. 목적 이름은 6/7 일치했고 목록 질문을 MIXED로 분류한1건은 제외하지 않아 자료를 잃지 않았다. 이 결과가 수천 개 개념에서의 목적 인식 정확도를 입증하지는 않는다.

버전 변경 사례에서는 현재 원문 해시가 과거 분류와 달라 제외 정책을 해제하고55개를 조사했다. 양쪽 모두 신판 특례와3영업일을 답했다. 다만 비교한 일반 비의결권 제외 규정의 원문을 최종 claims에 인용하지 않아 사전 기준은 양쪽6/7이다. 필수 원문은 선별 입력까지100% 보존됐으며 이 실패는 최종 인용 단계다. 결과를 보고 gold나 성공 문턱을 바꾸지 않았다.

## 측정 감사

종료 시 집계 JSON의 FTS timing 배열에 앞선 wrapper가 후속 사례 timing도 추가하는 문제가 있었다. 각 사례가 끝날 때 저장한 개별 result는 정확하며 SQL console 이벤트와 호출 수를 모두 대조했다. 원본 집계는 보존하고 FTS 계산만 개별 receipt에서 수행했다. 원문 수·답변·비용·case wall·사전 점수는 바뀌지 않았다. native Fulltext 객체 cache는 프로세스 내 공유됐고 wrapper 층의 작은 측정 overhead가 남아 있다. 이 때문에 단일 소형 실행의 SQL 미세 차이를 속도 개선으로 해석하지 않는다. [측정 감사](../../../04_EXPERIMENTS/ADR/ADR-0567-investigation-ontology-journal/artifacts/run-001/instrumentation-audit.json).

## 판단

과거 안내 prototype ADR-0562는 이미 최소 원문에 가까워 읽은 수17→16에 그쳤고 입력·비용이 약44% 증가했다. 이번에는 **읽기 전 범위를 줄이는 DB 소비자**를 연결해 원문 회수와 선별 inventory 입력을 줄였다. 잡음 자료가 많고 조사 목적·자료 분류가 검증된 곳에서는 이 방향의 가치가 관측됐다.

사용자가 지적한 Fulltext 병목은 그대로다. 현재 `rank()`는 전체 FTS SQL을 실행하고 반환된 행을 allowed scope로 거른다. 후보는 SQL 검색 호출과 fetch 행을 줄이지 못했다. 원문 회수 전체 시간은 6.26→5.07초였고, 추가 목적 인식에는 합계 25.76초가 들었다. 원문을 줄여도 모델 호출을 추가하면 느려질 수 있다는 결과다.

다음 설계의 우선순위는 기존 검색 계획·행동 판단에서 조사 목적을 함께 생성해 추가 판별 호출을 없애고, DB 정책을 공통 데이터 접근 계약으로 전달한 뒤 backend가 검색 전에 가능한 범위로 적용하는 것이다. Fulltext에는 SQL/색인 범위 제약, 다른 검색에는 그 backend의 범위 제약으로 번역한다. 이 개선은 이번 결과로 검증한 기능이 아니며 새 후보·분리 평가가 필요하다. 그다음 실제 로그에서 만든 관계의 오제외와 분류·통합 유지 비용을 평가해야 한다.

MAIN·활성 포인터 generation31·운영 registry·GENOS는 변경하지 않았다. 사전 기능7/7 기준과 속도 목표를 충족하지 않아 운영 승격 근거로 사용하지 않는다. 전체 graph validator의 기존 오류는 검증 기록에 별도로 남긴다.

[원시 결과](../../../04_EXPERIMENTS/ADR/ADR-0567-investigation-ontology-journal/artifacts/run-001/result.json) · [사전 기준·채점](../../../04_EXPERIMENTS/ADR/ADR-0567-investigation-ontology-journal/artifacts/run-001/offline-grade.json) · [SQL·목적 분류 상세](../../../04_EXPERIMENTS/ADR/ADR-0567-investigation-ontology-journal/artifacts/run-001/stage-attribution.json)

최종 검증: 새 후보 snapshot과 ADR 최종 검증 통과. 전체 실험 graph는 기존 ADR-0305/0444/0541/0542/0158 오류6개로 미통과했으며, 이번0566/0567 scope의 계보·부모 hash는 통과했다.
