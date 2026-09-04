---
adr_id: ADR-0166
title: Permanent v2 completion and release hardening
status: Proposed
decision_date: 2026-09-04
phase: audit
in_sample: false
decision_eligible: false
main_wiring: unchanged
created_at: 2026-09-04T00:23:39.298640Z
updated_at: 2026-09-04T01:28:03.842538Z
owner: Codex
work_status: completed
---

# ADR-0166: Permanent v2 completion and release hardening

## 1. 결정 요약

영구 v2 코드 레이아웃의 경로·이력 해석·패키징·회귀 계약을 정리했다. 이 ADR은
결정론적 감사 기록이며 효과성 실험이나 MAIN 승격 기록이 아니다. 배포와 push는 수행하지 않았다.

### 작업 선점

- 생성·선점 시각(UTC): `2026-09-04T00:23:39.298640Z`
- 작업자: `Codex`
- Codex task/session: `/root`
- 작업 범위: Complete permanent v2 regression, tooling, path, provenance, resolver, packaging, and CAS hardening
- 중복 확인 키: `permanent-v2-completion`
- 작업 상태: `in_progress`

생성·시작·완료·포기 이력의 정본은 [실험 manifest](실험/manifest.json)의
`reservation.events`에 append-only로 기록한다.

## 2. 문제와 변경 전 구조

기본 pytest가 전체 테스트 트리를 수집하지 않았고, 다수의 도구·테스트가 퇴역한
`data/docs/scripts/lawrag/var` 경로를 직접 참조했다. 과거 ADR의 path/hash를 보존하면서
새 위치를 읽을 공통 resolver와 설치 가능한 패키지 계약도 없었다.

## 3. 가설과 사전 판정 기준

### 가설

활성화 영수증에 봉인된 source→target binding을 사용하면 과거 기록을 수정하지 않고도
영구 v2 경로에서 동일 artifact를 검증할 수 있다.

### 성공 기준

활성 v5 영수증 검증, wheel/code bundle 데이터 누수 0, 동결 후보 변경 0, 기본 회귀 실패 0.

### 반증 기준

영수증 hash 불일치, legacy/unknown root 잔존, research/raw corpus 패키징, 동결 snapshot
drift 또는 기본 회귀 실패가 하나라도 있으면 실패다. 기준은 첫 실행 전에 동결되지 않아
이 감사는 `decision_eligible=false`로 유지한다.

## 4. 실험 설계

| arm | 변경점 | 고정 조건 | 목적 |
|---|---|---|---|
| baseline | base commit의 영구 v2 작업판 | 동일 WSL/Python 환경 | reference |
| hardened-v2 | canonical 경로·receipt resolver·패키지 계약·v3 generation | 배포/LLM/검색·답변 변경 없음 | audit |



### 다른 ADR과의 관계

- 관련 ADR: 없음

- experiment 계보와 직접 부모 arm: [실험 manifest](실험/manifest.json)

## 5. 데이터·모델·재현성

- 데이터셋과 버전: repository migration audit / `20260904-code-v5`
- frozen source와 SHA-256: `00_SYSTEM/WORKSPACE.json` / `b98e9340...bbfda2`
- 제품/중간/채점 모델: 호출 없음
- 반복 수와 다수결: 해당 없음
- 법령·기준답변 버전 점검: 제품 데이터·답변 경로 미변경 확인

## 6. 결과

| arm | 정답/전체 | 정확도 | baseline 대비 | 입력 토큰 | p50/p95 |
|---|---:|---:|---:|---:|---:|
| baseline | 해당 없음 | 해당 없음 | - | 0 | 해당 없음 |
| hardened-v2 | 1960/1960 tests | 100% | 실패 0 | 0 | 153.14초 전체 |

| paired outcome | 건수 | 비율 |
|---|---:|---:|
| 비교 arm만 정답 | 해당 없음 | 해당 없음 |
| 기준 arm만 정답(회귀) | 0 | 0% |
| 둘 다 정답 | 해당 없음 | 해당 없음 |
| 둘 다 오답 | 0 | 0% |

## 7. 사례별 오류 분석

| 실패 유형 | 건수/분모 | 대표 질문 | 해석 |
|---|---:|---|---|
| 회귀 실패 | 0/1960 | 해당 없음 | 기본 수집 범위 전체 통과 |

질문별 실제 입출력은 [실험 인덱스](실험/README.md)에 연결한다.

## 8. 비용·지연·회수 규모

| 항목 | 값 | 측정 단위·분모 |
|---|---:|---|
| 전체 corpus | 해당 없음 | retrieval 미변경 |
| 필터 전/후 후보 | 해당 없음 | retrieval 미변경 |
| LLM 제시 수 | 0 | 평균·p50·p95 해당 없음 |
| golden recall | 해당 없음 | retrieval 미변경 |
| 제시 비율 | 해당 없음 | retrieval 미변경 |
| LLM 호출·토큰·지연 | 0 / 0 / 0 | deterministic audit |

회수를 변경하지 않았다면 해당 없음을 쓰고 frozen retrieval을 식별한다.

### 단계별 회수·탈락 원장

| run | arm | stage | kind | 후보 before→after | added / discarded | gold before→after | gold gain / loss | recall | 주요 탈락 이유 |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| run-001 | hardened-v2 | repository-audit | not_applicable | - | - | - | - | - | retrieval 미변경 |

후보를 바꾸는 실험은 `case_id + canonical article-root coordinate` 단위로 모든 실행 단계를
기록한다. 후보 snapshot은 gold-free로 고정하고 gold recall·탈락 이유는 선택 완료 뒤 결합한다.

## 9. 해석

사실: 활성 v5 영수증이 검증되고 wheel·코드 번들 계약 및 1960개 테스트가 통과했다.
해석: 저장 경로를 기록에서 직접 재작성하지 않고 영수증 경계에서 해석하는 방식이
현재 저장소의 영구 v2 이행에 충분하다.

## 10. 한계와 일반화 가능 범위

GenOS 호스트에서의 실제 활성화·rollback·관찰은 배포 작업이므로 포함하지 않았다.
첫 감사 전에 판정 기준을 동결하지 않았으므로 이 기록은 효과성 결정이나 MAIN 승격 근거가 아니다.
Legal Graph의 observation→승인 경계 변경도 별도 실험 범위다.

## 11. 운영 결정·롤백 조건

MAIN 검색·답변 배선은 변경하지 않는다. 코드 generation은
`20260904-code-v5`를 가리키며 기존 v10 활성화 영수증을 경로 이력으로 보존한다.
활성 영수증/hash 검증 또는 기본 회귀가 실패하면 이전 generation binding으로 되돌린다.

MAIN 승격 후보라면 완료 시 front matter를 `main_wiring: promotion-candidate`로 바꾸고,
`scripts/rag_main_promotion.py prepare`로 별도 hash 고정 plan을 만든다. 실험 결과만으로
자동 승격하거나 이 ADR manifest를 사후 수정해 `promoted` 상태를 쓰지 않는다.

## 12. 재현 명령

```bash
06_TOOLS/check_wsl_dev_environment.sh
.venv/bin/python -B 06_TOOLS/publish_code_generation.py --generation 20260904-code-v5
.venv/bin/python -B -m pip wheel --no-deps --no-build-isolation .
.venv/bin/python -B -m pytest -q
```

- 원시 산출물: [artifacts/manifest.json](artifacts/manifest.json)
- 질문 파일 hash: [실험/manifest.json](실험/manifest.json)
