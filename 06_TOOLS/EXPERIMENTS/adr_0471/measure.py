"""ADR-0471 measurement: 조문 지목 해소·참조 해소 수리·준용 역참조. 모델 호출 0회.

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python <this> run       # 측정 → metrics.json, cm-cases.json, precedent-cases.json,
                                                               #        resolution-diff.json, repair-samples.json(판정 전)
    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python <this> score     # repair-samples-judged.json 판정 집계 → metrics.json

수리 전 해소기는 ADR-0470 후보 rev-001의 references를 legal_agent_prev 패키지로 불러와 같은 색인 위에서 돌린다.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import random
import statistics
import sys
sys.dont_write_bytecode = True
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ART = ROOT / '04_EXPERIMENTS/ADR/ADR-0471-legal-agent-locator-and-reference-repair/artifacts'
CAND = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0471/legal-entry-repair'
FROZEN = CAND / 'revisions/rev-001/snapshot/02_BACKEND'
PREV = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0470/legal-bridges/revisions/rev-001/snapshot/02_BACKEND/legal_agent'
sys.path.insert(0, str(ROOT / '02_BACKEND'))
sys.path.insert(0, str(FROZEN))

GEN = ROOT / '01_DATA/SEMANTIC/GENERATIONS/navigation-source-20260918-body-v1'
PROJECTION = ROOT / '01_DATA/PROJECTIONS/document-origins/term-source-adca5fbe3650f90fb372.json'
LAW_ROOT = ROOT / '01_DATA/RAW/law'
ADR69 = ROOT / '04_EXPERIMENTS/ADR/ADR-0469-legal-agent-loop-rev2/artifacts'
PREC_CASES = ROOT / '09_ARTIFACTS/AUDITS/20260918-precedent-bridge-eval/cases.json'
TRAJECTORIES = {'gemini': 'loop2-flash', 'qwen': 'loop2c-qwen'}
STRONG_PREV = {'quoted', 'declared_alias', 'corpus_name', 'already_resolved', 'same_document'}
STRONG = STRONG_PREV | {'declared_alias_decree', 'cue_override'}
SAMPLE_SEED = 4710
SAMPLE_SIZE = 40


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path: Path):
    return json.loads(Path(path).read_text())


def write(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def spread(values: list[int]) -> dict:
    ordered = sorted(values)
    return {'median': statistics.median(ordered), 'p90': ordered[min(len(ordered) - 1, round((len(ordered) - 1) * .9))],
            'max': ordered[-1], 'zero': sum(1 for v in ordered if v == 0)}


def previous_references():
    spec = importlib.util.spec_from_file_location('legal_agent_prev', PREV / '__init__.py',
                                                  submodule_search_locations=[str(PREV)])
    module = importlib.util.module_from_spec(spec)
    sys.modules['legal_agent_prev'] = module
    spec.loader.exec_module(module)
    return importlib.import_module('legal_agent_prev.references')


def label(index, sid: str | None) -> str:
    if not sid:
        return '-'
    article = index.article(sid)
    if article is None:
        return sid
    return f'{article.document_name} {article.label} {article.heading[len(article.label):].strip()[:30]}'.strip()


def build():
    from legal_agent.bridges import Bridges
    from legal_agent.harness import PUBLIC_ORIGINS
    from legal_agent.index import LegalIndex
    from legal_agent.locator import Locator, official_abbreviations
    from legal_agent.references import ReferenceResolver
    from legal_agent.replay import origin_prefixes
    from legal_agent.search import Search
    index = LegalIndex(GEN / 'store.sqlite')
    origins = origin_prefixes(PROJECTION)
    allowed = {d for d in index.documents if origins.get(d) in PUBLIC_ORIGINS}
    resolver = ReferenceResolver(index, GEN / 'navigation/navigation.sqlite')
    new = resolver.resolve_all()
    old = previous_references().ReferenceResolver(index, GEN / 'navigation/navigation.sqlite').resolve_all()
    edges_new = resolver.edges([r for r in new if r.via in STRONG])
    edges_old = resolver.edges([r for r in old if r.via in STRONG_PREV])
    search = Search(GEN, allowed, index)
    official = official_abbreviations(LAW_ROOT)
    locator = Locator(index, official, allowed)
    bridges = Bridges(index, search, edges_new, GEN / 'navigation/navigation.sqlite',
                      mutatis_edges=resolver.mutatis_edges(new))
    return index, search, locator, bridges, new, old, edges_new, edges_old, official


def resolution_diff(index, new, old) -> list[dict]:
    before = {r.reference_id: r for r in old}
    nav = __import__('sqlite3').connect(f"file:{GEN / 'navigation/navigation.sqlite'}?mode=ro", uri=True)
    texts = {rid: json.loads(raw) for rid, raw in nav.execute('SELECT id, json FROM reference')}
    rows = []
    for r in new:
        o = before[r.reference_id]
        if o.target_source_id == r.target_source_id:
            continue
        row = texts[r.reference_id]
        start = row.get('mention_start', 0)
        text = row.get('source_text') or ''
        rows.append({'reference_id': r.reference_id, 'from': label(index, r.source_id),
                     'context': text[max(0, start - 60):start] + '⟦' + text[start:row.get('mention_end', start)] + '⟧'
                                + text[row.get('mention_end', start):row.get('mention_end', start) + 40],
                     'locator': r.locator, 'before': {'via': o.via, 'target': label(index, o.target_source_id)},
                     'after': {'via': r.via, 'target': label(index, r.target_source_id), 'cue': r.cue}})
    return rows


def one_hop(edges, seeds) -> set[str]:
    return set().union(*[edges.get(s, set()) for s in seeds]) if seeds else set()


def measure_cm(index, locator, bridges, edges_new, edges_old) -> dict:
    frozen = read(ADR69 / 'frozen-inputs.json')
    loops = read(ADR69 / 'loop-results.json')['results']
    report = {}
    for name, arm in TRAJECTORIES.items():
        rows = []
        for case in frozen['cases']:
            cid, question = case['case_id'], case['question']
            row = loops[f'{cid}::{arm}::run-001']
            shown_list = list(row['shown_source_ids'])
            shown = set(shown_list)
            adopted = list(row['adopted_source_ids'])
            decisive = set(case['decisive_source_ids'])
            outside = decisive - shown
            located_q = locator.find(question)
            queries = [q for step in row.get('trace', []) if step.get('step') == 'round'
                       for q in step['decision'].get('search', [])]
            located_s = [(q, x) for q in queries for x in locator.find(q)]
            hop_new, hop_old = one_hop(edges_new, adopted), one_hop(edges_old, adopted)
            mutatis = bridges.mutatis(question, shown_list, shown)
            rows.append({
                'case_id': cid, 'question': question,
                'outside': [label(index, s) for s in sorted(outside)],
                'question_locator': [{'label': label(index, x.source_id), 'cue': x.cue, 'via': x.via,
                                      'paragraph': x.paragraph, 'already_card': x.source_id in shown,
                                      'decisive': x.source_id in decisive} for x in located_q],
                'query_locator': [{'query': q, 'label': label(index, x.source_id), 'cue': x.cue, 'via': x.via,
                                   'already_card': x.source_id in shown, 'decisive': x.source_id in decisive}
                                  for q, x in located_s],
                'queries_total': len(queries),
                'reach': {'question_locator': sorted(label(index, s) for s in {x.source_id for x in located_q} & outside),
                          'query_locator': sorted(label(index, s) for s in {x.source_id for _, x in located_s} & outside),
                          'repair_one_hop': sorted(label(index, s) for s in (hop_new - hop_old) & outside),
                          'mutatis': sorted(label(index, h.source_id) for h in mutatis if h.source_id in outside)},
                'one_hop_new_targets': len(hop_new - hop_old), 'one_hop_lost_targets': len(hop_old - hop_new),
                'mutatis': [{'label': label(index, h.source_id), 'via': h.via, 'decisive': h.source_id in decisive}
                            for h in mutatis]})
        summary = {'outside_total': sum(len(r['outside']) for r in rows)}
        for key in ('question_locator', 'query_locator', 'repair_one_hop', 'mutatis'):
            summary[key] = [f"{r['case_id']} {x}" for r in rows for x in r['reach'][key]]
        union = {(r['case_id'], x) for r in rows for key in ('question_locator', 'query_locator', 'repair_one_hop', 'mutatis')
                 for x in r['reach'][key]}
        summary['union'] = sorted(f'{c} {x}' for c, x in union)
        summary['question_locator_total'] = sum(len(r['question_locator']) for r in rows)
        summary['questions_with_locator'] = sum(1 for r in rows if r['question_locator'])
        summary['queries_total'] = sum(r['queries_total'] for r in rows)
        summary['queries_with_locator'] = sum(len({q for q in {y['query'] for y in r['query_locator']}}) for r in rows)
        summary['query_locator_articles'] = sum(len(r['query_locator']) for r in rows)
        summary['query_locator_already_card'] = sum(1 for r in rows for y in r['query_locator'] if y['already_card'])
        summary['mutatis_added'] = spread([len(r['mutatis']) for r in rows])
        summary['one_hop_new_targets'] = spread([r['one_hop_new_targets'] for r in rows])
        summary['one_hop_lost_targets'] = sum(r['one_hop_lost_targets'] for r in rows)
        report[name] = {'arm': arm, 'summary': summary, 'cases': rows}
    return report


def measure_precedents(index, search, locator, bridges) -> dict:
    cases = [c for c in read(PREC_CASES) if c['evaluable']]
    rows = []
    for c in cases:
        cited = {s for g in c['gold'] for s in g['source_ids']}
        valid = {s for g in c['gold'] if g['valid'] for s in g['source_ids']}
        located = locator.find(c['question_raw'], cap=10)
        pre = search.articles(c['question'], limit=8)
        mutatis = bridges.mutatis(c['question'], pre, set(pre))
        rows.append({'case_id': c['id'], 'question_raw': c['question_raw'],
                     'located': [{'label': label(index, x.source_id), 'cue': x.cue, 'via': x.via,
                                  'in_references': x.source_id in cited} for x in located],
                     'valid_hit': bool(valid & {x.source_id for x in located}),
                     'pre_read_hit': bool(valid & set(pre)),
                     'mutatis': [{'label': label(index, h.source_id), 'via': h.via, 'gold': h.source_id in valid}
                                 for h in mutatis],
                     'mutatis_hit': bool(valid & {h.source_id for h in mutatis})})
    located = [x for r in rows for x in r['located']]
    by_via = {}
    for x in located:
        v = by_via.setdefault(x['via'], {'located': 0, 'in_references': 0})
        v['located'] += 1
        v['in_references'] += x['in_references']
    summary = {'cases': len(rows), 'located_total': len(located),
               'precision': round(sum(x['in_references'] for x in located) / max(1, len(located)), 4),
               'by_via': by_via, 'cases_with_valid_hit': sum(r['valid_hit'] for r in rows),
               'not_in_references': [f"{r['case_id']} {x['cue']} → {x['label']}" for r in rows for x in r['located']
                                     if not x['in_references']],
               'mutatis_gain': [r['case_id'] for r in rows if not r['pre_read_hit'] and r['mutatis_hit']],
               'mutatis_added': spread([len(r['mutatis']) for r in rows])}
    return {'summary': summary, 'cases': rows}


def run() -> None:
    index, search, locator, bridges, new, old, edges_new, edges_old, official = build()
    diff = resolution_diff(index, new, old)
    counts: dict[str, int] = {}
    for d in diff:
        key = f"{d['before']['via']} → {d['after']['via']}"
        counts[key] = counts.get(key, 0) + 1
    cm = measure_cm(index, locator, bridges, edges_new, edges_old)
    prec = measure_precedents(index, search, locator, bridges)
    sample = random.Random(SAMPLE_SEED).sample(diff, min(SAMPLE_SIZE, len(diff)))
    write(ART / 'resolution-diff.json', {'changed': len(diff), 'by_transition': counts, 'rows': diff})
    write(ART / 'repair-samples.json', {'seed': SAMPLE_SEED, 'size': len(sample), 'samples': sample})
    write(ART / 'cm-cases.json', {name: value['cases'] for name, value in cm.items()})
    write(ART / 'precedent-cases.json', prec['cases'])
    metrics = {'schema_version': 'adr0471-metrics-v1', 'llm_calls': 0,
               'official_abbreviations': len(official), 'official_resolvable': len(locator.official),
               'resolution': {'total': len(new), 'resolved_before': sum(1 for r in old if r.target_source_id),
                              'resolved_after': sum(1 for r in new if r.target_source_id), 'changed': len(diff),
                              'by_transition': counts,
                              'mutatis_marked': sum(1 for r in new if r.mutatis and r.target_source_id)},
               'cm': {name: value['summary'] for name, value in cm.items()},
               'precedent_set': prec['summary'],
               'repair_sample': {'seed': SAMPLE_SEED, 'size': len(sample), 'judged': None},
               'inputs': {'store_sha256': sha(GEN / 'store.sqlite'),
                          'navigation_sha256': sha(GEN / 'navigation/navigation.sqlite'),
                          'fulltext_sha256': sha(GEN / 'fulltext/fulltext.sqlite'),
                          'adr0469_loop_results_sha256': sha(ADR69 / 'loop-results.json'),
                          'adr0469_frozen_inputs_sha256': sha(ADR69 / 'frozen-inputs.json'),
                          'precedent_cases_sha256': sha(PREC_CASES),
                          'candidate_json_sha256': sha(CAND / 'candidate.json')}}
    write(ART / 'metrics.json', metrics)
    print(json.dumps({k: metrics[k] for k in ('official_abbreviations', 'official_resolvable', 'resolution')},
                     ensure_ascii=False, indent=1))
    for name, s in metrics['cm'].items():
        print(name, json.dumps(s, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in prec['summary'].items()}, ensure_ascii=False, indent=1))


def score() -> None:
    judged = read(ART / 'repair-samples-judged.json')
    metrics = read(ART / 'metrics.json')
    verdicts = [s['verdict'] for s in judged['samples']]
    metrics['repair_sample']['judged'] = {'correct': verdicts.count('correct'), 'mislink': verdicts.count('mislink'),
                                          'unclear': verdicts.count('unclear'), 'judge': judged['judge'],
                                          'method': judged['method']}
    write(ART / 'metrics.json', metrics)
    print(metrics['repair_sample'])


if __name__ == '__main__':
    {'run': run, 'score': score}[sys.argv[1]]()
