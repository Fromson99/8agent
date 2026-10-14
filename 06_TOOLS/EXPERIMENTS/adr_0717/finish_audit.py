"""Final record and serving-display checks; consumes saved bytes only."""
from pathlib import Path
import hashlib, json, sqlite3, tarfile, tempfile

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0717-main50-cm51-sequential-profile'
O = A / 'artifacts/run-001'
read = lambda p: json.loads(p.read_text())
rows = read(O / 'result.json')['cases']
assert len(rows) == 51
display = []
failures = []
for d in rows:
    cid = d['case_id']
    r = read(O / cid / 'result.json')
    if d['http_status'] == 200:
        stats = r['output']['execution_stats']
        display.append({'case_id': cid, 'calls_match': stats['llm_calls'] == len(d['physical_attempts']),
                        'duration_delta_ms': stats['llm_duration_ms'] - d['all_model_seconds'] * 1000,
                        'each_duration_delta_ms': [x['duration_ms'] - y['seconds'] * 1000
                            for x, y in zip(stats['calls'], d['physical_attempts'], strict=True)]})
    else:
        with tarfile.open(O / cid / 'raw.tar.gz') as t, tempfile.TemporaryDirectory(prefix='cm-failure-audit-') as temp:
            names = [x for x in t.getnames() if x.startswith('runtime/') and x.endswith('/journal.sqlite')]
            records = []
            if names:
                assert len(names) == 1
                p = Path(temp) / 'journal.sqlite'
                p.write_bytes(t.extractfile(names[0]).read())
                db = sqlite3.connect(p.as_uri() + '?mode=ro', uri=True)
                records = [{'kind': k, 'payload': json.loads(v)} for k, v in db.execute(
                    "select kind,payload_json from event where kind in ('RUN_FAILED','CASE_FAILED') order by seq")]
                db.close()
            failures.append({'case_id': cid, 'http_status': d['http_status'],
                             'public_response': r['output'], 'original_failure_events': records})
observations = [read(A / 'artifacts/observations' / (d['case_id'] + '.json')) for d in rows]
policies = {}
repeated_searches = []
searches_with_fingerprint = 0
searches_without_fingerprint = []
for o in observations:
    seen = set()
    for event in o['search_and_rejection_events']:
        if event['kind'] not in ('LAW_FULLTEXT_DIRECTORY', 'LAW_SCOPED_FULLTEXT'):
            continue
        payload = event['payload']
        fingerprint = payload.get('query_fingerprint')
        if not fingerprint:
            searches_without_fingerprint.append({'case_id': o['case_id'], 'seq': event['seq']})
            continue
        searches_with_fingerprint += 1
        signature = json.dumps([event['kind'], fingerprint, payload.get('document_id'), payload.get('document_ids')], sort_keys=True)
        if signature in seen:
            repeated_searches.append({'case_id': o['case_id'], 'seq': event['seq'], 'signature': signature})
        seen.add(signature)
    for call in o['calls']:
        key = json.dumps({'provider': call['requested_provider'], 'model': call['requested_model'],
                          'reasoning': call['requested_reasoning']}, sort_keys=True, ensure_ascii=False)
        policies[key] = policies.get(key, 0) + 1
checks = {
    'public_display_call_counts_match_actual_transport': all(x['calls_match'] for x in display),
    'public_display_duration_agrees_within_5ms': all(abs(x['duration_delta_ms']) < 5 for x in display),
    'public_display_each_duration_agrees_within_5ms': all(abs(v) < 5 for x in display for v in x['each_duration_delta_ms']),
    'actual_model_and_provider': all(x['model_verified'] and x['provider_verified'] for x in observations),
}
archive_hashes = []
for d in rows:
    p = O / d['case_id'] / 'raw.tar.gz'
    receipt = read(O / d['case_id'] / 'raw-archive.json')
    with p.open('rb') as f:
        matches = hashlib.file_digest(f, 'sha256').hexdigest() == receipt['sha256']
    archive_hashes.append({'case_id': d['case_id'], 'matches': matches})
checks['all51_preserved_archive_hashes_match'] = all(x['matches'] for x in archive_hashes)
freeze = read(A / 'artifacts/design/freeze.json')
roots = {'working': R, 'candidate': R / freeze['code_root'],
         'selected_release': R / '08_DEPLOYMENT/RELEASES/compact-input-20261009-r1/code'}
code_checks = {}
for name, root in roots.items():
    mismatches = [p for p, expected in freeze['serving_files'].items()
                  if not (root / p).is_file() or hashlib.sha256((root / p).read_bytes()).hexdigest() != expected]
    code_checks[name] = {'root': str(root.relative_to(R)) or '.', 'files': len(freeze['serving_files']), 'mismatches': mismatches}
    checks[name + '_287_serving_files_unchanged'] = not mismatches
out = {'checks': checks, 'display_cases': display, 'failure_cases': failures,
       'archive_hashes': archive_hashes,
       'code_fingerprints': code_checks,
       'fulltext_search_audit': {'fingerprinted_events': searches_with_fingerprint,
           'events_without_fingerprint': searches_without_fingerprint,
           'repeated_same_case_kind_query_scope': repeated_searches,
           'not_the_same_as_rereading_delivered_subtrees': True},
       'requested_policies': [{'policy': json.loads(k), 'calls': v} for k, v in policies.items()],
       'not_an_accuracy_score': True, 'model_calls_added': 0}
(A / 'artifacts/final-observation-audit.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'checks': checks, 'display_cases': len(display), 'failures': len(failures)}, ensure_ascii=False))
