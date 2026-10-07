"""ADR-0465 runner: legal_agent composer replay on ADR-0461 run1 adopted evidence, judged with the ADR-0462 contract.

    .venv/bin/python <this> freeze    # inputs only, no model call
    .venv/bin/python <this> compose   # 4 composer arms (Gemini flash-lite / Qwen3.5-122B FP8 proxy) x (plain / ledger)
    .venv/bin/python <this> judge     # 6 arms x 51, Gemini flash-lite, ADR-0056 system/schema
    .venv/bin/python <this> score
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
sys.dont_write_bytecode = True  # keep the frozen revision free of __pycache__
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ART = ROOT / '04_EXPERIMENTS/ADR/ADR-0465-legal-agent-composer-replay/artifacts'
CAND = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0465/legal-agent'
FROZEN = CAND / 'revisions/rev-001/snapshot/02_BACKEND'
sys.path.insert(0, str(ROOT / '02_BACKEND'))
sys.path.insert(0, str(FROZEN))          # legal_agent comes only from the frozen revision

RUN1 = ROOT / '04_EXPERIMENTS/ADR/ADR-0461-fulltext-candidate-ranking/artifacts/runs-run1'
ADR62 = ROOT / '04_EXPERIMENTS/ADR/ADR-0462-cm-golden-answer-correctness-regrade/artifacts'
GOLDEN = ROOT / '01_DATA/review/cm_core_e2e_v3.json'
PROJECTION = ROOT / '01_DATA/PROJECTIONS/document-origins/term-source-adca5fbe3650f90fb372.json'
COMPOSE_ARMS = {'compose-flash': ('flash-lite-exp', 'plain'), 'compose-flash-ledger': ('flash-lite-exp', 'ledger'),
                'compose-qwen': ('genos-qwen-proxy', 'plain'), 'compose-qwen-ledger': ('genos-qwen-proxy', 'ledger')}
ARMS = ['baseline', 'strip', *COMPOSE_ARMS]
GAP = ['cm-003', 'cm-013', 'cm-014', 'cm-025', 'cm-027', 'cm-028', 'cm-034', 'cm-042', 'cm-045', 'cm-047']
DIAGNOSTIC = re.compile(r'^채택 원문(이|의) ')
ORDER_SEED = 4650
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


def strip_diagnostics(text: str) -> str:
    """Pre-registered: drop paragraphs starting with '채택 원문이/의 '; keep the original if nothing remains."""
    kept = [p for p in text.split('\n\n') if not DIAGNOSTIC.match(p.strip())]
    return '\n\n'.join(kept).strip() or text


def judge_user(question: str, reference: str, answer: str) -> str:
    # Identical to ADR-0056 / ADR-0462 judge_user.
    return (f"[질문]\n{question}\n\n[기준답변]\n{reference}\n\n"
            f"[시스템 답변]\n{answer}\n\n"
            "reason은 3문장 이내, missing_points는 최대 5개의 짧은 항목으로 쓴다.")


def check_client_pin() -> dict:
    frozen = CAND / 'revisions/rev-001/snapshot/02_BACKEND/lawrag/research/experiment_client.py'
    live = ROOT / '02_BACKEND/lawrag/research/experiment_client.py'
    if sha(frozen) != sha(live):
        raise SystemExit('experiment_client drifted from frozen revision; refuse to run')
    return {'frozen': str(frozen.relative_to(ROOT)), 'sha256': sha(frozen)}


def freeze() -> None:
    from legal_agent.replay import load_run_case, origin_prefixes
    golden = {c['id']: c for c in read(GOLDEN)['cases']}
    origins = origin_prefixes(PROJECTION)
    cases = []
    for cid in sorted(golden):
        path = RUN1 / f'{cid}.json'
        run = read(path)
        question, units, excluded = load_run_case(path, origins)
        if question != golden[cid]['question']:
            raise SystemExit(f'question mismatch {cid}')
        baseline = run['output']['answer']['text']
        cases.append({'case_id': cid, 'question': question, 'reference_answer': golden[cid]['reference_answer'],
                      'run1_path': str(path.relative_to(ROOT)), 'run1_sha256': sha(path),
                      'units': [asdict(u) for u in units], 'excluded': excluded,
                      'baseline_answer': baseline, 'strip_answer': strip_diagnostics(baseline)})
    judge = read(ADR62 / 'frozen-inputs.json')
    frozen = {'schema_version': 'adr0465-frozen-inputs-v1', 'golden_sha256': sha(GOLDEN),
              'projection_sha256': sha(PROJECTION), 'candidate_revision': 'rev-001',
              'candidate_json_sha256': sha(CAND / 'candidate.json'), 'client_pin': check_client_pin(),
              'judge_system': judge['judge_system'], 'judge_system_sha256': judge['judge_system_sha256'],
              'judge_schema': judge['judge_schema'], 'compose_arms': COMPOSE_ARMS, 'gap_cases': GAP,
              'order_seed': ORDER_SEED, 'cases': cases}
    write(ART / 'frozen-inputs.json', frozen)
    print(f"frozen {len(cases)} cases; units {sum(len(c['units']) for c in cases)}; "
          f"excluded {sum(len(c['excluded']) for c in cases)} in {sum(bool(c['excluded']) for c in cases)} cases; "
          f"no-evidence {sum(not c['units'] for c in cases)}; strip changed {sum(c['strip_answer'] != c['baseline_answer'] for c in cases)}")


def compose() -> None:
    from legal_agent.contracts import EvidenceUnit
    from legal_agent.models import experiment_model
    from legal_agent.pipeline import answer_from_evidence
    from legal_agent.profiles import PROFILES
    check_client_pin()
    frozen = read(ART / 'frozen-inputs.json')
    out_path = ART / 'compose-results.json'
    out = read(out_path) if out_path.exists() else {'schema_version': 'adr0465-compose-v1', 'results': {}}
    for arm, (profile_name, mode) in COMPOSE_ARMS.items():
        profile = PROFILES[profile_name]
        todo = [c for c in frozen['cases'] if f"{c['case_id']}::{arm}" not in out['results']]
        buckets = [todo[i::WORKERS] for i in range(WORKERS)]

        def worker(no: int, cases: list[dict]) -> None:
            model = experiment_model(profile, ROOT, ART / 'calls' / arm / f'worker-{no}', max_calls=2 * len(cases) + 2)
            for case in cases:
                units = [EvidenceUnit(**u) for u in case['units']]
                before = model.calls
                try:
                    answer = answer_from_evidence(model, case['question'], units, mode=mode,
                                                  phase=f"compose-{case['case_id']}")
                    row = {'text': answer.text, 'answer': answer.to_json(), 'error': None}
                except Exception as exc:  # product failure is recorded and judged as the text shown
                    row = {'text': '(답변 생성 실패)', 'answer': None, 'error': f'{type(exc).__name__}: {exc}'[:500]}
                row.update(arm=arm, case_id=case['case_id'], profile=profile_name, mode=mode, worker=no,
                           calls=model.calls - before, usage=[u for u in model.usage if u['call'] > before])
                with LOCK:
                    out['results'][f"{case['case_id']}::{arm}"] = row
                    write(out_path, out)

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for future in [pool.submit(worker, i, b) for i, b in enumerate(buckets) if b]:
                future.result()
        done = sum(1 for k in out['results'] if k.endswith('::' + arm))
        errors = sum(1 for k, v in out['results'].items() if k.endswith('::' + arm) and v['error'])
        print(f'{arm}: {done}/51 composed, errors {errors}', flush=True)


def judged_texts() -> dict[str, dict]:
    frozen = read(ART / 'frozen-inputs.json')
    composed = read(ART / 'compose-results.json')['results']
    items = {}
    for case in frozen['cases']:
        for arm in ARMS:
            if arm == 'baseline':
                text = case['baseline_answer']
            elif arm == 'strip':
                text = case['strip_answer']
            else:
                text = composed[f"{case['case_id']}::{arm}"]['text']
            items[f"{case['case_id']}::{arm}"] = {'case_id': case['case_id'], 'arm': arm, 'text': text,
                                                  'question': case['question'], 'reference': case['reference_answer']}
    return items


def judge() -> None:
    from lawrag.research.experiment_client import GeminiExperimentClient
    frozen = read(ART / 'frozen-inputs.json')
    items = judged_texts()
    out_path = ART / 'judged-results.json'
    out = read(out_path) if out_path.exists() else {'schema_version': 'adr0465-judged-v1', 'results': {}}
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
            for _ in range(2):  # pre-registered: at most one retry
                try:
                    parsed = client.generate(frozen['judge_system'], user, frozen['judge_schema'],
                                             phase=f"judge-{item['case_id']}-{item['arm']}")
                    attempts.append({'call': client.calls, 'error': None})
                    break
                except Exception as exc:
                    attempts.append({'call': client.calls, 'error': f'{type(exc).__name__}: {exc}'[:500]})
            row = {'key': key, 'arm': item['arm'], 'case_id': item['case_id'], 'text_sha256': sha_text(item['text']),
                   'user_sha256': sha_text(user), 'attempts': attempts, 'output': parsed,
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
    v = {a: {c: (judged[f'{c}::{a}']['output'] or {}).get('correct') for c in cases} for a in ARMS}

    def paired(cand, base, subset=None):
        keys = subset or cases
        return {'candidate': cand, 'baseline': base, 'n': len(keys),
                'candidate_only': sorted(k for k in keys if v[cand][k] and not v[base][k]),
                'baseline_only': sorted(k for k in keys if v[base][k] and not v[cand][k]),
                'both_correct': sum(1 for k in keys if v[cand][k] and v[base][k]),
                'both_wrong': sum(1 for k in keys if not v[cand][k] and not v[base][k])}

    by_arm = {a: {'correct': sum(v[a][c] is True for c in cases), 'ungraded': sum(v[a][c] is None for c in cases),
                  'gap_recovered': sorted(c for c in GAP if v[a][c]),
                  'regressions_vs_baseline': sorted(c for c in cases if v['baseline'][c] and not v[a][c])}
              for a in ARMS}
    comparisons = [paired('strip', 'baseline')] + [paired(a, 'baseline') for a in COMPOSE_ARMS] + [
        paired('compose-flash-ledger', 'compose-flash'), paired('compose-qwen-ledger', 'compose-qwen'),
        paired('compose-qwen', 'compose-flash'), paired('compose-qwen-ledger', 'compose-flash-ledger')]
    compose_stats = {}
    for arm in COMPOSE_ARMS:
        rows = [composed[f'{c}::{arm}'] for c in cases]
        ok = [r for r in rows if r['answer']]
        findings = [f for r in ok for f in r['answer']['findings']]
        ledgers = [r['answer']['composition']['ledger'] for r in ok if r['answer']['composition']['mode'] == 'ledger']
        usage = [u for r in rows for u in r['usage']]
        compose_stats[arm] = {
            'errors': sorted(r['case_id'] for r in rows if r['error']),
            'no_evidence': sorted(r['case_id'] for r in ok if r['answer']['composition']['mode'] == 'no_evidence'),
            'answer_chars_p50': sorted(len(r['text']) for r in rows)[len(rows) // 2],
            'findings': {k: sum(1 for f in findings if f['kind'] == k) for k in sorted({f['kind'] for f in findings})},
            'ledger_rows_mean': round(sum(len(x) for x in ledgers) / max(1, len(ledgers)), 2) if ledgers else None,
            'ledger_single_row_cases': sum(1 for x in ledgers if len(x) <= 1) if ledgers else None,
            'calls': len(usage), 'repairs': sum(1 for u in usage if str(u.get('phase', '')).endswith('-repair')),
            'input_tokens': sum(u.get('input_tokens') or 0 for u in usage),
            'output_tokens': sum(u.get('output_tokens') or 0 for u in usage),
            'thinking_tokens': sum(u.get('thinking_tokens') or 0 for u in usage),
            'cost_usd': round(sum(u.get('cost_usd') or 0 for u in usage), 6) if any('cost_usd' in u for u in usage) else None,
            'upstream_providers': sorted({u.get('upstream_provider') for u in usage if u.get('upstream_provider')}),
            'seconds_p50': sorted(u['seconds'] for u in usage)[len(usage) // 2] if usage else None}
    failure = {a: {} for a in ARMS}
    for row in judged.values():
        out = row['output'] or {}
        if out and not out.get('correct'):
            failure[row['arm']][out['failure_type']] = failure[row['arm']].get(out['failure_type'], 0) + 1
    metrics = {'schema_version': 'adr0465-metrics-v1', 'by_arm': by_arm, 'comparisons': comparisons,
               'compose': compose_stats, 'failure_types': failure,
               'judge_errors': sorted(k for k, r in judged.items() if r['output'] is None),
               'judge_usage': {'calls': sum(len(r['usage']) for r in judged.values()),
                               'input_tokens': sum(u['input_tokens'] or 0 for r in judged.values() for u in r['usage']),
                               'output_tokens': sum(u['output_tokens'] or 0 for r in judged.values() for u in r['usage'])}}
    write(ART / 'metrics.json', metrics)
    print(json.dumps({a: by_arm[a]['correct'] for a in ARMS}, ensure_ascii=False))


if __name__ == '__main__':
    {'freeze': freeze, 'compose': compose, 'judge': judge, 'score': score}[sys.argv[1]]()
