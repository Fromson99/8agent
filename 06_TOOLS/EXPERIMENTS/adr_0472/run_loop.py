"""ADR-0472 runner: legal_agent 탐색 루프 rev-003 E2E on CM 51 (공개 출처 문서만), ADR-0462 채점 계약.

    .venv/bin/python <this> gate       # 조문 지목 rev-2 정밀도 관문(모델 0회) → locator-gate.json
    .venv/bin/python <this> freeze
    .venv/bin/python <this> run        # loop3-flash, loop3-qwen × run-001
    .venv/bin/python <this> judge      # 2 arm + 참고 3 arm(기존 run1, loop2-flash, loop2c-qwen)
    .venv/bin/python <this> score
    .venv/bin/python <this> questions  # 실험/질문-NNN-cm-XXX.md
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import statistics
import sys
sys.dont_write_bytecode = True
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0472-legal-agent-loop-rev3'
ART = ADR / 'artifacts'
CAND = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0472/legal-loop-v3'
FROZEN = CAND / 'revisions/rev-001/snapshot/02_BACKEND'
sys.path.insert(0, str(ROOT / '02_BACKEND'))
sys.path.insert(0, str(FROZEN))

GEN = ROOT / '01_DATA/SEMANTIC/GENERATIONS/navigation-source-20260918-body-v1'
PROJECTION = ROOT / '01_DATA/PROJECTIONS/document-origins/term-source-adca5fbe3650f90fb372.json'
LAW_ROOT = ROOT / '01_DATA/RAW/law'
PREC_ROOT = ROOT / '01_DATA/RAW/prec'
PREC_CASES = ROOT / '09_ARTIFACTS/AUDITS/20260918-precedent-bridge-eval/cases.json'
ADR69 = ROOT / '04_EXPERIMENTS/ADR/ADR-0469-legal-agent-loop-rev2/artifacts'
ARMS = {'loop3-flash': ('flash-lite-exp', 'v2'), 'loop3-qwen': ('genos-qwen-proxy', 'v3')}
PREVIOUS = {'loop3-flash': 'loop2-flash', 'loop3-qwen': 'loop2c-qwen'}
RUNS = ['run-001']
REFERENCE = {'baseline': 'ADR-0461 run1 답변', 'loop2-flash': 'ADR-0469 loop2-flash run-001',
             'loop2c-qwen': 'ADR-0469 loop2c-qwen run-001'}
STRONG = {'quoted', 'declared_alias', 'declared_alias_decree', 'corpus_name', 'already_resolved', 'cue_override',
          'same_document'}
CHANNELS = [('질문 지목', 'question_locator'), ('FTS', 'pre_read'), ('재검색 지목', 'query_locator'),
            ('재검색', 'search'), ('역참조', 'reverse'), ('참조', 'reference'), ('목록 열기', 'listing')]
GATE = {'precision': 0.95, 'deleted': 0, 'abbreviation_wrong': 0}
ORDER_SEED = 4720
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


def channel(via: str) -> str:
    for prefix, name in CHANNELS:
        if via.startswith(prefix):
            return name
    return 'other'


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


def shared(with_locator: bool):
    from legal_agent.harness import PUBLIC_ORIGINS
    from legal_agent.index import LegalIndex
    from legal_agent.locator import Locator, official_abbreviations
    from legal_agent.references import ReferenceResolver
    from legal_agent.replay import origin_prefixes
    index = LegalIndex(GEN / 'store.sqlite')
    resolver = ReferenceResolver(index, GEN / 'navigation/navigation.sqlite')
    edges = resolver.edges([r for r in resolver.resolve_all() if r.via in STRONG])
    reverse: dict[str, set[str]] = {}
    for source, targets in edges.items():
        for target in targets:
            reverse.setdefault(target, set()).add(source)
    origins = origin_prefixes(PROJECTION)
    allowed = {d for d in index.documents if origins.get(d) in PUBLIC_ORIGINS}
    locator = Locator(index, official_abbreviations(LAW_ROOT), allowed) if with_locator else None
    return index, edges, reverse, origins, allowed, locator


# ── 관문 ─────────────────────────────────────────────────────────────────
def gate() -> None:
    import html
    import xml.etree.ElementTree as ET
    from legal_agent.bridges import REFERENCE as CITATION
    from legal_agent.index import LegalIndex
    from legal_agent.locator import DELETED, Locator, official_abbreviations
    index = LegalIndex(GEN / 'store.sqlite')
    official = official_abbreviations(LAW_ROOT)
    locator = Locator(index, official)
    names = {re.sub(r'\s+', '', n): d for d, n in index.documents.items()}
    clean = lambda s: re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html.unescape(s or ''))).strip()
    records = {}
    for item in read(PREC_ROOT / 'manifest.json')['items']:
        if item.get('status') == 'ok':
            r = ET.fromstring((PREC_ROOT / item['file']).read_text())
            records[r.findtext('사건번호')] = clean(r.findtext('참조조문'))

    def cited(text: str) -> set[str]:
        out, law = set(), None
        for m in CITATION.finditer(text):
            if m.group(1):
                law = re.sub(r'\s+', '', m.group(1)).split(',')[-1]
                law = law[1:] if law.startswith('구') and law[1:] in names else law
            doc = names.get(law or '')
            if doc:
                sid = index.by_label(doc, f'제{m.group(2)}조' + (f'의{m.group(3)}' if m.group(3) else ''))
                if sid:
                    out.add(sid)
        return out

    rows, located_total, in_refs, deleted, skipped_total = [], 0, 0, 0, {}
    for case in [c for c in read(PREC_CASES) if c['evaluable']]:
        skipped: list = []
        located = locator.find(case['question_raw'], cap=10, skipped=skipped)
        refs = cited(records.get(case['id'], '')) | {s for g in case['gold'] for s in g['source_ids']}
        for s in skipped:
            skipped_total[s.reason] = skipped_total.get(s.reason, 0) + 1
        for x in located:
            located_total += 1
            in_refs += x.source_id in refs
            deleted += bool(DELETED.match(index.article(x.source_id).heading or ''))
        rows.append({'case_id': case['id'], 'located': [{'label': f"{index.article(x.source_id).document_name} "
                                                                  f"{index.article(x.source_id).label}",
                                                         'cue': x.cue, 'via': x.via, 'in_references': x.source_id in refs}
                                                        for x in located],
                     'skipped': [s.__dict__ for s in skipped]})
    syllable_only = Locator(index, {})
    abbreviations = []
    for name, abbreviation in sorted(official.items()):
        expected = names.get(re.sub(r'\s+', '', name))
        if expected is None:
            continue
        doc, via, cue = syllable_only._document(abbreviation.split(), None)
        abbreviations.append({'name': name, 'abbreviation': abbreviation, 'resolved': index.documents.get(doc),
                              'via': via, 'verdict': 'abstain' if doc is None else ('correct' if doc == expected else 'wrong')})
    precision = in_refs / max(1, located_total)
    wrong = sum(1 for a in abbreviations if a['verdict'] == 'wrong')
    result = {'schema_version': 'adr0472-locator-gate-v1', 'thresholds': GATE,
              'G1_precision': round(precision, 4), 'located': located_total, 'in_references': in_refs,
              'G2_deleted': deleted, 'skipped': skipped_total,
              'G3_abbreviation_wrong': wrong,
              'G3_abbreviation': {'correct': sum(1 for a in abbreviations if a['verdict'] == 'correct'),
                                  'abstain': sum(1 for a in abbreviations if a['verdict'] == 'abstain'), 'wrong': wrong,
                                  'rows': abbreviations},
              'passed': precision >= GATE['precision'] and deleted <= GATE['deleted'] and wrong <= GATE['abbreviation_wrong'],
              'precedent_rows': rows,
              'inputs': {'precedent_cases_sha256': sha(PREC_CASES), 'precedent_manifest_sha256': sha(PREC_ROOT / 'manifest.json'),
                         'candidate_json_sha256': sha(CAND / 'candidate.json')}}
    write(ART / 'locator-gate.json', result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('precedent_rows',)} | {
        'G3_abbreviation': {k: v for k, v in result['G3_abbreviation'].items() if k != 'rows'}}, ensure_ascii=False, indent=1))
    print('not in references:', [f"{r['case_id']} {x['cue']}→{x['label']}" for r in rows for x in r['located']
                                 if not x['in_references']])
    print('abbreviation rows:', [(a['abbreviation'], a['verdict'], a['resolved']) for a in abbreviations])


# ── 동결 ─────────────────────────────────────────────────────────────────
def freeze() -> None:
    previous = read(ADR69 / 'frozen-inputs.json')
    loops2 = read(ADR69 / 'loop-results.json')['results']
    judge = read(ROOT / '04_EXPERIMENTS/ADR/ADR-0462-cm-golden-answer-correctness-regrade/artifacts/frozen-inputs.json')
    gate_result = read(ART / 'locator-gate.json')
    cases = []
    for case in previous['cases']:
        cid = case['case_id']
        cases.append({'case_id': cid, 'question': case['question'], 'reference_answer': case['reference_answer'],
                      'decisive_source_ids': case['decisive_source_ids'],
                      'reference_texts': {'baseline': case['reference_texts']['baseline'],
                                          'loop2-flash': loops2[f'{cid}::loop2-flash::run-001']['text'],
                                          'loop2c-qwen': loops2[f'{cid}::loop2c-qwen::run-001']['text']}})
    frozen = {'schema_version': 'adr0472-frozen-inputs-v1', 'adr0469_frozen_sha256': sha(ADR69 / 'frozen-inputs.json'),
              'adr0469_loop_results_sha256': sha(ADR69 / 'loop-results.json'),
              'store_sha256': sha(GEN / 'store.sqlite'), 'navigation_sha256': sha(GEN / 'navigation/navigation.sqlite'),
              'fulltext_sha256': sha(GEN / 'fulltext/fulltext.sqlite'), 'projection_sha256': sha(PROJECTION),
              'candidate_json_sha256': sha(CAND / 'candidate.json'), 'client_pin': check_client_pin(),
              'locator_enabled': bool(gate_result['passed']), 'locator_gate_sha256': sha(ART / 'locator-gate.json'),
              'judge_system': judge['judge_system'], 'judge_system_sha256': judge['judge_system_sha256'],
              'judge_schema': judge['judge_schema'], 'arms': ARMS, 'runs': RUNS, 'reference_arms': REFERENCE,
              'order_seed': ORDER_SEED, 'cases': cases}
    write(ART / 'frozen-inputs.json', frozen)
    print(f"frozen {len(cases)} cases, decisive {sum(len(c['decisive_source_ids']) for c in cases)}, "
          f"locator {'on' if frozen['locator_enabled'] else 'off'}")


# ── 실행 ─────────────────────────────────────────────────────────────────
def run() -> None:
    from legal_agent.loop import Loop, LoopConfig
    from legal_agent.models import experiment_model
    from legal_agent.profiles import PROFILES
    from legal_agent.search import Search
    check_client_pin()
    frozen = read(ART / 'frozen-inputs.json')
    index, edges, reverse, origins, allowed, locator = shared(frozen['locator_enabled'])
    out_path = ART / 'loop-results.json'
    out = read(out_path) if out_path.exists() else {'schema_version': 'adr0472-loop-v1', 'results': {}}
    for run_id in RUNS:
        for arm, (profile_name, rules) in ARMS.items():
            profile = PROFILES[profile_name]
            # 기록이 없거나 제공자 오류(503 등)로 끝난 문항만 다시 돈다. 실패한 시도의 호출 원문은 calls/에 남는다.
            todo = [c for c in frozen['cases'] if f"{c['case_id']}::{arm}::{run_id}" not in out['results']
                    or out['results'][f"{c['case_id']}::{arm}::{run_id}"]['error']]
            buckets = [todo[i::WORKERS] for i in range(WORKERS)]

            def worker(no: int, cases: list[dict]) -> None:
                search = Search(GEN, allowed, index)
                model = experiment_model(profile, ROOT, ART / 'calls' / run_id / arm / f'worker-{no}',
                                         max_calls=9 * len(cases) + 4)
                for case in cases:
                    before = model.calls
                    try:
                        result = Loop(index, search, edges, origins, allowed, model, LoopConfig(composer_rules=rules),
                                      reverse_edges=reverse, locator=locator).run(
                            case['question'], phase=f"loop-{case['case_id']}")
                        answer = result.pop('answer')
                        row = {'text': answer.text, 'answer': answer.to_json(), 'error': None, **result}
                    except Exception as exc:
                        row = {'text': '(답변 생성 실패)', 'answer': None, 'error': f'{type(exc).__name__}: {exc}'[:500],
                               'shown_source_ids': [], 'adopted_source_ids': [], 'evidence_source_ids': [],
                               'listing_source_ids': []}
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


# ── 채점 ─────────────────────────────────────────────────────────────────
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
    out = read(out_path) if out_path.exists() else {'schema_version': 'adr0472-judged-v1', 'results': {}}
    order = sorted(items)
    random.Random(ORDER_SEED).shuffle(order)
    todo = [k for k in order if k not in out['results'] or out['results'][k]['output'] is None]
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
    print(f"judged {len(out['results'])}/{len(items)}, errors {sum(1 for r in out['results'].values() if r['output'] is None)}")


# ── 집계 ─────────────────────────────────────────────────────────────────
def score() -> None:
    frozen = read(ART / 'frozen-inputs.json')
    judged = read(ART / 'judged-results.json')['results']
    loops = read(ART / 'loop-results.json')['results']
    loops2 = read(ADR69 / 'loop-results.json')['results']
    cases = [c['case_id'] for c in frozen['cases']]
    decisive = {c['case_id']: set(c['decisive_source_ids']) for c in frozen['cases']}
    total_dec = sum(len(v) for v in decisive.values())

    def verdict(arm, run_id='run-001'):
        return {c: (judged.get(f'{c}::{arm}::{run_id}', {}).get('output') or {}).get('correct') for c in cases}

    base = verdict('baseline')
    by_arm = {a: {'run-001': sum(v is True for v in verdict(a).values())} for a in REFERENCE}
    detail = {}
    for arm in ARMS:
        v1, prev = verdict(arm), verdict(PREVIOUS[arm])
        rows = [loops[f'{c}::{arm}::run-001'] for c in cases]
        prev_rows = [loops2[f'{c}::{PREVIOUS[arm]}::run-001'] for c in cases]

        def recall(rs, key):
            return sum(len(decisive[x['case_id']] & set(x.get(key) or [])) for x in rs)

        by_channel = {}
        for x in rows:
            for card in x.get('cards') or []:
                if card['source_id'] in decisive[x['case_id']]:
                    ch = by_channel.setdefault(channel(card['via']), {'shown': 0, 'adopted': 0})
                    ch['shown'] += 1
                    ch['adopted'] += bool(card['adopted'])
        listed = sum(len(decisive[x['case_id']] & (set(x.get('listing_source_ids') or []) - set(x.get('shown_source_ids') or [])))
                     for x in rows)
        usage = [u for x in rows for u in x['usage']]
        calls = sorted(x['calls'] for x in rows)
        cards = sorted(len(x.get('cards') or []) for x in rows)
        opens = sum(len(t['decision'].get('open') or []) for x in rows for t in (x.get('trace') or []) if t.get('step') == 'round')
        detail[arm] = {
            'score': sum(v is True for v in v1.values()),
            'new_vs_baseline': sorted(c for c in cases if v1[c] and not base[c]),
            'regressions_vs_baseline': sorted(c for c in cases if base[c] and not v1[c]),
            'previous_arm': PREVIOUS[arm], 'previous_score': sum(v is True for v in prev.values()),
            'new_vs_previous': sorted(c for c in cases if v1[c] and not prev[c]),
            'lost_vs_previous': sorted(c for c in cases if prev[c] and not v1[c]),
            'decisive_shown': recall(rows, 'shown_source_ids'), 'decisive_adopted': recall(rows, 'adopted_source_ids'),
            'decisive_evidence': recall(rows, 'evidence_source_ids'), 'decisive_total': total_dec,
            'decisive_listed_not_opened': listed,
            'previous_decisive_shown': recall(prev_rows, 'shown_source_ids'),
            'previous_decisive_evidence': recall(prev_rows, 'evidence_source_ids'),
            'by_channel': by_channel, 'opens': opens,
            'short_answers': sorted(x['case_id'] for x in rows if len(x['text']) <= 30),
            'deferrals': sum(x.get('deferrals') or 0 for x in rows),
            'fallback_cases': sum(1 for x in rows if x.get('fallback')),
            'errors': sorted(x['case_id'] for x in rows if x['error']),
            'calls_median': statistics.median(calls), 'calls_max': calls[-1],
            'cards_median': statistics.median(cards), 'cards_max': cards[-1],
            'repairs': sum(1 for u in usage if str(u.get('phase', '')).endswith('-repair')),
            'input_tokens': sum(u.get('input_tokens') or 0 for u in usage),
            'output_tokens': sum(u.get('output_tokens') or 0 for u in usage),
            'cost_usd': round(sum(u.get('cost_usd') or 0 for u in usage), 4),
            'seconds_p50': sorted(u['seconds'] for u in usage)[len(usage) // 2] if usage else None,
            'unknown_handles': sum(len(t.get('unknown_handles') or []) for x in rows
                                   for t in (x.get('trace') or []) if t.get('step') == 'round')}
        by_arm[arm] = {'run-001': detail[arm]['score']}
    failure = {}
    for row in judged.values():
        o = row['output'] or {}
        if o and not o.get('correct'):
            failure.setdefault(row['arm'], {})
            failure[row['arm']][o['failure_type']] = failure[row['arm']].get(o['failure_type'], 0) + 1
    metrics = {'schema_version': 'adr0472-metrics-v1', 'by_arm': by_arm, 'detail': detail, 'failure_types': failure,
               'locator_enabled': frozen['locator_enabled'],
               'judge_errors': sorted(k for k, r in judged.items() if r['output'] is None),
               'judge_usage': {'calls': sum(len(r['usage']) for r in judged.values())}}
    write(ART / 'metrics.json', metrics)
    print(json.dumps({a: by_arm[a] for a in by_arm}, ensure_ascii=False))
    for arm in ARMS:
        print(arm, json.dumps({k: v for k, v in detail[arm].items() if k not in ('new_vs_baseline', 'regressions_vs_baseline')},
                              ensure_ascii=False))


# ── 질문 파일 ──────────────────────────────────────────────────────────────
def questions() -> None:
    frozen = read(ART / 'frozen-inputs.json')
    loops = read(ART / 'loop-results.json')['results']
    judged = read(ART / 'judged-results.json')['results']
    ledger = read(ART / 'retrieval-stage-ledger.json')
    manifest_path = ADR / '실험/manifest.json'
    manifest = read(manifest_path)
    calls_index: dict[str, list[str]] = {}
    for d in sorted((ART / 'calls').glob('run-*/*/worker-*/call-*')):
        m = re.match(r'call-\d+-loop-(cm-\d+)-', d.name)
        if m:
            calls_index.setdefault(f"{m.group(1)}::{d.parent.parent.name}", []).append(str(d.relative_to(ADR)))
    judge_index: dict[str, list[str]] = {}
    for d in sorted((ART / 'judge-calls').glob('worker-*/call-*')):
        m = re.match(r'call-\d+-judge-(cm-\d+)-(.+)-(run-\d+)$', d.name)
        if m:
            judge_index.setdefault(f'{m.group(1)}::{m.group(2)}::{m.group(3)}', []).append(str(d.relative_to(ADR)))
    stage_rows = {}
    for run in ledger['runs']:
        for arm in run['arms']:
            for case in arm['cases']:
                stage_rows[(case['case_id'], arm['arm_id'])] = case['stages']
    arms_all = list(REFERENCE) + list(ARMS)
    entries = []
    for number, case in enumerate(frozen['cases'], start=1):
        cid = case['case_id']
        lines = [f'# 질문 {number:03d} — {cid}', '', '## 1. 실행 메타', '',
                 f"- ADR: `{manifest['adr_id']}`", f"- experiment: `{manifest['experiment_id']}`", f'- case ID: `{cid}`',
                 '- run ID: `run-001`', '- 원본 상태: `exact` (루프·조립·채점 호출 원문 보존)',
                 '- 제품 호출 모델: `gemini-3.1-flash-lite`(loop3-flash), `qwen/qwen3.5-122b-a10b` OpenRouter FP8(loop3-qwen)',
                 '- 오프라인 평가 모델: `gemini-3.1-flash-lite`',
                 f"- 실행 arm: {', '.join(f'`{a}`' for a in arms_all)}",
                 f"- 조문 지목 해소: {'켬' if frozen['locator_enabled'] else '끔(관문 미통과)'}", '',
                 '## 2. 사용자 질문 원문', '', '```text', case['question'], '```', '',
                 '## 3. 기준답변 — 채점 전용, 제품 입력 비공개', '', '```text', case['reference_answer'], '```', '',
                 '## 4. 제품 입력을 구성한 원값', '', '### 회수 전 전체·후보·제시 규모', '', '```json',
                 json.dumps({'corpus_total': 17637, 'decisive': len(case['decisive_source_ids'])}), '```', '',
                 '### 회수 좌표·조문·정의·Wiki·관계 — 전체', '']
        for arm in ARMS:
            row = loops[f'{cid}::{arm}::run-001']
            lines += [f'{arm} 카드:', '', '```json', json.dumps(
                [{'handle': c['handle'], 'via': c['via'], 'label': c['label'], 'adopted': c['adopted'],
                  'dropped': c['dropped'], 'decisive': c['source_id'] in set(case['decisive_source_ids'])}
                 for c in row.get('cards') or []], ensure_ascii=False), '```', '']
        lines += ['### 회수·탈락 단계 원장 — run·arm별', '',
                  '| run | arm | stage | kind | before | +added | -discarded | after | gold before | gold + | gold - | gold after/total | recall | 대표 탈락 이유 |',
                  '|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|']
        for arm in ARMS:
            for s in stage_rows.get((cid, arm), []):
                reasons = ', '.join(f'{k}:{v}' for k, v in s['discard_reason_counts'].items()) or '-'
                lines.append(f"| run-001 | {arm} | {s['stage_id']} | {s['kind']} | {s['before_count']} | {s['added_count']} | "
                             f"{s['discarded_count']} | {s['after_count']} | {s['gold_before']} | {s['gold_added']} | "
                             f"{s['gold_discarded']} | {s['gold_after']}/{s['gold_total']} | {s['golden_recall']} | {reasons} |")
        lines += ['', '```json', json.dumps({'stage_ledger_artifact': 'artifacts/retrieval-stage-ledger.json',
                                             'gold_visible_to_product': False}), '```', '',
                  '## 5. 제품 모델 호출 — run·arm별 실제 원문', '']
        for arm in arms_all:
            lines += [f'### run-001 / {arm} / system', '']
            if arm in REFERENCE:
                lines += ['```text', f'제품 호출 없음(저장된 답 재채점: {REFERENCE[arm]})', '```', '']
            else:
                lines += ['루프 SYSTEM·STEP_SCHEMA와 조립기 원문은 호출 디렉터리 request.json: '
                          + ', '.join(calls_index.get(f'{cid}::{arm}', [])), '']
            lines += [f'### run-001 / {arm} / user', '', '```text', case['question'], '```', '',
                      f'### run-001 / {arm} / schema·tool', '', '```json',
                      'null' if arm in REFERENCE else json.dumps('legal_agent.loop rev-003 STEP_SCHEMA + composer plain (request.json 참조)'),
                      '```', '', f'### run-001 / {arm} / provider 원응답·structured output·usage·지연', '']
            if arm in REFERENCE:
                lines += ['```text', case['reference_texts'][arm], '```', '']
            else:
                row = loops[f'{cid}::{arm}::run-001']
                lines += ['사용자 표시 답(채점 대상):', '', '```text', row['text'], '```', '', '```json', json.dumps(
                    {k: row.get(k) for k in ('error', 'calls', 'rounds', 'deferrals', 'fallback', 'trace', 'usage')},
                    ensure_ascii=False, indent=1), '```', '']
        lines += ['## 6. 중간 LLM 호출 — router/compiler/verifier/repair', '', '```json', json.dumps(
            [{'arm': arm, 'phases': [u['phase'] for u in loops[f'{cid}::{arm}::run-001']['usage']]} for arm in ARMS],
            ensure_ascii=False), '```', '', '## 7. 채점 호출과 반복 판정', '', '### judge system/user — 기준답변 포함', '',
                  '```json', json.dumps({'judge_system_sha256': frozen['judge_system_sha256'], 'requests': [
                      {'key': f'{cid}::{arm}::run-001', 'user_sha256': judged[f'{cid}::{arm}::run-001']['user_sha256'],
                       'call_dirs': judge_index.get(f'{cid}::{arm}::run-001', [])} for arm in arms_all]},
                                        ensure_ascii=False, indent=1), '```', '', '### judge 원응답과 최종 다수결', '',
                  '```json', json.dumps({f'{cid}::{arm}::run-001': {'output': judged[f'{cid}::{arm}::run-001']['output'],
                                                                     'attempts': judged[f'{cid}::{arm}::run-001']['attempts']}
                                         for arm in arms_all}, ensure_ascii=False, indent=1), '```', '',
                  '## 8. 사례 최종 판정', '', '| run | arm | 정답 | 핵심 근거 | 실패 유형 |', '|---|---|---:|---|---|']
        verdicts = {}
        for arm in arms_all:
            o = judged[f'{cid}::{arm}::run-001']['output'] or {}
            verdicts[arm] = o.get('correct')
            lines.append(f"| run-001 | {arm} | {'O' if o.get('correct') else 'X'} | {(o.get('reason') or '')[:120]} | "
                         f"{o.get('failure_type', '-')} |")
        notes = []
        for arm in ARMS:
            prev = PREVIOUS[arm]
            if verdicts[arm] and not verdicts[prev]:
                notes.append(f'{arm} 신규(대 {prev})')
            elif verdicts[prev] and not verdicts[arm]:
                notes.append(f'{arm} 회귀(대 {prev})')
        lines += ['', f"- 사전 지정 비교쌍의 신규 정답·회귀: {', '.join(notes) or '변화 없음'}",
                  f"- 공통 실패 유형: loop3-flash 기준 `{(judged[f'{cid}::loop3-flash::run-001']['output'] or {}).get('failure_type', '-')}`",
                  '- 사람이 확인한 직접 원인: 미확인(모델 채점만)', '']
        name = f'질문-{number:03d}-{cid}.md'
        path = ADR / '실험' / name
        path.write_text('\n'.join(lines) + '\n')
        entries.append({'number': number, 'case_id': cid, 'file': name, 'sha256': sha(path)})
    manifest['questions'] = entries
    write(manifest_path, manifest)
    print(f'wrote {len(entries)} question files')


if __name__ == '__main__':
    {'gate': gate, 'freeze': freeze, 'run': run, 'judge': judge, 'score': score, 'questions': questions}[sys.argv[1]]()
