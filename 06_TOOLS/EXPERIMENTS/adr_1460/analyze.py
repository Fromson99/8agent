"""ADR-1460 analysis from saved records only (no model call): this run vs ADR-1447 per reading group."""
from common import *
from collections import Counter
import re
import statistics

sys.path.insert(0, str(ROOT / read(DES / 'candidate.json')['code_root'] / '02_BACKEND'))
from semantic_runtime.legal_agent.journal_storage import connect   # noqa: E402

OPEN = ('DEFERRED', 'EXTERNAL_NOT_FOUND')
NUMBER = re.compile(r'제\s*(\d+(?:-\d+)*)\s*조(?:의\s*\d+)?')


def number(text):
    found = NUMBER.search(text or '')
    return found.group(0).replace(' ', '') if found else None


def final_state(art):
    """The parent workflow state with the most finished groups (a continuation carries earlier groups)."""
    best = None
    for journal in sorted(art.glob('run-*/runtime/workflows/*/journal.sqlite')):
        db = connect(str(journal))
        row = db.execute('SELECT journal_text(checkpoint_json) FROM workflow_state').fetchone()
        db.close()
        state = json.loads(row[0]) if row and row[0] else {}
        done = sum(g.get('status') == 'done' for g in (state.get('groups') or {}).values())
        if best is None or done > best[0]:
            best = (done, state, journal)
    return best[1], best[2]


def groups(state):
    out = {}
    for gid, g in (state.get('groups') or {}).items():
        if g.get('status') == 'done':
            out[gid] = [u for u in g.get('units', []) if u.get('status') == 'done']
    return out


def verdicts(units):
    return Counter(u['verdict'] for u in units)


def children(art):
    """Per document-compare child: unit id, definition targets, external reads (document, heading)."""
    out = []
    for journal in sorted(art.glob('run-*/runtime/workflows/*/children/external/legal-agent/runs/*/*/journal.sqlite')):
        db = connect(str(journal))
        task, targets, reads = None, 0, []
        for kind, payload in db.execute('SELECT kind,journal_text(payload_json) FROM event ORDER BY seq'):
            if kind == 'WORKFLOW_TASK_CONTEXT' and task is None:
                task = json.loads(payload)['task']
            elif kind in ('SYSTEM_DEFINITION_ORIGINALS_ACQUIRED', 'SYSTEM_DEFINITION_ORIGINALS_PENDING'):
                targets += len(json.loads(payload)['targets'])
        for did, meta in db.execute('SELECT document_id,journal_text(metadata_json) FROM evidence_unit'):
            reads.append((did, json.loads(meta).get('heading', '')))
        db.close()
        if task and task.get('issues'):
            out.append({'unit_id': task['issues'][0]['id'], 'definition_targets': targets, 'reads': reads,
                        'question_definitions': task.get('question_definitions')})
    return out


def run_usage(art):
    rows = []
    for result in sorted(art.glob('run-*/result.json')):
        r = read(result)
        calls = read(result.parent / 'calls.json') if (result.parent / 'calls.json').exists() else []
        usage = [c.get('usage') or {} for c in calls]
        rows.append({'run': result.parent.name, 'http_status': r.get('http_status'), 'status': r.get('status'), 'stop_code': r.get('stop_code'),
                     'request_seconds': r.get('request_seconds'), 'physical_calls': r.get('physical_calls'), 'unknown': r.get('unknown'),
                     'stage_counts': r.get('stage_counts'), 'duplicate': r.get('duplicate'),
                     'prompt_tokens': sum(u.get('prompt_tokens') or 0 for u in usage),
                     'completion_tokens': sum(u.get('completion_tokens') or 0 for u in usage),
                     'reported_cost_usd': round(sum(u.get('cost') or 0 for u in usage), 6),
                     'groups_finished': (r.get('document_compare') or {}).get('groups_finished')})
    return rows


def compare_inputs(art):
    sizes = []
    for path in sorted(art.glob('run-*/canonical/*.json.gz')):
        if path.name.endswith('-output.json.gz'):
            continue
        import gzip
        value = json.loads(gzip.decompress(path.read_bytes()))
        view = value.get('view') or {}
        if view.get('source_stage') == 'workflow-unit_compare':
            external = [s for s in view.get('sources', []) if s.get('side') == 'external']
            sizes.append({'chars': len(json.dumps(view.get('sources', []), ensure_ascii=False)), 'external_sources': len(external),
                          'nearby': sum(s.get('found_for') == 'nearby_unit' for s in external)})
    return sizes


def number_chasing(state, kids, external_ids):
    labels = {u['unit_id']: u['label'] for g in (state.get('groups') or {}).values() for u in g.get('units', [])}
    total = same = 0
    for child in kids:
        own = number(labels.get(child['unit_id']))
        for did, heading in child['reads']:
            if did in external_ids:
                total += 1
                same += bool(own and number(heading) == own)
    return {'external_reads': total, 'same_number_as_unit': same}


def main():
    state, journal = final_state(ART)
    base_state, base_journal = final_state(BASELINE_ADR / 'artifacts')
    mine, base = groups(state), groups(base_state)
    shared = sorted(set(mine) & set(base))
    def summary(selected, units_of):
        units = [u for gid in selected for u in units_of[gid]]
        v = verdicts(units)
        return {'groups': len(selected), 'units': len(units), 'verdicts': dict(v),
                'open': sum(v[k] for k in OPEN), 'open_share': round(sum(v[k] for k in OPEN) / len(units), 4) if units else None,
                'substantive': len(units) - sum(v[k] for k in OPEN)}
    units = [u for gid in mine for u in mine[gid]]
    substantive = [u for u in units if u['verdict'] not in OPEN]
    both_sides = sum(bool((u.get('comparison') or {}).get('internal_citations')) and bool((u.get('comparison') or {}).get('external_citations'))
                     for u in substantive)
    nearby_cited = sum(any(c['evidence'] in set(u.get('shared_external') or []) for c in (u.get('comparison') or {}).get('external_citations', []))
                       for u in units)
    kids, base_kids = children(ART), children(BASELINE_ADR / 'artifacts')
    external = set(EXTERNAL)
    widened = Counter()
    for u in units:
        widened['units'] += 1
        widened['child_evidence'] += len(u.get('external') or [])
        widened['compared_external'] += len(u.get('articles') or [])
        widened['shared_used'] += len(u.get('shared_external') or [])
    sizes = compare_inputs(ART)
    by_group = []
    for gid in shared:
        by_group.append({'group_id': gid, 'baseline': dict(verdicts(base[gid])), 'candidate': dict(verdicts(mine[gid]))})
    samples = [{'label': u['label'], 'verdict': u['verdict'], 'reason': (u.get('comparison') or {}).get('reason'),
                'internal': [c['quote'] for c in (u.get('comparison') or {}).get('internal_citations', [])][:2],
                'external': [c['quote'] for c in (u.get('comparison') or {}).get('external_citations', [])][:2]}
               for gid in shared for u in mine[gid] if u['verdict'] not in OPEN][:12]
    report = {
        'state_journal': str(journal.relative_to(ROOT)), 'baseline_state_journal': str(base_journal.relative_to(ROOT)),
        'candidate_all': summary(sorted(mine), mine), 'baseline_all': summary(sorted(base), base),
        'shared_groups': {'candidate': summary(shared, mine), 'baseline': summary(shared, base)},
        'substantive_with_both_sides': [both_sides, len(substantive)],
        'units_citing_a_nearby_article': nearby_cited,
        'children': {'count': len(kids), 'definition_targets': sum(k['definition_targets'] for k in kids),
                     'question_definitions_false': sum(k['question_definitions'] is False for k in kids),
                     'baseline_count': len(base_kids), 'baseline_definition_targets': sum(k['definition_targets'] for k in base_kids)},
        'number_chasing': {'candidate': number_chasing(state, kids, external), 'baseline': number_chasing(base_state, base_kids, external)},
        'widening': dict(widened),
        'compare_inputs': {'calls': len(sizes), 'max_chars': max((s['chars'] for s in sizes), default=0),
                           'median_chars': statistics.median([s['chars'] for s in sizes]) if sizes else 0,
                           'with_nearby': sum(s['nearby'] > 0 for s in sizes)},
        'runs': run_usage(ART), 'baseline_runs': run_usage(BASELINE_ADR / 'artifacts'),
        'by_shared_group': by_group, 'samples': samples}
    put(ART / 'analysis.json', report)
    print(json.dumps({k: report[k] for k in ('candidate_all', 'baseline_all', 'shared_groups', 'substantive_with_both_sides',
                                             'units_citing_a_nearby_article', 'children', 'number_chasing', 'widening', 'compare_inputs')},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
