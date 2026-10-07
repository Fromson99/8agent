"""ADR-0469 runner: legal_agent 탐색 루프 rev-002 E2E on CM 51 (공개 출처 문서만), ADR-0462 채점 계약.

    .venv/bin/python <this> freeze
    .venv/bin/python <this> run       # loop-flash, loop-qwen × run-001, run-002
    .venv/bin/python <this> judge     # 4 arm-run + 참고 2 arm
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
ART = ROOT / '04_EXPERIMENTS/ADR/ADR-0469-legal-agent-loop-rev2/artifacts'
CAND = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0469/legal-loop-v2'
FROZEN = CAND / 'revisions/rev-001/snapshot/02_BACKEND'
sys.path.insert(0, str(ROOT / '02_BACKEND'))
sys.path.insert(0, str(FROZEN))

GEN = ROOT / '01_DATA/SEMANTIC/GENERATIONS/navigation-source-20260918-body-v1'
PROJECTION = ROOT / '01_DATA/PROJECTIONS/document-origins/term-source-adca5fbe3650f90fb372.json'
GOLDEN = ROOT / '01_DATA/review/cm_core_e2e_v3.json'
RUN1 = ROOT / '04_EXPERIMENTS/ADR/ADR-0461-fulltext-candidate-ranking/artifacts/runs-run1'
ADR68 = ROOT / '04_EXPERIMENTS/ADR/ADR-0468-legal-agent-loop-server-reading/artifacts'
ARMS = {'loop2-flash': ('flash-lite-exp', 'v2'), 'loop2-qwen': ('genos-qwen-proxy', 'v2'),
        'loop2c-flash': ('flash-lite-exp', 'v3'), 'loop2c-qwen': ('genos-qwen-proxy', 'v3')}
RUNS = ['run-001']
REFERENCE = {'baseline': 'ADR-0461 run1 답변', 'loop1-flash': 'ADR-0468 loop-flash run-001', 'loop1-qwen': 'ADR-0468 loop-qwen run-001'}
RETRIEVAL_GAP = ['cm-007', 'cm-012', 'cm-016', 'cm-020', 'cm-029', 'cm-031', 'cm-035', 'cm-040', 'cm-041', 'cm-050']
STRONG = {'quoted', 'declared_alias', 'corpus_name', 'already_resolved', 'same_document'}
ORDER_SEED = 4690
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
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + '\n')
    tmp.replace(path)


def judge_user(question: str, reference: str, answer: str) -> str:
    return (f"[질문]\n{question}\n\n[기준답변]\n{reference}\n\n"
            f"[시스템 답변]\n{answer}\n\n"
            "reason은 3문장 이내, missing_points는 최대 5개의 짧은 항목으로 쓴다.")


def check_client_pin() -> dict:
    frozen = FROZEN / 'lawrag/research/experiment_client.py'
    live = ROOT / '02_BACKEND/lawrag/research/experiment_client.py'
    if sha(frozen) != sha(live):
        raise SystemExit('experiment_client drifted from the frozen revision; refuse to run')
    return {'frozen': str(frozen.relative_to(ROOT)), 'sha256': sha(frozen)}


def freeze() -> None:
    golden = {c['id']: c for c in read(GOLDEN)['cases']}
    judge = read(ROOT / '04_EXPERIMENTS/ADR/ADR-0462-cm-golden-answer-correctness-regrade/artifacts/frozen-inputs.json')
    loops1 = read(ADR68 / 'loop-results.json')['results']
    cases = []
    for cid in sorted(golden):
        run = read(RUN1 / f'{cid}.json')
        decisive = sorted({s for e in run['expected'] if e['role'] == 'decisive' for s in e['source_ids']})
        cases.append({'case_id': cid, 'question': golden[cid]['question'],
                      'reference_answer': golden[cid]['reference_answer'], 'decisive_source_ids': decisive,
                      'reference_texts': {'baseline': run['output']['answer']['text'],
                                          'loop1-flash': loops1[f'{cid}::loop-flash::run-001']['text'],
                                          'loop1-qwen': loops1[f'{cid}::loop-qwen::run-001']['text']}})
    frozen = {'schema_version': 'adr0469-frozen-inputs-v1', 'golden_sha256': sha(GOLDEN),
              'store_sha256': sha(GEN / 'store.sqlite'), 'navigation_sha256': sha(GEN / 'navigation/navigation.sqlite'),
              'fulltext_sha256': sha(GEN / 'fulltext/fulltext.sqlite'), 'projection_sha256': sha(PROJECTION),
              'candidate_json_sha256': sha(CAND / 'candidate.json'), 'client_pin': check_client_pin(),
              'judge_system': judge['judge_system'], 'judge_system_sha256': judge['judge_system_sha256'],
              'judge_schema': judge['judge_schema'], 'arms': ARMS, 'runs': RUNS, 'reference_arms': REFERENCE,
              'retrieval_gap_cases': RETRIEVAL_GAP, 'order_seed': ORDER_SEED, 'cases': cases}
    write(ART / 'frozen-inputs.json', frozen)
    print(f'frozen {len(cases)} cases, decisive {sum(len(c["decisive_source_ids"]) for c in cases)}')


def shared():
    from legal_agent.harness import PUBLIC_ORIGINS
    from legal_agent.index import LegalIndex
    from legal_agent.references import ReferenceResolver
    from legal_agent.replay import origin_prefixes
    index = LegalIndex(GEN / 'store.sqlite')
    resolver = ReferenceResolver(index, GEN / 'navigation/navigation.sqlite')
    edges = resolver.edges([r for r in resolver.resolve_all() if r.via in STRONG])
    origins = origin_prefixes(PROJECTION)
    allowed = {d for d in index.documents if origins.get(d) in PUBLIC_ORIGINS}
    return index, edges, origins, allowed


def run() -> None:
    from legal_agent.loop import Loop, LoopConfig
    from legal_agent.models import experiment_model
    from legal_agent.profiles import PROFILES
    from legal_agent.search import Search
    check_client_pin()
    frozen = read(ART / 'frozen-inputs.json')
    index, edges, origins, allowed = shared()
    out_path = ART / 'loop-results.json'
    out = read(out_path) if out_path.exists() else {'schema_version': 'adr0469-loop-v1', 'results': {}}
    for run_id in RUNS:
        for arm, (profile_name, rules) in ARMS.items():
            profile = PROFILES[profile_name]
            todo = [c for c in frozen['cases'] if f"{c['case_id']}::{arm}::{run_id}" not in out['results']]
            buckets = [todo[i::WORKERS] for i in range(WORKERS)]

            def worker(no: int, cases: list[dict]) -> None:
                search = Search(GEN, allowed, index)
                model = experiment_model(profile, ROOT, ART / 'calls' / run_id / arm / f'worker-{no}',
                                         max_calls=8 * len(cases) + 4)
                for case in cases:
                    before = model.calls
                    try:
                        result = Loop(index, search, edges, origins, allowed, model,
                                      LoopConfig(composer_rules=rules)).run(
                            case['question'], phase=f"loop-{case['case_id']}")
                        answer = result.pop('answer')
                        row = {'text': answer.text, 'answer': answer.to_json(), 'error': None, **result}
                    except Exception as exc:
                        row = {'text': '(답변 생성 실패)', 'answer': None, 'error': f'{type(exc).__name__}: {exc}'[:500],
                               'shown_source_ids': [], 'adopted_source_ids': [], 'evidence_source_ids': []}
                    row.update(arm=arm, run=run_id, case_id=case['case_id'], calls=model.calls - before,
                               usage=[u for u in model.usage if u['call'] > before])
                    with LOCK:
                        out['results'][f"{case['case_id']}::{arm}::{run_id}"] = row
                        write(out_path, out)

            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                for future in [pool.submit(worker, i, b) for i, b in enumerate(buckets) if b]:
                    future.result()
            done = [v for k, v in out['results'].items() if k.endswith(f'::{arm}::{run_id}')]
            print(f"{run_id} {arm}: {len(done)}/51, errors {sum(1 for v in done if v['error'])}", flush=True)


def judge() -> None:
    from lawrag.research.experiment_client import GeminiExperimentClient
    frozen = read(ART / 'frozen-inputs.json')
    loops = read(ART / 'loop-results.json')['results']
    items = {}
    for case in frozen['cases']:
        cid = case['case_id']
        for arm, text in case['reference_texts'].items():
            items[f'{cid}::{arm}::run-001'] = (case, arm, 'run-001', text)
        for run_id in RUNS:
            for arm in ARMS:
                items[f'{cid}::{arm}::{run_id}'] = (case, arm, run_id, loops[f'{cid}::{arm}::{run_id}']['text'])
    out_path = ART / 'judged-results.json'
    out = read(out_path) if out_path.exists() else {'schema_version': 'adr0469-judged-v1', 'results': {}}
    order = sorted(items)
    random.Random(ORDER_SEED).shuffle(order)
    todo = [k for k in order if k not in out['results']]
    buckets = [todo[i::WORKERS] for i in range(WORKERS)]

    def worker(no: int, keys: list[str]) -> None:
        client = GeminiExperimentClient(ROOT, ART / 'judge-calls' / f'worker-{no}', max_calls=2 * len(keys) + 2)
        for key in keys:
            case, arm, run_id, text = items[key]
            user = judge_user(case['question'], case['reference_answer'], text)
            attempts, parsed = [], None
            for _ in range(2):
                try:
                    parsed = client.generate(frozen['judge_system'], user, frozen['judge_schema'],
                                             phase=f"judge-{case['case_id']}-{arm}-{run_id}")
                    attempts.append({'call': client.calls, 'error': None})
                    break
                except Exception as exc:
                    attempts.append({'call': client.calls, 'error': f'{type(exc).__name__}: {exc}'[:500]})
            row = {'key': key, 'arm': arm, 'run': run_id, 'case_id': case['case_id'], 'text_sha256': sha_text(text),
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
    loops = read(ART / 'loop-results.json')['results']
    cases = [c['case_id'] for c in frozen['cases']]
    decisive = {c['case_id']: set(c['decisive_source_ids']) for c in frozen['cases']}

    def verdict(arm, run_id):
        return {c: (judged.get(f'{c}::{arm}::{run_id}', {}).get('output') or {}).get('correct') for c in cases}

    base = verdict('baseline', 'run-001')
    ref1 = {'flash': verdict('loop1-flash', 'run-001'), 'qwen': verdict('loop1-qwen', 'run-001')}
    by_arm = {a: {'run-001': sum(v is True for v in verdict(a, 'run-001').values())} for a in REFERENCE}
    detail = {}
    for arm in ARMS:
        per = {r: verdict(arm, r) for r in RUNS}
        rows = {r: [loops[f'{c}::{arm}::{r}'] for c in cases] for r in RUNS}
        total_dec = sum(len(decisive[c]) for c in cases)
        shown = {r: sum(len(decisive[x['case_id']] & set(x.get('shown_source_ids') or [])) for x in rows[r]) for r in RUNS}
        adopted = {r: sum(len(decisive[x['case_id']] & set(x.get('adopted_source_ids') or [])) for x in rows[r]) for r in RUNS}
        usage = [u for r in RUNS for x in rows[r] for u in x['usage']]
        calls = sorted(x['calls'] for r in RUNS for x in rows[r])
        v1 = per['run-001']
        detail[arm] = {
            'per_run': {r: sum(v is True for v in per[r].values()) for r in RUNS},
            'mean': round(sum(sum(v is True for v in per[r].values()) for r in RUNS) / len(RUNS), 1),
            'new_vs_baseline': sorted(c for c in cases if v1[c] and not base[c]),
            'regressions_vs_baseline': sorted(c for c in cases if base[c] and not v1[c]),
            'new_vs_loop1': sorted(c for c in cases if v1[c] and not ref1['qwen' if 'qwen' in arm else 'flash'][c]),
            'lost_vs_loop1': sorted(c for c in cases if ref1['qwen' if 'qwen' in arm else 'flash'][c] and not v1[c]),
            'short_answers': sorted(x['case_id'] for x in rows['run-001'] if len(x['text']) <= 30),
            'deferrals': sum(x.get('deferrals') or 0 for x in rows['run-001']),
            'retrieval_gap_recovered': sorted(c for c in RETRIEVAL_GAP if v1[c]),
            'decisive_shown_recall': {r: round(shown[r] / total_dec, 3) for r in RUNS},
            'decisive_adopted_recall': {r: round(adopted[r] / total_dec, 3) for r in RUNS},
            'fallback_cases': {r: sum(1 for x in rows[r] if x.get('fallback')) for r in RUNS},
            'errors': {r: sorted(x['case_id'] for x in rows[r] if x['error']) for r in RUNS},
            'calls_median': calls[len(calls) // 2], 'calls_max': calls[-1],
            'repairs': sum(1 for u in usage if str(u.get('phase', '')).endswith('-repair')),
            'input_tokens': sum(u.get('input_tokens') or 0 for u in usage),
            'output_tokens': sum(u.get('output_tokens') or 0 for u in usage),
            'cost_usd': round(sum(u.get('cost_usd') or 0 for u in usage), 4),
            'seconds_p50': sorted(u['seconds'] for u in usage)[len(usage) // 2] if usage else None,
            'unknown_handles': sum(len(t.get('unknown_handles') or []) for r in RUNS for x in rows[r]
                                   for t in (x.get('trace') or []) if t.get('step') == 'round')}
        by_arm[arm] = detail[arm]['per_run']
    failure = {}
    for row in judged.values():
        o = row['output'] or {}
        if o and not o.get('correct'):
            key = f"{row['arm']}/{row['run']}"
            failure.setdefault(key, {})
            failure[key][o['failure_type']] = failure[key].get(o['failure_type'], 0) + 1
    metrics = {'schema_version': 'adr0469-metrics-v1', 'by_arm': by_arm, 'detail': detail, 'failure_types': failure,
               'judge_errors': sorted(k for k, r in judged.items() if r['output'] is None),
               'judge_usage': {'calls': sum(len(r['usage']) for r in judged.values())},
               'loop1_reference': {'loop-flash': {'score': 36, 'decisive_adopted_recall': 0.547},
                                   'loop-qwen': {'score': 30, 'decisive_adopted_recall': 0.547}}}
    write(ART / 'metrics.json', metrics)
    print(json.dumps({a: by_arm[a] for a in by_arm}, ensure_ascii=False))


if __name__ == '__main__':
    {'freeze': freeze, 'run': run, 'judge': judge, 'score': score}[sys.argv[1]]()
