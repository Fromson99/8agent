"""Render ADR-0484 from its sealed result without any additional model call."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0484-qwen-reference-harness-smoke'
OUT = ADR / 'artifacts/run-001'


def read(path):
    return json.loads(Path(path).read_text())


def write(path, text):
    Path(path).write_text(text.rstrip() + '\n')


def write_json(path, value):
    write(path, json.dumps(value, ensure_ascii=False, indent=2))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def block(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def main():
    result, fixture = read(OUT / 'result.json'), read(ADR / 'fixture.json')
    usage = result['usage'][0]
    cases = {row['case_id']: row for row in fixture['cases']}
    scores = {row['case_id']: row for row in result['scores']}
    manifest_path = ADR / '실험/manifest.json'
    manifest = read(manifest_path)
    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    candidate_only = sum(row['qwen_harness_exact'] and not row['baseline_exact'] for row in result['scores'])
    baseline_only = sum(row['baseline_exact'] and not row['qwen_harness_exact'] for row in result['scores'])
    both = sum(row['baseline_exact'] and row['qwen_harness_exact'] for row in result['scores'])
    neither = len(result['scores']) - candidate_only - baseline_only - both
    manifest['runs'][0].update(status='complete', sha256=sha(OUT / 'result.json'), completed_at=now)
    manifest['results'] = {
        'status': 'complete',
        'by_arm': {
            'baseline': {'correct': result['baseline_exact'], 'total': 6,
                         'accuracy': result['baseline_exact'] / 6,
                         'behavior': 'All six cases remain UNKNOWN', 'model_calls': 0},
            'qwen-harness': {'correct': result['qwen_harness_exact'], 'total': 6,
                             'accuracy': result['qwen_harness_exact'] / 6,
                             'target_set_exact': result['target_set_exact'],
                             'unknown_false_resolutions': result['unknown_false_resolutions'],
                             'outside_candidate_ids': result['outside_candidate_ids'],
                             'success_criteria_pass': result['success'], 'model_calls': 1}
        },
        'comparisons': [{'baseline': 'baseline', 'candidate': 'qwen-harness', 'total': 6,
                         'candidate_only_correct': candidate_only, 'baseline_only_correct': baseline_only,
                         'both_correct': both, 'both_wrong': neither}],
        'judge_disagreements': None,
        'judge_disagreement_note': 'No LLM judge; deterministic exact comparison with pre-frozen gold.',
        'usage': {'product_calls': 1, 'provider': usage['provider'],
                  'upstream_provider': usage['upstream_provider'], 'model': usage['model'],
                  'input_tokens': usage['input_tokens'], 'output_tokens': usage['output_tokens'],
                  'thinking_tokens': usage['thinking_tokens'], 'total_tokens': usage['total_tokens'],
                  'provider_reported_cost_usd': usage['cost_usd']},
        'latency': {'single_batch_seconds': result['seconds'],
                    'p50_p95': 'not meaningful for one physical call'},
        'error_taxonomy': []
    }
    schema_sha = sha(OUT / 'calls/call-001-reference-resolution/validation-schema.json')
    index_rows = []
    for question in manifest['questions']:
        case, score = cases[question['case_id']], scores[question['case_id']]
        prediction = score['prediction']
        paired = ('후보만 정답' if score['qwen_harness_exact'] and not score['baseline_exact'] else
                  '기준만 정답' if score['baseline_exact'] and not score['qwen_harness_exact'] else
                  '둘 다 정답' if score['baseline_exact'] else '둘 다 오답')
        baseline_label = '정답' if score['baseline_exact'] else '오답'
        qwen_label = '정답' if score['qwen_harness_exact'] else '오답'
        index_rows.append(f"| {question['number']:03d} | `{case['case_id']}` | baseline {baseline_label} / Qwen {qwen_label} | {paired} | 없음 | [{question['file']}]({question['file']}) |")
        product_case = {key: value for key, value in case.items() if key != 'gold'}
        text = f"""# 질문 {question['number']:03d} — {case['case_id']}

## 1. 실행 메타

- ADR/run: `ADR-0484 / run-001`
- 실행 상태: `exact`; Qwen 단일 공유 배치
- 제품 모델: `qwen/qwen3.5-122b-a10b` (`OpenRouter` → `{usage['upstream_provider']}`)
- reasoning/thinking: `off / 0 tokens`; repair·fallback: `0 / 0`
- arm: `baseline`, `qwen-harness`

## 2. 사용자 질문 원문

```text
{case['source']}
```

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

```json
{block(case['gold'])}
```

## 4. 제품 입력을 구성한 원값

gold를 제거한 합성 입력이다. corpus 회수·후보 추가·탈락은 없었다.

```json
{block(product_case)}
```

- 전체 corpus: 해당 없음
- 필터 전/후/제시 후보: `{len(case['candidates'])} / {len(case['candidates'])} / {len(case['candidates'])}`
- stage ledger: `not_applicable`; `gold_visible_to_product=false`

### 회수·탈락 단계 원장 — run·arm별

`not_applicable`: fixture의 폐쇄 후보를 그대로 제시했으며 corpus 회수·추가·탈락이 없다.

## 5. 제품 모델 호출 — run·arm별 실제 원문

### baseline

모델 호출 없이 `UNKNOWN / []`를 유지했다.

### qwen-harness system

```text
{result['system']}
```

### qwen-harness user·schema·provider 결과

이 사례는 6건 공유 `cases` 배열의 한 항목이었다. 전체 exact request/response는
`../artifacts/run-001/calls/call-001-reference-resolution/request.json`과
`response.json`에 보존했다. validation schema SHA-256은 `{schema_sha}`다.

서버 정규화 결과:

```json
{block(prediction)}
```

공유 호출 사용량: 입력 `{usage['input_tokens']}`, 출력 `{usage['output_tokens']}`, thinking
`{usage['thinking_tokens']}`, 합계 `{usage['total_tokens']}` tokens, 비용 `${usage['cost_usd']}`,
provider 지연 `{usage['seconds']}`초.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

없음. 폐쇄 ID 검증과 상태 계산은 frozen server protocol의 결정론 로직이다.

## 7. 채점 호출과 반복 판정

LLM judge 0회, 반복 1회. 동결 gold와 `(resolution_state, selected_candidate_ids)`를 exact 비교했다.

## 8. 사례 최종 판정

| arm | 정답 | 상태 / candidate IDs | 실패 유형 |
|---|---:|---|---|
| baseline | {str(score['baseline_exact']).lower()} | UNKNOWN / [] | {'없음' if score['baseline_exact'] else 'other:unresolved_baseline'} |
| qwen-harness | {str(score['qwen_harness_exact']).lower()} | {prediction['resolution_state']} / {prediction['selected_candidate_ids']} | 없음 |

- paired 분류: {paired}
- 직접 원인: Qwen ID 선택을 폐쇄 검증한 뒤 서버가 선택 개수로 상태를 계산해 동결 gold와 일치했다.
- 한계: 합성 인샘플 단회라 일반화·운영 승격 근거가 아니다.
"""
        qpath = ADR / '실험' / question['file']
        write(qpath, text)
        question['sha256'] = sha(qpath)
    write(ADR / '실험/README.md', f"""# ADR-0484 실험 질문 인덱스

합성 6건을 Qwen 한 배치로 실행하고 현재 frozen server protocol로 ID와 상태를 검증했다.

## 계보와 arm

- 부모: `ADR-0483-experiment-v1/qwen-review`
- `baseline`: 전부 UNKNOWN 유지
- `qwen-harness`: Qwen은 ID만 선택/기권하고 서버가 0/1/2+ 상태 계산
- MAIN·GENOS 배선: 변경 없음

## 질문 인덱스

| 번호 | case ID | arm별 판정 | paired 분류 | 실패 유형 | 파일 |
|---:|---|---|---|---|---|
{chr(10).join(index_rows)}

## 집계

- baseline: `{result['baseline_exact']}/6`
- Qwen+서버 정규화: `{result['qwen_harness_exact']}/6`
- target ID 집합: `{result['target_set_exact']}/6`
- UNKNOWN 오연결 / 후보 밖 ID: `{result['unknown_false_resolutions']} / {result['outside_candidate_ids']}`
- paired: 후보만 `{candidate_only}`, 기준만 `{baseline_only}`, 둘 다 정답 `{both}`, 둘 다 오답 `{neither}`
- judge: 없음; 동결 gold 결정론 채점
- retrieval: 해당 없음; fixture 폐쇄 후보 그대로 제시

[기계 판독 manifest](manifest.json) · [전체 결과](../artifacts/run-001/result.json)
""")
    write_json(manifest_path, manifest)
    readme = f"""---
adr_id: ADR-0484
title: Qwen 참조 해소 하네스 소표본 smoke
status: Proposed
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

# ADR-0484: Qwen 참조 해소 하네스 소표본 smoke

## 1. 결정 요약

소표본 smoke는 사전 기준을 모두 통과했다. Qwen 후보 ID 집합과 서버 정규화 상태가 `6/6`,
UNKNOWN 오연결과 후보 밖 ID가 모두 0이었다. 다만 합성 6건·단회 인샘플이므로 결정은 `Proposed`이며
MAIN과 GENOS를 변경하지 않는다.

## 2. 문제와 변경 전 구조

ADR-0483은 대상 ID 집합은 맞았지만 모델이 복수 상태를 잘못 출력해 엄격 기준이 `8/12`였다.
현재 구현은 모델에게 상태 필드를 주지 않고 서버가 선택 개수로 계산한다. 이 계약을 실제 Qwen으로 확인했다.

## 3. 가설과 사전 판정 기준

[PLAN](PLAN.md)과 [동결 설계](artifacts/frozen-design.json)에 6/6 exact, UNKNOWN 오연결 0,
후보 밖 ID 0, 1회·$0.05·120초 한계를 첫 호출 전에 고정했다. 하나라도 실패하면 Rejected로 두기로 했다.

## 4. 실험 설계

| arm | 변경점 | 고정 조건 | 목적 |
|---|---|---|---|
| baseline | 6건 모두 UNKNOWN | 같은 합성 사례·후보·gold-free 입력 | 안전한 미해소 기준 |
| qwen-harness | Qwen ID 선택 후 서버 0/1/2+ 상태 계산 | 1회, temperature 0, reasoning off, no repair/fallback | 현재 계약 smoke |

## 5. 데이터·모델·재현성

ADR-0483 합성 사례 중 범위 2, 문맥 2, 기권 2를 결과 확인 전 고정했다. 내부 자료와 실제 내규는 없다.
모델은 사용자 지정 `qwen/qwen3.5-122b-a10b`, upstream `{usage['upstream_provider']}`였고,
frozen current protocol과 schema를 research-only snapshot에서 읽었다. gold는 제품 입력에서 제거했다.

## 6. 결과

| arm | 정답/전체 | 정확도 | baseline 대비 | 호출 |
|---|---:|---:|---:|---:|
| baseline | {result['baseline_exact']}/6 | {result['baseline_exact']/6:.1%} | - | 0 |
| qwen-harness | {result['qwen_harness_exact']}/6 | {result['qwen_harness_exact']/6:.1%} | +{candidate_only}건 | 1 |

paired 결과는 후보만 `{candidate_only}`, 기준만 `{baseline_only}`, 둘 다 정답 `{both}`, 둘 다 오답 `{neither}`다.
target ID 집합도 `6/6`, UNKNOWN 오연결 0, 후보 밖 ID 0이었다.

## 7. 사례별 오류 분석

실패 사례는 없다. [질문별 실제 입력·출력](실험/README.md)에 여섯 사례를 모두 기록했다.

## 8. 비용·지연·회수 규모

- 입력 `{usage['input_tokens']}`, 출력 `{usage['output_tokens']}`, thinking `{usage['thinking_tokens']}`,
  총 `{usage['total_tokens']}` tokens
- provider 보고 비용: `${usage['cost_usd']}`
- 전체 지연: `{result['seconds']}`초; 단회라 p50/p95 일반화 불가
- corpus 회수 없음; 사례당 2~4개의 동결 폐쇄 후보만 제시

## 9. 해석

이 소표본에서는 ADR-0483의 상태 라벨 실패를 서버 cardinality 계산이 제거했다. Qwen은 범위·문맥의
정확 ID를 선택하고 근거 부족·버전 충돌에는 기권했다. 이는 하네스 계약의 동작 확인이지 전체 후보 생성
recall이나 실제 내부 규정 정확도 확인은 아니다.

## 10. 한계와 일반화 가능 범위

합성 6건, 단일 batch, 한 번 실행한 인샘플 smoke다. 외부 Qwen FP8 대리 결과이며 GENOS 내부 endpoint,
실제 7,076개 후보 사례, 운영자 검토 처리량은 검증하지 않았다. 독립 judge도 사용하지 않았다.

## 11. 운영 결정·롤백 조건

`Proposed`, MAIN 불변, GENOS 미배포다. 적용한 운영 변경이 없으므로 rollback 대상도 없다.
후속 holdout과 GENOS 내부 검증 없이는 승인 결과를 navigation에 적용하지 않는다.

## 12. 재현 명령

완료된 `run-001`은 재호출을 거부한다. 재실행은 새 ADR을 사용한다.

```bash
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0484/run_smoke.py
.venv/bin/python 06_TOOLS/run_tool.py adr_candidate.py validate 02_BACKEND/lawrag/research/candidates/adr_0484/qwen-reference-harness
.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0484-qwen-reference-harness-smoke --final
```

[전체 결과](artifacts/run-001/result.json) · [산출물 manifest](artifacts/manifest.json) · [실험 manifest](실험/manifest.json)
"""
    write(ADR / 'README.md', readme)
    artifact_paths = [ADR / 'PLAN.md', ADR / 'fixture.json', ADR / 'artifacts/frozen-design.json',
                      CANDIDATE := ROOT / '02_BACKEND/lawrag/research/candidates/adr_0484/qwen-reference-harness/candidate.json',
                      ROOT / '06_TOOLS/EXPERIMENTS/adr_0484/run_smoke.py']
    artifact_paths += sorted(path for path in OUT.rglob('*') if path.is_file())
    files = []
    for path in artifact_paths:
        relative = path.relative_to(ROOT).as_posix()
        raw = any(name in path.name for name in ('request.json', 'response.json', 'output.json', 'result.json'))
        files.append({'path': relative, 'sha256': sha(path), 'bytes': path.stat().st_size,
                      'description': 'Frozen design/input/code or sealed Qwen request/output/result',
                      'contains_raw_prompts_and_outputs': raw})
    write_json(ADR / 'artifacts/manifest.json', {
        'schema_version': 'adr-artifacts-v1', 'adr_id': 'ADR-0484',
        'created_at': manifest['reservation']['created_at'], 'files': files})


if __name__ == '__main__':
    main()
