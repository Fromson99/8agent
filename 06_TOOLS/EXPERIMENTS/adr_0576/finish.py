"""Document the completed synthetic probe without changing MAIN wiring."""
import hashlib
import json
from pathlib import Path

from harness import R, A, write, sha

RUN = A / "artifacts/run-001"
ARMS = ("baseline", "guide_direct", "guide_compact")


def read(path):
    return json.loads(path.read_text())


def main():
    m = read(A / "실험/manifest.json")
    grade = read(RUN / "offline-grade.json")
    review = read(RUN / "semantic-review.json")
    by = grade["by_arm"]
    assert len(review["rows"]) == 12
    grade["answer_semantic_review"] = {
        "artifact": str((RUN / "semantic-review.json").relative_to(R)),
        "source_supported_candidates": all(row["status"].startswith("SOURCE_SUPPORTED")
                                          for row in review["rows"] if row["arm"] != "baseline"),
        "baseline_no_substantive_answer": [row["case_id"] for row in review["rows"]
                                            if row["status"] == "NO_SUBSTANTIVE_ANSWER"],
        "independent_legal_review": False,
    }
    grade["interpretation"] = (
        "Direct GUIDE recall is mechanically verified, but provider latency dominated one baseline "
        "request (S02: 312.9s), so the paired mean cannot certify an operational speed win. "
        "Compact planning reduced tokens and was faster on three of four pairs; n=4 synthetic "
        "single-run evidence is insufficient for MAIN promotion."
    )
    write(RUN / "offline-grade.json", grade)
    m["results"]["comparisons"] = [{"baseline": "baseline", "candidate": arm,
        "source_citation_pass": by[arm]["source_citation_pass"],
        "rank_calls": {"baseline": by["baseline"]["fulltext_rank_calls"],
                       arm: by[arm]["fulltext_rank_calls"]},
        "wall_seconds": {"baseline": by["baseline"]["total_seconds"],
                         arm: by[arm]["total_seconds"]},
        "measured_speed_gate": grade["speed_gate"][arm],
        "speed_certified": False,
        "reason": "one 312.9s baseline provider outlier and n=4 synthetic single run"}
        for arm in ARMS[1:]]
    m["results"]["error_taxonomy"] = [
        {"kind": "empty_answer_after_provider_delay", "case_id": "S02", "arm": "baseline",
         "latency_seconds": next(row["seconds"] for row in read(RUN / "result.json")["results"]
                                 if row["case_id"] == "S02" and row["arm"] == "baseline")},
        {"kind": "speed_inference_limited", "details": "single paired synthetic run; provider tail dominated baseline"}]
    write(A / "실험/manifest.json", m)

    summary = """---
adr_id: ADR-0576
title: GUIDES_TO 직접 원문 회수와 질문계획 축약 실험
status: Proposed
decision_date: 2026-09-30
phase: probe
in_sample: true
decision_eligible: false
main_wiring: unchanged
created_at: 2026-09-30T00:17:39.785785Z
updated_at: 2026-09-30T00:17:39.853803Z
owner: codex
work_status: in_progress
---

# ADR-0576: GUIDES_TO 직접 원문 회수와 질문계획 축약 실험

## 1. 결정 요약

연구용 후보에서 검증된 `GUIDES_TO`의 원문 ID를 직접 읽으면, 해당 조사 목적의 fulltext 순위 검색을 생략할 수 있었다. 질문 계획의 단일 조각을 결정적으로 만들면 첫 계획 입력 토큰도 줄었다. 다만 모델 호출 수는 그대로이고, 외부 모델 지연 이상치와 합성 4문항 단회 실행 때문에 운영 속도 개선은 인증하지 않는다. MAIN·GENOS·활성 릴리스는 바꾸지 않았다.

## 2. 문제와 변경 전 구조

ADR-0575는 야간 생성한 개념·가이드 경로를 온라인 검색 범위에 전달했지만, 실제 원문 회수는 여전히 fulltext를 호출했다. 같은 목적을 위해 이미 알려진 원문을 다시 검색하고, 단일 질문 조각에도 계획 구조를 모델이 중복 생성했다.

## 3. 가설과 사전 판정 기준

현재 데이터 세대에 결속된 활성 GUIDE 원문을 먼저 읽고 근거가 부족하면 기존 검색으로 돌아간다. 계획 축약 후보는 단일 질문 조각의 요구를 질문 원문에서 결정적으로 만들되 다중 조각은 기존 경로를 유지한다. 사전 기준은 4문항 HTTP 성공, guide-hit 3문항 검색 0회, 다른 목적의 통계 질문 검색 복귀, 필수 원문·인용 보존, 후보 평균 종단 지연 비증가와 첫 계획 토큰 감소였다. 정확한 기준은 [실험 manifest](실험/manifest.json)에 있다.

## 4. 실험 설계

세 arm은 같은 합성 3개 원문·야간 구축 개념 DB·Gemma 모델·전체 HTTP `/v1/rag/ask`를 사용했다. `baseline`은 ADR-0575의 기존 통합 경로, `guide_direct`는 원문 직접 회수만 추가, `guide_compact`는 직접 회수와 단일 조각 계획 축약을 결합했다. 4개 질문에서 arm 순서를 바꾸고 각 1회 실행했다. GUIDE 사용 시에도 원문 직접 읽기·선별·답변 생성·인용 검사는 유지했다. 후보 코드는 격리 snapshot으로 고정했다.

## 5. 데이터·모델·재현성

합성 승인 규정 3개 article root와 야간 자동 생성 `GUIDES_TO` 2개를 사용했다. 통계 질문은 목적 불일치 대조군이다. 모델은 `google/gemma-4-31b-it`, OpenRouter Parasail FP8, thinking off, fallback 없음. 사용자 질문·원문·기준 좌표와 코드/DB SHA-256을 manifest에 고정했으며 gold는 제품 실행 후에만 결합했다. 실행기·원시 모델 요청과 응답은 [artifacts](artifacts/manifest.json)에 있다.

## 6. 결과

| arm | 필수 원문·인용 | guide-hit 검색 호출 | 전체 검색 호출 | 모델 호출 | 첫 계획 입력 토큰 | 전체 입력 토큰 | 평균 HTTP 초 |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 3/4 | 20 | 24 | 12 | 6,498 | 18,303 | 94.09 |
| guide_direct | 4/4 | 0 | 4 | 12 | 6,495 | 17,736 | 26.90 |
| guide_compact | 4/4 | 0 | 4 | 12 | 4,931 | 15,993 | 15.24 |

통계 질문은 두 후보 모두 검색 4회로 복귀했다. 두 후보의 답변 8건은 합성 원문과 수동 대조 시 새로운 사실 단정이 없었다. 단순화 후보의 첫 계획 입력 토큰은 direct 대비 24.1%, 전체 입력 토큰은 9.8% 감소했다. 네 쌍 중 단순화 후보가 세 쌍에서 빨랐다. 모델 호출 수가 줄었다는 주장은 하지 않는다.

## 7. 사례별 오류 분석

S02 baseline의 답변 생성 제공자 호출이 지연되어 HTTP가 312.88초 걸렸고, 최종 결과는 인용 없는 한계 문구였다. 따라서 종단 평균에서 baseline을 직접 비교해 운영 속도 이득을 인증할 수 없다. S01 direct는 검색이 0회였지만 45.61초로 baseline 36.04초보다 느렸다. S03 compact는 필요한 승인 원칙 외에 제2조 예외 확인 문구를 덧붙였으나 이는 제1조에 명시된 문구이며 합성 원문 밖의 단정은 아니다. 세부 사항은 [수동 근거 검토](artifacts/run-001/semantic-review.json)와 [문항별 입출력](실험/README.md)에 남겼다.

## 8. 비용·지연·회수 규모

원문 corpus는 3개다. 최종 답변 입력 원문 수는 세 arm 모두 6개/4문항, 필수 좌표 recall은 모두 1.0이다. baseline은 S02에서 인용이 빠져 source-citation gate 3/4다. `guide_direct` 전체 107.58초, `guide_compact` 60.94초이나 baseline 376.34초에는 312.88초 이상치가 포함된다. S02를 제외한 세 질문 합계는 각각 baseline 63.46초, direct 74.02초, compact 44.48초다. 실제 단계별 집합·탈락 사유·gold join은 [회수 원장](artifacts/run-001/retrieval-stage-ledger.json)에 보존했다.

## 9. 해석

검색 생략 메커니즘은 입증됐다: guide-hit 세 질문에서 `ACTION_MEMORY_DIRECT_RECALL`이 각각 발생했고 `FulltextIndex.rank`는 0회였다. 직접 회수만으로 모델 선별 호출이 없어지지는 않는다. 단일 조각 계획 축약은 입력 토큰을 줄였으나 별도 모델 호출 하나를 제거한 것은 아니다. 검색의 SQLite 실행 시간 자체는 작은 합성 corpus에서는 미미하므로, 실제 속도 이득은 모델의 입력 크기·선별 및 답변 단계의 변동에 크게 좌우된다.

## 10. 한계와 일반화 가능 범위

노출된 합성 4문항의 1회 실행이다. 기준 arm의 제공자 꼬리 지연과 빈 답변으로 속도 비교가 불안정하다. 큰 corpus, 다양한 조사 목적, stale GUIDE, 다중 질문 조각, 실제 내부 법률자료, GENOS 지연은 검증하지 않았다. 법률 정확도 독립 심사가 아니라 고정 합성 원문 대조다.

## 11. 운영 결정·롤백 조건

기계적 직접 회수와 축약 계획 후보는 다음 out-of-sample 속도·품질 검증 대상으로 보존한다. 기존 fulltext 경로는 목적 불일치·근거 불충분·데이터 세대 변경 때 필요한 fallback이므로 제거하지 않는다. 선별 모델 단계와 원문 검증도 이번 실험에서는 유지했고 제거 효과는 미측정이다. 활성 MAIN·로컬 릴리스·GENOS 배포 변경 없음.

## 12. 재현 명령

`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0576/run.py`는 고정 입력을 검증하고 새 `run-001`을 생성한다. 완료 run은 덮어쓰지 않으므로 재실행은 새 ADR/run 선점이 필요하다. 오프라인 정리는 `audit.py`와 `finish.py`를 사용하고, `adr_structure.py validate --final`로 계약을 확인한다.
"""
    (A / "README.md").write_text(summary)
    (A / "실험/README.md").write_text(
        "# ADR-0576 질문·실행 인덱스\n\n"
        "[실험 manifest](manifest.json)에 고정 질문·arm·코드·원문 hash를 보존한다. "
        "아래 각 파일에는 실제 HTTP 결과와 모델 원시 요청·응답이 포함된다.\n\n" +
        "\n".join(f"- [{q['case_id']}]({q['file']})" for q in m["questions"]) +
        "\n\n[오프라인 판정](../artifacts/run-001/offline-grade.json) · "
        "[수동 근거 검토](../artifacts/run-001/semantic-review.json) · "
        "[회수 단계 원장](../artifacts/run-001/retrieval-stage-ledger.json)\n")
    files = []
    for path in sorted(set((A / "artifacts").rglob("*")) | set((R / "06_TOOLS/EXPERIMENTS/adr_0576").glob("*.py"))):
        if path.is_file() and path != A / "artifacts/manifest.json":
            files.append({"path": str(path.relative_to(R)), "bytes": path.stat().st_size,
                          "sha256": sha(path),
                          "description": "frozen input, exact model call, product trace, or offline audit",
                          "contains_raw_prompts_and_outputs": "calls" in path.parts})
    for arm in ("guide-direct", "guide-compact"):
        root = R / "02_BACKEND/lawrag/research/candidates/adr_0576" / arm
        for path in sorted(set([root / "candidate.json"]) | set((root / "revisions/rev-001").rglob("*"))):
            if path.is_file():
                files.append({"path": str(path.relative_to(R)), "bytes": path.stat().st_size,
                              "sha256": sha(path), "description": "frozen candidate source",
                              "contains_raw_prompts_and_outputs": False})
    write(A / "artifacts/manifest.json", {"schema_version": "adr-artifacts-v1",
                                           "adr_id": m["adr_id"], "files": files})
    print(json.dumps({"artifacts": len(files), "semantic_review": grade["answer_semantic_review"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
