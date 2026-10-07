"""Render ADR-0483's sealed one-call result without re-running or re-scoring it."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / "04_EXPERIMENTS/ADR/ADR-0483-qwen-ambiguous-reference-probe"
OUT = ADR / "artifacts/run-001"


def read(path: Path):
    return json.loads(path.read_text())


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def block(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def main() -> None:
    result = read(OUT / "result.json")
    fixture = read(ADR / "fixture.json")
    manifest_path = ADR / "실험/manifest.json"
    manifest = read(manifest_path)
    usage = read(OUT / "calls/usage.json")[0]
    cases = {row["case_id"]: row for row in fixture["cases"]}
    scores = {row["case_id"]: row for row in result["scores"]}
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    auth = read(ADR / "artifacts/frozen-design.json")["scope_authorization"]
    manifest["llm_policy"]["experiment_override"]["authorization"] = auth
    manifest["llm_policy"]["experiment_override"]["frozen_design_sha256"] = digest(
        ADR / "artifacts/frozen-design.json"
    )
    manifest["llm_policy"]["llm_calls"][0]["thinking_level"] = "off"

    candidate_only = sum(not row["baseline_exact"] and row["qwen_exact"] for row in result["scores"])
    baseline_only = sum(row["baseline_exact"] and not row["qwen_exact"] for row in result["scores"])
    both_correct = sum(row["baseline_exact"] and row["qwen_exact"] for row in result["scores"])
    both_wrong = len(result["scores"]) - candidate_only - baseline_only - both_correct
    target_set_exact = sum(
        sorted(row["prediction"].get("candidate_ids", [])) == sorted(row["gold"]["candidate_ids"])
        for row in result["scores"]
    )

    manifest["runs"][0].update(
        status="complete", sha256=digest(OUT / "result.json"), completed_at=now
    )
    manifest["results"] = {
        "status": "complete",
        "by_arm": {
            "baseline": {
                "correct": result["baseline_exact"], "total": 12,
                "accuracy": result["baseline_exact"] / 12,
                "behavior": "All selected hard cases remain UNKNOWN",
                "model_calls": 0,
            },
            "qwen-review": {
                "correct": result["qwen_exact"], "total": 12,
                "accuracy": result["qwen_exact"] / 12,
                "target_set_exact": target_set_exact,
                "unknown_false_resolutions": result["criteria"]["unknown_false_resolutions"],
                "outside_candidate_ids": result["criteria"]["outside_candidate_ids"],
                "success_criteria_pass": result["success"],
                "model_calls": 1,
            },
        },
        "comparisons": [{
            "baseline": "baseline", "candidate": "qwen-review", "total": 12,
            "candidate_only_correct": candidate_only,
            "baseline_only_correct": baseline_only,
            "both_correct": both_correct,
            "both_wrong": both_wrong,
        }],
        "judge_disagreements": None,
        "judge_disagreement_note": "No LLM judge; deterministic comparison with pre-frozen gold.",
        "usage": {
            "product_calls": 1,
            "provider": usage["provider"],
            "upstream_provider": usage["upstream_provider"],
            "model": usage["model"],
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
            "thinking_tokens": usage["thinking_tokens"],
            "total_tokens": usage["total_tokens"],
            "provider_reported_cost_usd": usage["cost_usd"],
        },
        "latency": {"single_batch_seconds": result["seconds"], "p50_p95": "not meaningful for one call"},
        "error_taxonomy": [{
            "type": "other:decision_cardinality_label",
            "count": 4,
            "cases": ["range-001", "range-002", "range-003", "range-004"],
            "note": "All target ID sets were exact, but Qwen returned RESOLVED instead of frozen MULTI_TARGET.",
        }],
    }
    write_json(manifest_path, manifest)

    system = result["system"]
    schema_hash = digest(OUT / "calls/call-001-reference-review/validation-schema.json")
    rows = []
    for question in manifest["questions"]:
        case_id = question["case_id"]
        case = cases[case_id]
        score = scores[case_id]
        baseline = "정답" if score["baseline_exact"] else "오답"
        qwen = "정답" if score["qwen_exact"] else "오답"
        paired = (
            "후보만 정답" if score["qwen_exact"] and not score["baseline_exact"] else
            "기준만 정답" if score["baseline_exact"] and not score["qwen_exact"] else
            "둘 다 정답" if score["baseline_exact"] else "둘 다 오답"
        )
        failure = "없음" if score["qwen_exact"] else "other:decision_cardinality_label"
        rows.append(
            f'| {question["number"]:03d} | `{case_id}` | `run-001` | baseline {baseline} / Qwen {qwen} | '
            f'{paired} | {failure} | [{question["file"]}]({question["file"]}) |'
        )
        product_case = {k: v for k, v in case.items() if k != "gold"}
        question_text = f"""# 질문 {question['number']:03d} — {case_id}

## 1. 실행 메타

- 실행: `2026-09-21 / run-001 / baseline, qwen-review / exact`
- 제품 모델: `qwen/qwen3.5-122b-a10b` (`OpenRouter` → `{usage['upstream_provider']}`, reasoning 0)
- 오프라인 평가 모델: 없음. 동결 gold와 결정론적으로 비교
- 공유 단일 배치 원문: `../artifacts/run-001/calls/call-001-reference-review/`

## 2. 사용자 질문 원문

```text
{case['source']}
```

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

```json
{block(case['gold'])}
```

## 4. 제품 입력을 구성한 원값

회수는 실행하지 않았다. 제품에는 아래 폐쇄 후보와 근거만 제시했고 gold는 제거했다.

```json
{block(product_case)}
```

단계 원장: `not_applicable` — corpus 검색이나 후보 추가·제거가 없었다. 후보 수는 {len(case['candidates'])}개,
제품 제시 수도 {len(case['candidates'])}개이며 gold는 제품 선택 완료 후에만 결합했다.

### 회수·탈락 단계 원장 — run·arm별

`not_applicable`: 이 사례는 fixture의 폐쇄 후보를 그대로 제시했으며 corpus 회수·추가·탈락이 없다.

## 5. 제품 모델 호출 — run·arm별 실제 원문

### system

```text
{system}
```

### user

이 사례는 `{{"cases": [...]}}` 형태의 12건 공유 배치 중 위 JSON 한 항목으로 전달됐다.
전체 exact 요청은 `../artifacts/run-001/calls/call-001-reference-review/request.json`에 보존했다.

### schema·structured output·usage

- validation schema SHA-256: `{schema_hash}`
- 이 사례 structured output:

```json
{block(score['prediction'])}
```

- 공유 배치 usage: 입력 {usage['input_tokens']} / 출력 {usage['output_tokens']} / thinking {usage['thinking_tokens']} /
  합계 {usage['total_tokens']} tokens, `${usage['cost_usd']}`, {usage['seconds']}초
- 전체 provider 원응답: `../artifacts/run-001/calls/call-001-reference-review/response.json`

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

없음. router/compiler/verifier/repair 및 fallback은 모두 0회다.

## 7. 채점 호출과 반복 판정

LLM judge 0회, 반복 1회. 동결한 decision과 candidate ID 집합이 모두 같을 때만 정답으로 계산했다.

## 8. 사례 최종 판정

| arm | 정답 | decision / candidate IDs | 실패 유형 |
|---|---:|---|---|
| baseline | {str(score['baseline_exact']).lower()} | UNKNOWN / [] | {'없음' if score['baseline_exact'] else 'other:unresolved_baseline'} |
| qwen-review | {str(score['qwen_exact']).lower()} | {score['prediction'].get('decision')} / {score['prediction'].get('candidate_ids')} | {failure} |

- paired 분류: {paired}
- 직접 원인: {'없음' if score['qwen_exact'] else '대상 ID는 모두 맞았으나 복수 대상을 MULTI_TARGET이 아닌 RESOLVED로 표시했다.'}
- 후속 가설: 복수 여부를 LLM 자유 판정에 맡기지 말고 `candidate_ids` 길이로 결정론적 정규화한다.
"""
        (ADR / "실험" / question["file"]).write_text(question_text)

    experiment_index = """# ADR-0483 실험 질문 인덱스

합성 12건을 Qwen 한 배치로 실행했다. 내부 자료·실제 법령 corpus·GENOS는 사용하지 않았다.

## 계보와 arm

- `baseline`: 선택된 난제 12건을 모두 UNKNOWN으로 보존
- `qwen-review`: 폐쇄 후보·근거 안에서 Qwen이 RESOLVED/MULTI_TARGET/UNKNOWN 선택
- 부모: `ADR-0467-experiment-v1/resolver`; MAIN 배선 변경 없음

## 질문 인덱스

| 번호 | case ID | run | arm별 판정 | paired 분류 | 실패 유형 | 파일 |
|---:|---|---|---|---|---|---|
""" + "\n".join(rows) + f"""

## 집계

- baseline: {result['baseline_exact']}/12
- Qwen frozen primary metric: {result['qwen_exact']}/12 — 사전 기준 10/12 미달
- 진단용 target ID 집합 일치: {target_set_exact}/12
- UNKNOWN 오연결: {result['criteria']['unknown_false_resolutions']}/4
- 후보 밖 ID: {result['criteria']['outside_candidate_ids']}건
- paired: 후보만 {candidate_only}, 기준만 {baseline_only}, 둘 다 정답 {both_correct}, 둘 다 오답 {both_wrong}
- judge: 없음; 동결 gold 결정론 채점
- retrieval stage ledger: 해당 없음(폐쇄 후보 fixture, corpus 회수 미실행)

[기계 판독 manifest](manifest.json) · [전체 결과](../artifacts/run-001/result.json)
"""
    (ADR / "실험/README.md").write_text(experiment_index)

    readme = f"""---
adr_id: ADR-0483
title: Qwen 범위·애매 참조 제한 후보 해소 probe
status: Rejected
decision_date: 2026-09-21
phase: probe
in_sample: true
decision_eligible: false
main_wiring: unchanged
created_at: {manifest['reservation']['created_at']}
updated_at: {manifest['reservation']['updated_at']}
owner: Codex
work_status: in_progress
---

# ADR-0483: Qwen 범위·애매 참조 제한 후보 해소 probe

## 1. 결정 요약

Qwen 제한 후보 해소는 사전 기준을 통과하지 못해 `Rejected`다. 엄격 일치는 8/12(기준 10/12),
UNKNOWN 오연결 0/4, 후보 밖 생성 0건이었다. 범위 4건의 대상 ID 집합은 모두 맞았지만
`MULTI_TARGET` 대신 `RESOLVED`를 반환했다. 운영 MAIN과 GENOS 배선은 변경하지 않았다.

## 2. 문제와 변경 전 구조

현행 결정 규칙이 해소하지 못하는 범위·약칭·문맥 참조를 LLM이 보조할 수 있는지 확인했다.
baseline은 이 12개 난제를 모두 UNKNOWN으로 남기므로 애매한 연결을 만들지 않지만 해소율이 낮다.

## 3. 가설과 사전 판정 기준

[PLAN](PLAN.md)과 [동결 설계](artifacts/frozen-design.json)를 첫 호출 전에 고정했다.
정확 decision+ID 집합 10/12 이상, 의도적 UNKNOWN 4건 오연결 0, 후보 밖 ID 0,
비용 $0.10 이하, 지연 120초 이하를 모두 요구했다. 하나라도 실패하면 승격하지 않기로 했다.

## 4. 실험 설계

| arm | 변경점 | 고정 조건 | 목적 |
|---|---|---|---|
| baseline | 12건 모두 UNKNOWN 보존 | 같은 합성 사례·후보·근거 | 안전한 현행 동작 |
| qwen-review | Qwen 1회가 폐쇄 후보 안에서 판정 | gold 제거, 수리·fallback·judge 없음 | 애매 참조 제한 해소 |

범위 4, 약칭/문맥 4, 반드시 UNKNOWN 4건이다. 결과를 본 뒤 프롬프트·코드·gold를 수정하거나 재호출하지 않았다.

## 5. 데이터·모델·재현성

모두 손으로 만든 합성 입력이며 내부 문서와 실제 법령 본문은 전송하지 않았다.
`qwen/qwen3.5-122b-a10b`, temperature 0, reasoning off, OpenRouter FP8 경로를 사용했다.
실제 upstream은 `{usage['upstream_provider']}`였다. 기준답은 제품 입력에서 제거했으며 호출 원문과 응답을 보존했다.
첫 호출 전 동결본은 `frozen-design-pre-validator-normalization.json`에 그대로 보존했다. 이후 stable validator가 요구하는
`scope_authorization/configs` 바인딩 필드만 같은 내용으로 추가했으며 모델·입력·기준·결과는 변경하지 않았다.

## 6. 결과

| arm | 정답/전체 | 정확도 | baseline 대비 | 호출 |
|---|---:|---:|---:|---:|
| baseline | {result['baseline_exact']}/12 | {result['baseline_exact']/12:.1%} | - | 0 |
| qwen-review | {result['qwen_exact']}/12 | {result['qwen_exact']/12:.1%} | +4건 | 1 |

| paired outcome | 건수 |
|---|---:|
| 후보만 정답 | {candidate_only} |
| 기준만 정답(회귀) | {baseline_only} |
| 둘 다 정답 | {both_correct} |
| 둘 다 오답 | {both_wrong} |

사전 primary metric은 8/12로 실패했다. 별도 진단상 대상 ID 집합만 보면 12/12였지만,
이는 결과 확인 전 성공 기준이 아니므로 통과로 바꾸지 않는다.

## 7. 사례별 오류 분석

| 실패 유형 | 건수 | 사례 | 해석 |
|---|---:|---|---|
| decision cardinality label | 4/12 | range-001~004 | 복수 ID를 정확히 골랐지만 MULTI_TARGET 대신 RESOLVED |

[질문별 실제 입출력과 판정](실험/README.md)에 전부 연결했다.

## 8. 비용·지연·회수 규모

- 제품 호출 1회: 입력 {usage['input_tokens']:,}, 출력 {usage['output_tokens']:,}, thinking {usage['thinking_tokens']:,}, 총 {usage['total_tokens']:,} tokens
- provider 보고 비용: `${usage['cost_usd']:.7f}`
- 전체 지연: `{result['seconds']}`초
- corpus 회수: 해당 없음. fixture의 폐쇄 후보만 모델에 제시했으며 검색·추가·탈락 단계가 없다.

단회 호출이라 p50/p95는 일반화할 수 없다.

## 9. 해석

Qwen은 약칭·상대 참조 4건을 해소하고, 근거 부족·구조 부재·버전 충돌 4건을 모두 UNKNOWN으로 유지했다.
범위 확장 대상도 정확했으므로 의미 선택 가능성은 보였지만 출력 상태 계약을 그대로 맡기는 설계는 통과하지 못했다.
후속 실험은 모델이 ID와 근거만 고르게 하고, 0개→UNKNOWN·1개→RESOLVED·2개 이상→MULTI_TARGET으로
서버가 정규화하는 방식이 적절하다는 가설을 새 ADR에서 검증해야 한다.

## 10. 한계와 일반화 가능 범위

합성 12건, 단회, in-sample이며 독립 holdout·전문가 judge가 없다. 폐쇄 후보 생성 자체의 recall도 측정하지 않았다.
로컬 외부 proxy 결과이지 GENOS 내부 Qwen, 실제 내부 규정, 전체 법령 corpus 성능이 아니다.

## 11. 운영 결정·롤백 조건

Rejected. 운영 코드·기본 registry·활성 릴리스·용어집·참조 index·GENOS 배포를 모두 그대로 유지했다.
격리된 연구 후보와 실패 기록만 보존한다. 따라서 롤백할 운영 변경은 없다.

## 12. 재현 명령

완료된 `run-001` 디렉터리가 있으면 실행기가 재호출을 거부한다. 유료 재실행이나 정규화 후보 평가는 새 ADR이 필요하다.

```bash
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0483/run_probe.py
.venv/bin/python 06_TOOLS/run_tool.py adr_candidate.py validate 02_BACKEND/lawrag/research/candidates/adr_0483/qwen-reference-review
.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0483-qwen-ambiguous-reference-probe --final
```

[원시 결과](artifacts/run-001/result.json) · [산출물 manifest](artifacts/manifest.json) · [실험 manifest](실험/manifest.json)
"""
    (ADR / "README.md").write_text(readme)

    artifact_manifest = read(ADR / "artifacts/manifest.json")
    artifact_paths = [p for p in (ADR / "artifacts").rglob("*") if p.is_file() and p.name != "manifest.json"]
    artifact_paths += [ADR / "PLAN.md", ADR / "fixture.json"]
    artifact_manifest["files"] = [{
        "path": str(path.relative_to(ROOT)),
        "sha256": digest(path),
        "bytes": path.stat().st_size,
        "description": "Frozen design, synthetic fixture, or sealed Qwen request/output/result",
        "contains_raw_prompts_and_outputs": path.name in {"request.json", "response.json", "output.json", "result.json"},
    } for path in sorted(set(artifact_paths))]
    write_json(ADR / "artifacts/manifest.json", artifact_manifest)
    print(json.dumps({
        "strict_exact": result["qwen_exact"], "target_set_exact": target_set_exact,
        "unknown_false_resolutions": result["criteria"]["unknown_false_resolutions"],
        "success": result["success"], "status": "Rejected",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
