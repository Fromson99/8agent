"""Aggregate ADR-1425 with the criteria frozen before the run; no model call.

``ADR1425_RUN=<dir>`` computes and prints the same numbers for another run directory
(used for the offline mock check) without writing any ADR record.
"""
from common import *
import json, os, statistics, time

RUNDIR = Path(os.environ.get('ADR1425_RUN', RUN))
DRY = RUNDIR != RUN
PLACES = ('units', 'not_target', 'hold')


def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))], 3)


def compute():
    freeze, criteria, schedule = read(DES / 'freeze.json'), read(DES / 'criteria.json'), read(DES / 'schedule.json')
    changed = [name for name, expected in freeze['files'].items() if sha(ROOT / name) != expected]
    events = [json.loads(line) for line in (RUNDIR / 'journal.jsonl').read_text('utf-8').splitlines()]
    store, built, loaded = Store(), {}, {}

    def group_of(item):
        code = CODE[item['arm']]
        if code not in loaded:
            loaded[code] = modules(code)
        slot = (item['case'], item['arm'])
        if slot not in built:
            built[slot] = loaded[code][0].build(store, CASES[item['case']], max_rows=ARMS[item['arm']], **FIXED)['groups']
        return built[slot][item['group_index']], loaded[code][1]

    by_key = {}
    for event in events:
        by_key.setdefault(event['key'], []).append(event)
    # Saved requests, in the order they were sent.
    calls = {}
    for folder in sorted((RUNDIR / 'calls').glob('s*/call-*')):
        calls.setdefault(folder.name.split('-', 2)[2], []).append(folder)
    sent_after_unknown, request_mismatch, request_count, groups, places = [], [], 0, [], {}
    for item in schedule:
        key = '/'.join((item['case'], item['arm'], item['group_id']))
        rows = by_key.get(key, [])
        results = [e for e in rows if e['event'] == 'RESULT']
        final = next((e for e in rows if e['event'] == 'FINAL'), None)
        group, review = group_of(item)
        did = CASES[item['case']]
        expected = review.payload(store.name(did), group, lambda segments: store.text(did, segments))
        folders = []
        for intent in (e for e in rows if e['event'] == 'INTENT'):
            for folder in calls.get(intent['phase'], []):
                request = read(folder / 'request.json'); request_count += 1; folders.append(str(folder.relative_to(RUNDIR)))
                user = json.loads(request['messages'][1]['content'])
                if (user['rows'] != expected['rows'] or user['document'] != expected['document'] or user['context'] != expected['context']
                        or request['model'] != 'qwen/qwen3.8-27b' or any(k in request for k in ('max_tokens', 'max_completion_tokens'))):
                    request_mismatch.append(str(folder.relative_to(RUNDIR)))
        seen_unknown = False
        for event in rows:
            if event['event'] == 'INTENT' and seen_unknown:
                sent_after_unknown.append(key)
            if event['event'] == 'RESULT' and event['status'] == 'UNKNOWN':
                seen_unknown = True
        value = None
        if final and final['final'] == 'COMPLETE':
            value = read(RUNDIR / folders[-1] / 'output.json')
            report = review.accounting(value, group)
            assert review.complete(report), key
            for ref, place in report['placed_once'].items():
                places.setdefault((item['case'], group['rows'][int(ref[1:]) - 1]['row_id']), {})[item['arm']] = place
        groups.append({'seq': item['seq'], 'case': item['case'], 'arm': item['arm'], 'group_index': item['group_index'], 'title': group['title'],
                       'rows': len(group['rows']), 'chars': group['chars'], 'final': final['final'] if final else 'NOT_RUN',
                       'attempts': [{k: e.get(k) for k in ('attempt', 'status', 'seconds', 'physical_requests', 'missing', 'duplicated', 'units', 'placed', 'usage', 'detail')} for e in results],
                       'units': len(value['units']) if value else None, 'call_folders': folders})

    def summary(selected):
        attempts = [a for g in selected for a in g['attempts']]
        first = [g['attempts'][0] for g in selected if g['attempts']]
        usage = [a['usage'] for a in attempts if a['usage']]
        complete = [g for g in selected if g['final'] == 'COMPLETE']
        return {'groups': len(selected), 'rows': sum(g['rows'] for g in selected),
                'first_complete': sum(a['status'] == 'COMPLETE' for a in first),
                'first_complete_rate': round(sum(a['status'] == 'COMPLETE' for a in first) / len(selected), 4) if selected else None,
                'final_complete': len(complete), 'final_by_status': {s: sum(g['final'] == s for g in selected) for s in sorted({g['final'] for g in selected})},
                'first_incomplete': sum(a['status'] == 'INCOMPLETE' for a in first), 'first_format': sum(a['status'] == 'FORMAT' for a in first),
                'first_rows_missing': sum(len(a['missing'] or []) for a in first), 'first_rows_duplicated': sum(len(a['duplicated'] or []) for a in first),
                'corrective_calls': sum(a['attempt'] == 2 for a in attempts), 'unknown': sum(g['final'] == 'UNKNOWN' for g in selected),
                'physical_requests': sum(a['physical_requests'] for a in attempts),
                'input_tokens': sum(u['input_tokens'] or 0 for u in usage), 'output_tokens': sum(u['output_tokens'] or 0 for u in usage),
                'reported_cost_usd': round(sum(u['cost_usd'] or 0 for u in usage), 8), 'usage_complete': len(usage) == len(attempts),
                'seconds_total': round(sum(a['seconds'] for a in attempts), 3), 'seconds_p50': percentile([a['seconds'] for a in attempts], .5),
                'seconds_p95': percentile([a['seconds'] for a in attempts], .95),
                'units': sum(g['units'] for g in complete),
                'rows_placed': {p: sum((g['attempts'][-1]['placed'] or {}).get(p, 0) for g in complete) for p in PLACES}}

    by_case_arm = {case: {arm: summary([g for g in groups if g['case'] == case and g['arm'] == arm]) for arm in ARMS} for case in CASES}
    by_arm = {arm: summary([g for g in groups if g['arm'] == arm]) for arm in ARMS}

    def meets(row):
        return bool(row['groups'] and row['first_complete_rate'] >= .9 and row['final_complete'] == row['groups'] and row['unknown'] == 0)
    arm_meets = {arm: all(meets(by_case_arm[case][arm]) for case in CASES) for arm in ARMS}
    recommended = next((ARMS[arm] for arm in ('rows60', 'baseline', 'rows15') if arm_meets[arm]), None)
    agreement = {}
    for case in CASES:
        full = [v for (c, _), v in places.items() if c == case and len(v) == len(ARMS)]
        agreement[case] = {'rows_placed_in_all_arms': len(full), 'same_place_in_all_arms': sum(len(set(v.values())) == 1 for v in full),
                           'pairs': {a + '|' + b: {'both': sum(1 for (c, _), v in places.items() if c == case and a in v and b in v),
                                                  'same': sum(1 for (c, _), v in places.items() if c == case and a in v and b in v and v[a] == v[b])}
                                     for a, b in (('baseline', 'rows15'), ('baseline', 'rows60'), ('rows15', 'rows60'))}}
    journal_physical = sum(e.get('physical_requests', 0) for e in events if e['event'] == 'RESULT')
    integrity = {'frozen_files_changed': changed, 'request_folders': request_count, 'journal_physical_requests': journal_physical,
                 'requests_differing_from_stored_original': request_mismatch, 'groups_sent_after_unknown': sent_after_unknown,
                 'groups_not_run': sum(g['final'] == 'NOT_RUN' for g in groups)}
    required = {'public_documents_and_exact_originals': not request_mismatch and request_count > 0,
                'default_arm_thresholds': arm_meets['baseline'],
                'accounting_and_freeze': not changed and request_count == journal_physical and not sent_after_unknown and not integrity['groups_not_run']}
    times = [e['at'] for e in events]
    return {'schema_version': 'adr-1425-result-v1', 'criteria_sha256': sha(DES / 'criteria.json'), 'by_case_arm': by_case_arm, 'by_arm': by_arm,
            'arm_meets_thresholds': arm_meets, 'recommended_max_rows': recommended, 'agreement': agreement, 'integrity': integrity,
            'required': required, 'success_criteria_met': all(required.values()),
            'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(min(times))), 'ended_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(max(times))),
            'semantic_quality_graded': False}, groups


if __name__ == '__main__':
    result, groups = compute()
    print(json.dumps({k: result[k] for k in ('by_arm', 'arm_meets_thresholds', 'recommended_max_rows', 'agreement', 'integrity', 'required')}, ensure_ascii=False, indent=1))
    for case in CASES:
        for arm in ARMS:
            row = result['by_case_arm'][case][arm]
            print(case, arm, {k: row[k] for k in ('groups', 'first_complete', 'final_complete', 'first_rows_missing', 'first_rows_duplicated', 'first_format', 'corrective_calls', 'physical_requests', 'seconds_p50', 'seconds_p95', 'units', 'rows_placed')})
    if not DRY:
        put(RUN / 'result.json', result)
        put(RUN / 'groups.json', groups)
        print('written', RUN / 'result.json')
