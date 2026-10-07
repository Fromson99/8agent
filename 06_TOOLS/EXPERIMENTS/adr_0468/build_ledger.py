"""ADR-0468: 루프 기록 → retrieval-stage-ledger-v1 원장, manifest 회수 요약값.

단계: pre_read(source, FTS 선읽기) → cards(expand, 참조·재검색 카드) → adopt(select, 모델 채택·대체)
→ evidence(present, 조립기 입력). 정답(결정 조문)은 제품 선택이 끝난 뒤 여기서만 결합한다.
"""
from __future__ import annotations

import json
import sqlite3
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
A = ROOT / '04_EXPERIMENTS/ADR/ADR-0468-legal-agent-loop-server-reading'
GEN = ROOT / '01_DATA/SEMANTIC/GENERATIONS/navigation-source-20260918-body-v1'
sys.path.insert(0, str(ROOT / '06_TOOLS/COMMANDS'))
from adr_structure import _canonical_value_sha256  # noqa: E402

UNIT = 'case_id + canonical article-root coordinate'
SCHEMA = 'retrieval-stage-ledger-v1'
STAGES = [('pre_read', 'source', []), ('cards', 'expand', ['pre_read']),
          ('adopt', 'select', ['cards']), ('evidence', 'present', ['adopt'])]


def key(identity: dict) -> str:
    return json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def ordered(identities) -> list[dict]:
    return sorted({key(i): i for i in identities}.values(), key=key)


def main() -> None:
    nav = sqlite3.connect(str(GEN / 'navigation/navigation.sqlite'))
    coord = {}
    for sid, doc, raw in nav.execute('SELECT id, document_id, json FROM source'):
        unit = json.loads(raw).get('unit_id')
        if unit is None or not str(unit).isdigit():
            continue                      # 조 단위 좌표가 아닌 원천(블록 묶음)은 원장 대상이 아니다
        coord[sid] = {'doc_id': doc, 'node': int(unit)}
    frozen = json.loads((A / 'artifacts/frozen-inputs.json').read_text())
    loops = json.loads((A / 'artifacts/loop-results.json').read_text())['results']
    manifest = json.loads((A / '실험/manifest.json').read_text())
    gold = {c['case_id']: [coord[s] for s in c['decisive_source_ids']] for c in frozen['cases']}

    def stage(stage_id, kind, parents, before, added, discarded, reasons, gold_ids):
        before_keys = {key(i) for i in before}
        after = [i for i in before + added if key(i) not in {key(d) for d in discarded}]
        after = ordered(after)
        gset = {key(g) for g in gold_ids}
        receipts = [{'identity': d, 'reason': reasons[key(d)]} for d in ordered(discarded)]
        reason_counts: dict[str, int] = {}
        for r in receipts:
            reason_counts[r['reason']] = reason_counts.get(r['reason'], 0) + 1
        gb = [i for i in ordered(before) if key(i) in gset]
        ga = [i for i in ordered(added) if key(i) in gset]
        gd = [i for i in ordered(discarded) if key(i) in gset]
        gafter = [i for i in after if key(i) in gset]
        total = len(gold_ids)
        return {'stage_id': stage_id, 'kind': kind, 'parent_stage_ids': parents, 'executed': True, 'skip_reason': None,
                'before': ordered(before), 'added': ordered(added), 'discarded': ordered(discarded), 'after': after,
                'before_count': len(ordered(before)), 'added_count': len(ordered(added)),
                'discarded_count': len(ordered(discarded)), 'after_count': len(after),
                'occurrence_counts': {'before': len(ordered(before)), 'after': len(after),
                                      'canonical_collapsed_before': 0, 'canonical_collapsed_after': 0},
                'discard_receipts': receipts, 'discard_reason_counts': dict(sorted(reason_counts.items())),
                'gold_total': total, 'gold_before': len(gb), 'gold_added': len(ga), 'gold_discarded': len(gd),
                'gold_after': len(gafter), 'golden_recall': (None if total == 0 else len(gafter) / total),
                'gold_before_identities': gb, 'gold_added_identities': ga,
                'discarded_gold': [{'identity': i, 'reason': reasons[key(i)]} for i in gd],
                'gold_after_identities': gafter}

    runs = []
    summary = {}
    for run_id in ('run-001', 'run-002'):
        arms = []
        for arm in ('loop-flash', 'loop-qwen'):
            cases = []
            finals = []
            for c in frozen['cases']:
                row = loops[f"{c['case_id']}::{arm}::{run_id}"]
                cards = row.get('cards') or []
                pre = [coord[x['source_id']] for x in cards if str(x['via']).startswith('FTS')]
                extra = [coord[x['source_id']] for x in cards if not str(x['via']).startswith('FTS')]
                shown = pre + extra
                evidence = [coord[s] for s in row.get('evidence_source_ids') or []]
                ev_keys = {key(e) for e in evidence}
                reasons = {}
                for x in cards:
                    k = key(coord[x['source_id']])
                    if k in ev_keys:
                        continue
                    reasons[k] = 'dropped_by_model' if x.get('dropped') else (
                        'not_adopted_fallback_used' if row.get('fallback') else 'not_adopted_by_model')
                g = gold[c['case_id']]
                s1 = stage('pre_read', 'source', [], [], pre, [], {}, g)
                s2 = stage('cards', 'expand', ['pre_read'], s1['after'], [e for e in extra if key(e) not in {key(p) for p in pre}], [], {}, g)
                dropped = [i for i in s2['after'] if key(i) not in ev_keys]
                s3 = stage('adopt', 'select', ['cards'], s2['after'], [], dropped, reasons, g)
                s4 = stage('evidence', 'present', ['adopt'], s3['after'], [], [], {}, g)
                if row.get('error'):
                    pass
                cases.append({'schema_version': SCHEMA, 'computed_post_selection': True, 'gold_visible_to_product': False,
                              'accounting_unit': UNIT, 'arm_id': arm, 'case_id': c['case_id'], 'gold_total': len(g),
                              'gold_identities': ordered(g), 'stages': [s1, s2, s3, s4]})
                finals.append((s4['after_count'], s4['gold_after'], s4['gold_total'], s2['gold_after']))
            counts = [f[0] for f in finals]
            agg = {'presented_total': sum(counts), 'gold_after': sum(f[1] for f in finals),
                   'gold_total': sum(f[2] for f in finals), 'shown_gold': sum(f[3] for f in finals)}
            arms.append({'arm_id': arm, 'declared_stage_ids': [s[0] for s in STAGES], 'cases': cases, 'aggregate': agg})
            summary[(run_id, arm)] = (counts, agg)
        runs.append({'run_id': run_id, 'arms': arms})
    ledger = {'schema_version': SCHEMA, 'adr_id': manifest['adr_id'], 'experiment_id': manifest['experiment_id'],
              'accounting_unit': UNIT, 'computed_post_selection': True, 'gold_visible_to_product': False, 'runs': runs}
    ledger['artifact_sha256'] = _canonical_value_sha256(ledger)
    path = A / 'artifacts/retrieval-stage-ledger.json'
    path.write_text(json.dumps(ledger, ensure_ascii=False) + '\n')

    import hashlib
    ra = manifest['retrieval_accounting']
    corpus = ra['corpus_total']
    for metric in ('before_filter', 'after_filter', 'presented_total', 'presented_mean', 'presented_p50',
                   'presented_p95', 'golden_recall', 'selectivity'):
        ra[metric] = {}
    for arm in ('loop-flash', 'loop-qwen'):
        counts, agg = summary[('run-001', arm)]
        ordered_counts = sorted(counts)
        mean = statistics.mean(counts)
        ra['before_filter'][arm] = corpus
        ra['after_filter'][arm] = agg['presented_total']
        ra['presented_total'][arm] = agg['presented_total']
        ra['presented_mean'][arm] = round(mean, 4)
        ra['presented_p50'][arm] = statistics.median(counts)
        ra['presented_p95'][arm] = ordered_counts[min(len(ordered_counts) - 1, max(0, round((len(ordered_counts) - 1) * .95)))]
        ra['golden_recall'][arm] = agg['gold_after'] / agg['gold_total']
        ra['selectivity'][arm] = mean / corpus
    ra['stage_ledger']['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    (A / '실험/manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    for (run_id, arm), (counts, agg) in summary.items():
        print(run_id, arm, 'presented', agg['presented_total'], 'shown gold', agg['shown_gold'], '/', agg['gold_total'],
              'evidence gold', agg['gold_after'], '/', agg['gold_total'])


if __name__ == '__main__':
    main()
