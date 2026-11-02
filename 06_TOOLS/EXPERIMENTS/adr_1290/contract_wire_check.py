"""Read-only accounting of the exact new provider payloads; no model calls."""
from common import *
from collections import Counter

freeze = read(DES / 'freeze.json')
sys.path.insert(0, str(ROOT / freeze['code_root'] / '02_BACKEND'))
from semantic_runtime.legal_agent import assessment_input

P = ART / 'live/review-whatif'
question = read(DES / 'cases.json')[0]['request']['json']['question']
source = read(DES / 'source.json')['texts'][0]

def walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)

rows = []
for folder in sorted((P / 'raw').glob('call-*')):
    request = read(folder / 'request.json.gz')
    started = read(folder / 'started.json')
    message = next(m['content'] for m in request['messages'] if m['role'] == 'user')
    try:
        value = json.loads(message)
    except ValueError:
        continue
    if set(value) == {'view'}:
        value = value['view']
    if assessment_input.META not in value:
        continue
    restored = assessment_input.restore(value)
    schema = request.get('response_format', {}).get('json_schema', {}).get('schema', {})
    strings = [x for x in walk(value) if isinstance(x, str)]
    properties = [x['properties'] for x in walk(schema) if isinstance(x, dict) and 'properties' in x]
    current = value.get('current_case', {})
    response_path = folder / 'response.json.gz'
    output = {}
    if response_path.exists():
        raw = read(response_path)
        try:
            output = json.loads(raw['choices'][0]['message']['content'])
        except (ValueError, KeyError, IndexError, TypeError):
            pass
    repeated = Counter(x for x in strings if len(x) >= 80)
    rows.append({
        'number': started['number'], 'turn': started['turn'], 'stage': started['stage'],
        'lossless_restore_verified': True,
        'current_case_facts_and_scenario': set(current) == {'facts', 'scenario'},
        'baseline_question_occurrences': sum(x.count(question) for x in strings),
        'source_clause_occurrences': sum(x.count(source) for x in strings),
        'long_duplicate_string_groups': sum(n > 1 for n in repeated.values()),
        'server_condition_results_requested': any('condition_results' in p for p in properties),
        'shared_links_requested': 'review_links' in schema.get('properties', {}),
        'shared_link_definitions_returned': len(output.get('review_links', [])) if isinstance(output.get('review_links'), list) else None,
        'link_references_returned': sum('link_ref' in x for x in walk(output) if isinstance(x, dict)),
        'wire_user_utf8_bytes': len(message.encode()),
        'restored_packed_view_utf8_bytes': len(json.dumps(restored, ensure_ascii=False, separators=(',', ':')).encode()),
    })
checks = {
    'scenario_inputs_observed': bool(rows),
    'lossless_restore': bool(rows) and all(r['lossless_restore_verified'] for r in rows),
    'authoritative_current_case': bool(rows) and all(r['current_case_facts_and_scenario'] for r in rows),
    'one_baseline_question_and_source': bool(rows) and all(r['baseline_question_occurrences'] == 1 and r['source_clause_occurrences'] == 1 for r in rows),
    'server_results_not_authored': bool(rows) and all(not r['server_condition_results_requested'] for r in rows),
    'shared_review_schema': bool(rows) and all(r['shared_links_requested'] for r in rows),
}
result = {'checks': checks, 'rows': rows, 'model_calls': 0,
          'limits': 'Exact provider payload observations, not a causal quality or token-savings experiment. All full originals retained.'}
put(ART / 'contract-wire-check.json', result)
print(json.dumps(result, ensure_ascii=False))
