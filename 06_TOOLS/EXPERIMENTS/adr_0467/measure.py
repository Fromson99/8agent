"""ADR-0467 measurement: 항 단위 읽기와 문서 간 참조 해소. 모델 호출 0회.

    .venv/bin/python <this> run      # 측정 실행 → metrics.json, samples.json
"""
from __future__ import annotations

import hashlib
import json
import glob
import statistics as st
import sys
sys.dont_write_bytecode = True
import collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ART = ROOT / '04_EXPERIMENTS/ADR/ADR-0467-legal-index-reference-resolution/artifacts'
CAND = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0467/legal-index'
FROZEN = CAND / 'revisions/rev-001/snapshot/02_BACKEND'
sys.path.insert(0, str(FROZEN))
GEN = ROOT / '01_DATA/SEMANTIC/GENERATIONS/navigation-source-20260918-body-v1'
RUN1 = ROOT / '04_EXPERIMENTS/ADR/ADR-0461-fulltext-candidate-ranking/artifacts/runs-run1'
STRONG = {'quoted', 'declared_alias', 'corpus_name', 'already_resolved', 'same_document'}
SAMPLE_SEED = 4670
SAMPLE_SIZE = 40


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def run() -> None:
    import random
    from legal_agent.index import LegalIndex, SHORT_ARTICLE_CHARS
    from legal_agent.references import ReferenceResolver

    index = LegalIndex(GEN / 'store.sqlite')
    resolver = ReferenceResolver(index, GEN / 'navigation/navigation.sqlite')
    resolutions = resolver.resolve_all()
    via = collections.Counter(r.via for r in resolutions)
    strong = {r.reference_id for r in resolutions if r.via in STRONG and r.target_source_id}
    edges_all = resolver.edges(resolutions)
    edges_strong = resolver.edges([r for r in resolutions if r.via in STRONG])

    # 1) 반사실: run1이 읽은 조문의 참조 1홉이 놓친 결정 조문을 덮는가
    def coverage(edges):
        total = hit = 0
        opened = []
        for path in sorted(glob.glob(str(RUN1 / 'cm-*.json'))):
            run = json.loads(Path(path).read_text())
            state = run['output']['retrieval']['term_agent']
            read = set(state.get('read_source_ids', [])) | set(state.get('selected_ids', []))
            decisive = {s for e in run['expected'] if e['role'] == 'decisive' for s in e['source_ids']}
            reachable = set().union(*[edges.get(x, set()) for x in read]) if read else set()
            opened.append(len(reachable - read))
            for missed in decisive - read:
                total += 1
                hit += missed in reachable
        opened.sort()
        return {'missed_decisive': total, 'reachable_one_hop': hit,
                'opened_median': opened[len(opened) // 2], 'opened_p90': opened[int(len(opened) * 0.9)],
                'opened_max': opened[-1], 'opened_mean': round(sum(opened) / len(opened), 1)}

    # 2) 항 단위 읽기: 결정 조문을 조 전문 대신 항 단위로 주면 전달 글자가 얼마나 주는가
    read_rows = []
    for path in sorted(glob.glob(str(RUN1 / 'cm-*.json'))):
        run = json.loads(Path(path).read_text())
        question = run['question']
        tokens = [t for t in set(question.replace('(', ' ').replace(')', ' ').split()) if len(t) >= 2]
        for e in run['expected']:
            if e['role'] != 'decisive':
                continue
            for sid in e['source_ids']:
                article = index.article(sid)
                if article is None:
                    continue
                view = index.read(sid, tokens=tokens)
                read_rows.append({'case': run['case_id'], 'law': e['law'], 'article': e['article'],
                                  'unit': view['unit'], 'full_chars': article.chars,
                                  'delivered_chars': len(view['text']),
                                  'paragraphs': view['paragraph_count'], 'focus': view.get('focus'),
                                  'siblings': len(view.get('siblings') or [])})
    long_rows = [r for r in read_rows if r['full_chars'] > SHORT_ARTICLE_CHARS]
    saving = [1 - r['delivered_chars'] / r['full_chars'] for r in long_rows]

    # 3) 표본 검사용 원문 맥락
    random.Random(SAMPLE_SEED).shuffle(resolutions)
    samples = []
    for r in resolutions:
        if r.via in ('quoted', 'declared_alias', 'corpus_name') and r.target_source_id and len(samples) < SAMPLE_SIZE:
            target = index.article(r.target_source_id)
            source = index.article(r.source_id)
            samples.append({'reference_id': r.reference_id, 'via': r.via, 'cue': r.cue, 'locator': r.locator,
                            'from': f'{source.document_name} {source.label}' if source else r.source_id,
                            'to': f'{target.document_name} {target.label}' if target else r.target_source_id})
    metrics = {'schema_version': 'adr0467-metrics-v1',
               'generation': str(GEN.relative_to(ROOT)),
               'references_total': len(resolutions),
               'resolved_before': via['already_resolved'],
               'resolved_after': sum(1 for r in resolutions if r.target_source_id),
               'by_via': dict(via.most_common()),
               'cross_document_links': sum(1 for r in resolutions
                                           if r.via in ('quoted', 'declared_alias', 'corpus_name')),
               'coverage_all': coverage(edges_all),
               'coverage_strong_only': coverage(edges_strong),
               'coverage_baseline_index': None,
               'article_reading': {
                   'decisive_articles': len(read_rows),
                   'long_articles': len(long_rows),
                   'delivered_saving_median': round(st.median(saving), 3) if saving else None,
                   'delivered_chars_median_long': int(st.median([r['delivered_chars'] for r in long_rows])) if long_rows else None,
                   'full_chars_median_long': int(st.median([r['full_chars'] for r in long_rows])) if long_rows else None,
                   'focus_found': sum(1 for r in long_rows if r['focus']),
                   'sibling_signals': sum(r['siblings'] for r in read_rows)},
               'alias_documents': sum(1 for v in resolver.aliases.values() if v),
               'inputs': {'store_sha256': sha(GEN / 'store.sqlite'),
                          'navigation_sha256': sha(GEN / 'navigation/navigation.sqlite'),
                          'candidate_json_sha256': sha(CAND / 'candidate.json')}}
    # 기존 색인만 썼을 때의 같은 반사실(비교 기준)
    base_edges: dict[str, set[str]] = {}
    for r in resolutions:
        if r.via == 'already_resolved' and r.target_source_id:
            base_edges.setdefault(r.source_id, set()).add(r.target_source_id)
    metrics['coverage_baseline_index'] = coverage(base_edges)
    write(ART / 'metrics.json', metrics)
    write(ART / 'samples.json', {'seed': SAMPLE_SEED, 'size': len(samples), 'samples': samples})
    write(ART / 'article-reading.json', {'rows': read_rows})
    print(json.dumps({k: metrics[k] for k in ('references_total', 'resolved_before', 'resolved_after',
                                              'cross_document_links', 'coverage_baseline_index',
                                              'coverage_strong_only', 'coverage_all', 'article_reading')},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    {'run': run}[sys.argv[1]]()
