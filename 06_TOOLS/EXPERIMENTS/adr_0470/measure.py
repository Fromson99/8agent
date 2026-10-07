"""ADR-0470 measurement: 진입 다리 6종의 도달·비용. 모델 호출 0회.

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python <this> run

CM 51: ADR-0469 궤적(loop2-flash, loop2c-qwen run-001)의 카드·채택을 고정하고 다리 후보를 더한다(반사실).
판례 101: 판시사항에서 법 이름·조문 번호를 지운 질문으로, FTS 상위 8 위에 질문만 쓰는 다리를 더한다.
"""
from __future__ import annotations

import hashlib
import json
import statistics
import sys
sys.dont_write_bytecode = True
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ART = ROOT / '04_EXPERIMENTS/ADR/ADR-0470-legal-agent-entry-bridges/artifacts'
CAND = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0470/legal-bridges'
FROZEN = CAND / 'revisions/rev-001/snapshot/02_BACKEND'
sys.path.insert(0, str(ROOT / '02_BACKEND'))
sys.path.insert(0, str(FROZEN))

GEN = ROOT / '01_DATA/SEMANTIC/GENERATIONS/navigation-source-20260918-body-v1'
PROJECTION = ROOT / '01_DATA/PROJECTIONS/document-origins/term-source-adca5fbe3650f90fb372.json'
ADR69 = ROOT / '04_EXPERIMENTS/ADR/ADR-0469-legal-agent-loop-rev2/artifacts'
PREC_ROOT = ROOT / '01_DATA/RAW/prec'
PREC_CASES = ROOT / '09_ARTIFACTS/AUDITS/20260918-precedent-bridge-eval/cases.json'
TRAJECTORIES = {'gemini': 'loop2-flash', 'qwen': 'loop2c-qwen'}
CARD_BRIDGES = ['heading', 'definition', 'reverse', 'precedent', 'synonym']
QUESTION_BRIDGES = ['heading', 'definition', 'precedent', 'synonym']
STRONG = {'quoted', 'declared_alias', 'corpus_name', 'already_resolved', 'same_document'}
MAX_JACCARD = 0.25
SENSITIVITY_CAP = 8


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path: Path):
    return json.loads(Path(path).read_text())


def write(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def spread(values: list[int]) -> dict:
    ordered = sorted(values)
    p90 = ordered[min(len(ordered) - 1, round((len(ordered) - 1) * .9))]
    return {'median': statistics.median(ordered), 'p90': p90, 'max': ordered[-1],
            'mean': round(statistics.mean(ordered), 2), 'zero': sum(1 for v in ordered if v == 0)}


def build():
    from legal_agent.bridges import BridgeConfig, Bridges, PrecedentCorpus
    from legal_agent.harness import PUBLIC_ORIGINS
    from legal_agent.index import LegalIndex
    from legal_agent.references import ReferenceResolver
    from legal_agent.replay import origin_prefixes
    from legal_agent.search import Search
    index = LegalIndex(GEN / 'store.sqlite')
    resolver = ReferenceResolver(index, GEN / 'navigation/navigation.sqlite')
    edges = resolver.edges([r for r in resolver.resolve_all() if r.via in STRONG])
    origins = origin_prefixes(PROJECTION)
    allowed = {d for d in index.documents if origins.get(d) in PUBLIC_ORIGINS}
    search = Search(GEN, allowed, index)
    precedents = PrecedentCorpus(PREC_ROOT, index, allowed)
    bridges = Bridges(index, search, edges, GEN / 'navigation/navigation.sqlite', precedents=precedents)
    wide = Bridges(index, search, edges, GEN / 'navigation/navigation.sqlite', precedents=precedents,
                   config=BridgeConfig(heading_top=SENSITIVITY_CAP, definition_cap=SENSITIVITY_CAP,
                                       reverse_per_adopted=SENSITIVITY_CAP, precedent_m=SENSITIVITY_CAP,
                                       synonym_top=SENSITIVITY_CAP))
    return index, search, precedents, bridges, wide


def label(index, sid: str) -> str:
    article = index.article(sid)
    return f'{article.document_name} {article.label} {article.heading[len(article.label):].strip()[:30]}'.strip() \
        if article else sid


def hops_for(bridges, question: str, exclude: set[str], adopted: list[str] | None, *, skip=frozenset(),
             max_jaccard=None) -> dict[str, list]:
    positions = bridges.positions(question)
    out = {'depth': bridges.depth(question, exclude),
           'heading': bridges.heading(question, exclude),
           'definition': bridges.definition(question, exclude, positions),
           'precedent': bridges.precedent(question, exclude, skip=skip, max_jaccard=max_jaccard),
           'synonym': bridges.synonym(question, exclude)}
    if adopted is not None:
        out['reverse'] = bridges.reverse(question, adopted, exclude, positions)
    return out


def rank_of(hops: list, targets: set[str]) -> int | None:
    for i, hop in enumerate(hops, start=1):
        if hop.source_id in targets:
            return i
    return None


def measure_cm(index, bridges, wide) -> dict:
    frozen = read(ADR69 / 'frozen-inputs.json')
    loops = read(ADR69 / 'loop-results.json')['results']
    report = {}
    for name, arm in TRAJECTORIES.items():
        rows = []
        for case in frozen['cases']:
            cid, question = case['case_id'], case['question']
            row = loops[f'{cid}::{arm}::run-001']
            shown = set(row['shown_source_ids'])
            adopted = [s for s in row['adopted_source_ids']]
            decisive = set(case['decisive_source_ids'])
            outside = sorted(decisive - shown)
            hops = hops_for(bridges, question, shown, adopted)
            wide_hops = hops_for(wide, question, shown, adopted)
            per = {}
            for bridge, items in hops.items():
                ids = [h.source_id for h in items]
                per[bridge] = {'added': len(ids), 'reached_outside': sorted(set(ids) & set(outside)),
                               'decisive_hits': len(set(ids) & decisive),
                               'hops': [{'source_id': h.source_id, 'label': label(index, h.source_id), 'via': h.via,
                                         'decisive': h.source_id in decisive} for h in items]}
            union = set().union(*[{h.source_id for h in hops[b]} for b in CARD_BRIDGES])
            per['union'] = {'added': len(union), 'reached_outside': sorted(union & set(outside)),
                            'decisive_hits': len(union & decisive)}
            sensitivity = {b: rank_of(wide_hops[b], set(outside)) for b in CARD_BRIDGES}
            rows.append({'case_id': cid, 'question': question,
                         'outside': [{'source_id': s, 'label': label(index, s)} for s in outside],
                         'adopted': [label(index, s) for s in adopted], 'bridges': per,
                         'sensitivity_first_rank': sensitivity})
        outside_total = sum(len(r['outside']) for r in rows)
        summary = {'outside_total': outside_total, 'cases_with_outside': sum(1 for r in rows if r['outside'])}
        for bridge in ['depth', *CARD_BRIDGES, 'union']:
            added = [r['bridges'][bridge]['added'] for r in rows]
            reached = [(r['case_id'], s) for r in rows for s in r['bridges'][bridge]['reached_outside']]
            hits = sum(r['bridges'][bridge]['decisive_hits'] for r in rows)
            summary[bridge] = {'reached_outside': len(reached),
                               'reached': [f"{cid} {label(index, s)}" for cid, s in reached],
                               'added_per_question': spread(added), 'added_total': sum(added),
                               'decisive_share_of_added': round(hits / max(1, sum(added)), 3)}
        reached_any = {(r['case_id'], s) for r in rows for s in r['bridges']['union']['reached_outside']}
        reached_any |= {(r['case_id'], s) for r in rows for s in r['bridges']['depth']['reached_outside']}
        summary['unreached'] = [f"{r['case_id']} {o['label']}" for r in rows for o in r['outside']
                                if (r['case_id'], o['source_id']) not in reached_any]
        summary['sensitivity'] = {b: {str(k): sum(1 for r in rows for v in [r['sensitivity_first_rank'][b]]
                                                  if v is not None and v <= k) for k in (1, 2, 3, 4, 6, 8)}
                                  for b in CARD_BRIDGES}
        report[name] = {'arm': arm, 'summary': summary, 'cases': rows}
    return report


def measure_precedents(index, search, bridges, wide) -> dict:
    cases = [c for c in read(PREC_CASES) if c['evaluable']]
    rows = []
    for c in cases:
        question = c['question']
        gold = {s for g in c['gold'] if g['valid'] for s in g['source_ids']}
        pre = search.articles(question, limit=8)
        exclude = set(pre)
        hops = hops_for(bridges, question, exclude, None, skip={c['id']}, max_jaccard=MAX_JACCARD)
        wide_hops = hops_for(wide, question, exclude, None, skip={c['id']}, max_jaccard=MAX_JACCARD)
        rows.append({'case_id': c['id'], 'question': question, 'gold': sorted(gold),
                     'pre_read_hit': bool(gold & exclude),
                     'bridges': {b: {'added': len(items), 'hit': bool(gold & {h.source_id for h in items}),
                                     'hops': [{'label': label(index, h.source_id), 'via': h.via,
                                               'gold': h.source_id in gold} for h in items]}
                                 for b, items in hops.items()},
                     'sensitivity_first_rank': {b: rank_of(wide_hops[b], gold - exclude) for b in QUESTION_BRIDGES}})
    base = sum(r['pre_read_hit'] for r in rows)
    summary = {'cases': len(rows), 'pre_read_hit': base}
    for bridge in ['depth', *QUESTION_BRIDGES]:
        gained = [r['case_id'] for r in rows if not r['pre_read_hit'] and r['bridges'][bridge]['hit']]
        summary[bridge] = {'hit_with_bridge': base + len(gained), 'gain': len(gained), 'gained': gained,
                           'added_per_question': spread([r['bridges'][bridge]['added'] for r in rows])}
    union = [r['case_id'] for r in rows if not r['pre_read_hit']
             and any(r['bridges'][b]['hit'] for b in QUESTION_BRIDGES)]
    summary['union'] = {'hit_with_bridge': base + len(union), 'gain': len(union),
                        'added_per_question': spread([len({h['label'] for b in QUESTION_BRIDGES
                                                           for h in r['bridges'][b]['hops']}) for r in rows])}
    summary['sensitivity'] = {b: {str(k): sum(1 for r in rows if not r['pre_read_hit']
                                              and r['sensitivity_first_rank'][b] is not None
                                              and r['sensitivity_first_rank'][b] <= k) for k in (1, 2, 3, 4, 6, 8)}
                              for b in QUESTION_BRIDGES}
    return {'summary': summary, 'cases': rows}


def run() -> None:
    index, search, precedents, bridges, wide = build()
    cm = measure_cm(index, bridges, wide)
    prec = measure_precedents(index, search, bridges, wide)
    metrics = {'schema_version': 'adr0470-metrics-v1', 'llm_calls': 0,
               'config': bridges.config.__dict__, 'sensitivity_cap': SENSITIVITY_CAP,
               'resources': {'precedents_with_targets': len(precedents.items),
                             'precedent_targets': sum(len(p.targets) for p in precedents.items.values()),
                             'definition_keys': len(bridges.definitions),
                             'synonym_terms': len(bridges.synonyms), 'synonym_surfaces': len(bridges.surfaces),
                             'reverse_targets': len(bridges.reverse_edges)},
               'cm': {name: value['summary'] for name, value in cm.items()},
               'precedent_set': prec['summary'],
               'inputs': {'store_sha256': sha(GEN / 'store.sqlite'),
                          'navigation_sha256': sha(GEN / 'navigation/navigation.sqlite'),
                          'fulltext_sha256': sha(GEN / 'fulltext/fulltext.sqlite'),
                          'adr0469_loop_results_sha256': sha(ADR69 / 'loop-results.json'),
                          'adr0469_frozen_inputs_sha256': sha(ADR69 / 'frozen-inputs.json'),
                          'precedent_cases_sha256': sha(PREC_CASES),
                          'precedent_manifest_sha256': sha(PREC_ROOT / 'manifest.json'),
                          'candidate_json_sha256': sha(CAND / 'candidate.json')}}
    write(ART / 'metrics.json', metrics)
    write(ART / 'cm-cases.json', {name: value['cases'] for name, value in cm.items()})
    write(ART / 'precedent-cases.json', prec['cases'])
    print(json.dumps({'resources': metrics['resources'],
                      'cm': {n: {k: (v if k in ('outside_total', 'cases_with_outside', 'unreached', 'sensitivity')
                                     else {'reached': v['reached_outside'], 'added': v['added_per_question']})
                                 for k, v in s.items()} for n, s in metrics['cm'].items()},
                      'precedent_set': {k: (v if not isinstance(v, dict) or 'gain' not in v
                                            else {'hit': v['hit_with_bridge'], 'gain': v['gain'],
                                                  'added': v['added_per_question']})
                                        for k, v in prec['summary'].items()}},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    {'run': run}[sys.argv[1]]()
