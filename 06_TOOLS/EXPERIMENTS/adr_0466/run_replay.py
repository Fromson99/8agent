"""ADR-0466 runner: legal_agent composer rev-002 (fixed items, answer-first audit, absence allowed).

Same replay inputs as ADR-0465 (run1 adopted public evidence), same ADR-0462 judge contract, two runs per arm.

    .venv/bin/python <this> freeze    # inputs + reference answers, no model call
    .venv/bin/python <this> compose   # 4 arms x 2 runs
    .venv/bin/python <this> judge     # every arm/run + 3 reference arms
    .venv/bin/python <this> score
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
sys.dont_write_bytecode = True
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ART = ROOT / '04_EXPERIMENTS/ADR/ADR-0466-legal-agent-composer-audit/artifacts'
CAND = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0466/legal-agent-v2'
FROZEN = CAND / 'revisions/rev-001/snapshot/02_BACKEND'
sys.path.insert(0, str(ROOT / '02_BACKEND'))
sys.path.insert(0, str(FROZEN))

ADR65 = ROOT / '04_EXPERIMENTS/ADR/ADR-0465-legal-agent-composer-replay/artifacts'
ADR62 = ROOT / '04_EXPERIMENTS/ADR/ADR-0462-cm-golden-answer-correctness-regrade/artifacts'
NEW_ARMS = {'plain-flash': ('flash-lite-exp', 'plain'), 'audit-flash': ('flash-lite-exp', 'audit'),
            'plain-qwen': ('genos-qwen-proxy', 'plain'), 'audit-qwen': ('genos-qwen-proxy', 'audit')}
REFERENCE = {'baseline': 'run1 답변 원문', 'v1-plain-flash': 'ADR-0465 compose-flash',
             'v1-ledger-qwen': 'ADR-0465 compose-qwen-ledger'}
RUNS = ['run-001', 'run-002']
GAP = ['cm-003', 'cm-013', 'cm-014', 'cm-025', 'cm-027', 'cm-028', 'cm-034', 'cm-042', 'cm-045', 'cm-047']
ORDER_SEED = 4660
WORKERS = 4
LOCK = threading.Lock()


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def read(path: Path):
    return json.loads(Path(path).read_text())


def write(path: Path, obj) -> None:
    tmp = Path(str(path) + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def judge_user(question: str, reference: str, answer: str) -> str:
    return (f"[질문]\n{question}\n\n[기준답변]\n{reference}\n\n"
            f"[시스템 답변]\n{answer}\n\n"
            "reason은 3문장 이내, missing_points는 최대 5개의 짧은 항목으로 쓴다.")


def check_client_pin() -> dict:
    frozen = CAND / 'revisions/rev-001/snapshot/02_BACKEND/lawrag/research/experiment_client.py'
    live = ROOT / '02_BACKEND/lawrag/research/experiment_client.py'
    if sha(frozen) != sha(live):
        raise SystemExit('experiment_client drifted from the frozen revision; refuse to run')
    return {'frozen': str(frozen.relative_to(ROOT)), 'sha256': sha(frozen)}


def freeze() -> None:
    base = read(ADR65 / 'frozen-inputs.json')
    v1 = read(ADR65 / 'compose-results.json')['results']
    cases = []
    for case in base['cases']:
        cid = case['case_id']
        cases.append({**case, 'reference_texts': {
            'baseline': case['baseline_answer'],
            'v1-plain-flash': v1[f'{cid}::compose-flash']['text'],
            'v1-ledger-qwen': v1[f'{cid}::compose-qwen-ledger']['text']}})
    frozen = {'schema_version': 'adr0466-frozen-inputs-v1',
              'inherited_inputs': '04_EXPERIMENTS/ADR/ADR-0465-legal-agent-composer-replay/artifacts/frozen-inputs.json',
              'inherited_sha256': sha(ADR65 / 'frozen-inputs.json'),
              'v1_results_sha256': sha(ADR65 / 'compose-results.json'),
              'golden_sha256': base['golden_sha256'], 'candidate_revision': 'rev-001',
              'candidate_json_sha256': sha(CAND / 'candidate.json'), 'client_pin': check_client_pin(),
              'judge_system': base['judge_system'], 'judge_system_sha256': base['judge_system_sha256'],
              'judge_schema': base['judge_schema'], 'new_arms': NEW_ARMS, 'reference_arms': REFERENCE,
              'runs': RUNS, 'gap_cases': GAP, 'order_seed': ORDER_SEED, 'cases': cases}
    write(ART / 'frozen-inputs.json', frozen)
    print(f"frozen {len(cases)} cases; units {sum(len(c['units']) for c in cases)}; "
          f"no-evidence {sum(not c['units'] for c in cases)}; arms {len(NEW_ARMS)}x{len(RUNS)} + {len(REFERENCE)} reference")


def compose() -> None:
    from legal_agent.contracts import EvidenceUnit
    from legal_agent.models import experiment_model
    from legal_agent.pipeline import answer_from_evidence
    from legal_agent.profiles import PROFILES
    check_client_pin()
    frozen = read(ART / 'frozen-inputs.json')
    out_path = ART / 'compose-results.json'
    out = read(out_path) if out_path.exists() else {'schema_version': 'adr0466-compose-v1', 'results': {}}
    for run_id in RUNS:
        for arm, (profile_name, mode) in NEW_ARMS.items():
            profile = PROFILES[profile_name]
            todo = [c for c in frozen['cases'] if f"{c['case_id']}::{arm}::{run_id}" not in out['results']]
            buckets = [todo[i::WORKERS] for i in range(WORKERS)]

            def worker(no: int, cases: list[dict]) -> None:
                model = experiment_model(profile, ROOT, ART / 'calls' / run_id / arm / f'worker-{no}',
                                         max_calls=4 * len(cases) + 2)
                for case in cases:
                    units = [EvidenceUnit(**u) for u in case['units']]
                    before = model.calls
                    try:
                        answer = answer_from_evidence(model, case['question'], units, mode=mode,
                                                      phase=f"compose-{case['case_id']}")
                        row = {'text': answer.text, 'answer': answer.to_json(), 'error': None}
                    except Exception as exc:
                        row = {'text': '(답변 생성 실패)', 'answer': None,
                               'error': f'{type(exc).__name__}: {exc}'[:500]}
                    row.update(arm=arm, run=run_id, case_id=case['case_id'], profile=profile_name, mode=mode,
                               calls=model.calls - before, usage=[u for u in model.usage if u['call'] > before])
                    with LOCK:
                        out['results'][f"{case['case_id']}::{arm}::{run_id}"] = row
                        write(out_path, out)

            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                for future in [pool.submit(worker, i, b) for i, b in enumerate(buckets) if b]:
                    future.result()
            done = sum(1 for k in out['results'] if k.endswith(f'::{arm}::{run_id}'))
            errors = sum(1 for k, v in out['results'].items() if k.endswith(f'::{arm}::{run_id}') and v['error'])
            print(f'{run_id} {arm}: {done}/51 composed, errors {errors}', flush=True)


def judged_items() -> dict[str, dict]:
    frozen = read(ART / 'frozen-inputs.json')
    composed = read(ART / 'compose-results.json')['results']
    items = {}
    for case in frozen['cases']:
        cid = case['case_id']
        for arm, text in case['reference_texts'].items():
            items[f'{cid}::{arm}::run-001'] = {'case_id': cid, 'arm': arm, 'run': 'run-001', 'text': text}
        for run_id in RUNS:
            for arm in NEW_ARMS:
                items[f'{cid}::{arm}::{run_id}'] = {'case_id': cid, 'arm': arm, 'run': run_id,
                                                    'text': composed[f'{cid}::{arm}::{run_id}']['text']}
        for key in list(items):
            if key.startswith(cid + '::'):
                items[key].update(question=case['question'], reference=case['reference_answer'])
    return items


def judge() -> None:
    from lawrag.research.experiment_client import GeminiExperimentClient
    frozen = read(ART / 'frozen-inputs.json')
    items = judged_items()
    out_path = ART / 'judged-results.json'
    out = read(out_path) if out_path.exists() else {'schema_version': 'adr0466-judged-v1', 'results': {}}
    order = sorted(items)
    random.Random(ORDER_SEED).shuffle(order)
    todo = [k for k in order if k not in out['results']]
    buckets = [todo[i::WORKERS] for i in range(WORKERS)]

    def worker(no: int, keys: list[str]) -> None:
        client = GeminiExperimentClient(ROOT, ART / 'judge-calls' / f'worker-{no}', max_calls=2 * len(keys) + 2)
        for key in keys:
            item = items[key]
            user = judge_user(item['question'], item['reference'], item['text'])
            attempts, parsed = [], None
            for _ in range(2):
                try:
                    parsed = client.generate(frozen['judge_system'], user, frozen['judge_schema'],
                                             phase=f"judge-{item['case_id']}-{item['arm']}-{item['run']}")
                    attempts.append({'call': client.calls, 'error': None})
                    break
                except Exception as exc:
                    attempts.append({'call': client.calls, 'error': f'{type(exc).__name__}: {exc}'[:500]})
            row = {'key': key, 'arm': item['arm'], 'run': item['run'], 'case_id': item['case_id'],
                   'text_sha256': sha_text(item['text']), 'user_sha256': sha_text(user),
                   'attempts': attempts, 'output': parsed,
                   'usage': [u for u in client.usage if u['call'] in {a['call'] for a in attempts}]}
            with LOCK:
                out['results'][key] = row
                write(out_path, out)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for future in [pool.submit(worker, i, b) for i, b in enumerate(buckets) if b]:
            future.result()
    print(f"judged {len(out['results'])}/{len(items)}")


def score() -> None:
    frozen = read(ART / 'frozen-inputs.json')
    judged = read(ART / 'judged-results.json')['results']
    composed = read(ART / 'compose-results.json')['results']
    cases = [c['case_id'] for c in frozen['cases']]
    filtered = [c['case_id'] for c in frozen['cases'] if c['excluded']]

    def verdicts(arm, run):
        return {c: (judged.get(f'{c}::{arm}::{run}', {}).get('output') or {}).get('correct') for c in cases}

    base = verdicts('baseline', 'run-001')
    by_arm = {}
    for arm in list(REFERENCE) + list(NEW_ARMS):
        runs = RUNS if arm in NEW_ARMS else ['run-001']
        per_run = {r: verdicts(arm, r) for r in runs}
        totals = {r: sum(v is True for v in per_run[r].values()) for r in runs}
        flips = (sorted(c for c in cases if per_run[RUNS[0]][c] != per_run[RUNS[1]][c]) if arm in NEW_ARMS else [])
        pooled = {c: per_run[runs[0]][c] for c in cases}
        by_arm[arm] = {'per_run': totals, 'mean': round(sum(totals.values()) / len(runs), 1),
                       'run_flips': flips,
                       'gap_recovered_run1': sorted(c for c in GAP if pooled[c]),
                       'regressions_vs_baseline_run1': sorted(c for c in cases if base[c] and not pooled[c]),
                       'new_vs_baseline_run1': sorted(c for c in cases if pooled[c] and not base[c]),
                       'unfiltered_correct_run1': sum(1 for c in cases if c not in filtered and pooled[c])}

    def paired(cand, run_c, ref, run_r):
        a, b = verdicts(cand, run_c), verdicts(ref, run_r)
        return {'candidate': f'{cand}/{run_c}', 'baseline': f'{ref}/{run_r}',
                'candidate_only': sorted(c for c in cases if a[c] and not b[c]),
                'baseline_only': sorted(c for c in cases if b[c] and not a[c]),
                'both_correct': sum(1 for c in cases if a[c] and b[c]),
                'both_wrong': sum(1 for c in cases if not a[c] and not b[c])}

    comparisons = [paired(a, 'run-001', 'baseline', 'run-001') for a in NEW_ARMS]
    comparisons += [paired('audit-flash', 'run-001', 'plain-flash', 'run-001'),
                    paired('audit-qwen', 'run-001', 'plain-qwen', 'run-001'),
                    paired('plain-flash', 'run-001', 'v1-plain-flash', 'run-001'),
                    paired('audit-qwen', 'run-001', 'v1-ledger-qwen', 'run-001')]
    ledger_stats = {}
    for arm in NEW_ARMS:
        rows = [composed[f'{c}::{arm}::{r}'] for c in cases for r in RUNS]
        ok = [x for x in rows if x['answer']]
        ledgers = [x['answer']['composition']['ledger'] for x in ok
                   if x['answer']['composition']['mode'] == 'audit']
        findings = [f for x in ok for f in x['answer']['findings']]
        usage = [u for x in rows for u in x['usage']]
        ledger_stats[arm] = {
            'errors': sorted({x['case_id'] for x in rows if x['error']}),
            'answer_chars_p50': sorted(len(x['text']) for x in rows)[len(rows) // 2],
            'ledger_rows_mean': round(sum(len(x) for x in ledgers) / max(1, len(ledgers)), 2) if ledgers else None,
            'ledger_single_row': sum(1 for x in ledgers if len(x) <= 1) if ledgers else None,
            'absent_rows_share': (round(sum(1 for x in ledgers for row in x if row['status'] == '원문에 없음')
                                        / max(1, sum(len(x) for x in ledgers)), 3) if ledgers else None),
            'cases_with_absent_row': sum(1 for x in ledgers if any(r['status'] == '원문에 없음' for r in x)) if ledgers else None,
            'coverage_repaired': sum(1 for f in findings if f['kind'] == 'ledger_coverage_repaired'),
            'coverage_still_missing': sum(1 for f in findings if f['kind'] == 'ledger_item_missing'),
            'findings': {k: sum(1 for f in findings if f['kind'] == k) for k in sorted({f['kind'] for f in findings})},
            'calls': len(usage), 'repairs': sum(1 for u in usage if str(u.get('phase', '')).endswith('-repair')),
            'input_tokens': sum(u.get('input_tokens') or 0 for u in usage),
            'output_tokens': sum(u.get('output_tokens') or 0 for u in usage),
            'cost_usd': round(sum(u.get('cost_usd') or 0 for u in usage), 6),
            'seconds_p50': sorted(u['seconds'] for u in usage)[len(usage) // 2] if usage else None}
    failure = {}
    for row in judged.values():
        out = row['output'] or {}
        if out and not out.get('correct'):
            failure.setdefault(f"{row['arm']}/{row['run']}", {})
            failure[f"{row['arm']}/{row['run']}"][out['failure_type']] = \
                failure[f"{row['arm']}/{row['run']}"].get(out['failure_type'], 0) + 1
    existence = {arm: {c: (judged.get(f'{c}::{arm}::run-001', {}).get('output') or {}).get('correct')
                       for c in ['cm-005', 'cm-025', 'cm-030']} for arm in list(REFERENCE) + list(NEW_ARMS)}
    metrics = {'schema_version': 'adr0466-metrics-v1', 'by_arm': by_arm, 'comparisons': comparisons,
               'compose': ledger_stats, 'failure_types': failure, 'existence_questions': existence,
               'filtered_cases': filtered,
               'judge_errors': sorted(k for k, r in judged.items() if r['output'] is None),
               'judge_usage': {'calls': sum(len(r['usage']) for r in judged.values()),
                               'input_tokens': sum(u['input_tokens'] or 0 for r in judged.values() for u in r['usage']),
                               'output_tokens': sum(u['output_tokens'] or 0 for r in judged.values() for u in r['usage'])}}
    write(ART / 'metrics.json', metrics)
    print(json.dumps({a: by_arm[a]['per_run'] for a in by_arm}, ensure_ascii=False))


if __name__ == '__main__':
    {'freeze': freeze, 'compose': compose, 'judge': judge, 'score': score}[sys.argv[1]]()
