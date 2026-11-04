"""Post-run read-only inspection. Never changes frozen product, prompts or results."""
from common import *
import collections

C = ROOT / read(DES / 'candidate-main142.json')['code_root']
sys.path.insert(0, str(C / '02_BACKEND'))
from semantic_runtime.legal_agent import journal_storage

base = ART / 'public-live/charter-main142'
assert (base / 'resource-final.json').exists(), 'Wait for the live worker to close'

def decode(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v

def keys(v, wanted, path=''):
    if isinstance(v, dict):
        for k, x in v.items():
            child = path + '/' + k
            if k in wanted:
                yield child
            yield from keys(x, wanted, child)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from keys(x, wanted, path + '/' + str(i))

assessments = []
events = []
memory = []
goals = []
for p in sorted((base / 'runtime').rglob('*.sqlite')):
    db = journal_storage.connect(p.as_uri() + '?mode=ro', uri=True)
    tables = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'goal' in tables:
        for x in db.execute('SELECT * FROM goal ORDER BY ordinal'):
            goals.append({k: decode(v) for k, v in dict(x).items()})
        for x in db.execute('SELECT * FROM event ORDER BY id'):
            memory.append({k: decode(v) for k, v in dict(x).items()})
    elif 'event' in tables:
        for x in db.execute('SELECT seq,kind,payload_json FROM event ORDER BY seq'):
            payload = json.loads(x['payload_json'])
            if x['kind'] == 'ASSESSMENT_VALIDATED':
                assessments.append({'run_id': p.parent.name, 'seq': x['seq'], **payload})
            if any(t in x['kind'] for t in ('REJECT', 'ERROR', 'REPAIR', 'STOP', 'COMMAND', 'REQUEST_ENTRY', 'CASE_EXECUTION')):
                events.append({'run_id': p.parent.name, 'seq': x['seq'], 'kind': x['kind'], 'payload': payload})
    db.close()

generation_checks = []
for p in sorted((base / 'canonical').glob('[0-9][0-9][0-9].json.gz')):
    data = read(p)
    stage = data['view'].get('source_stage')
    if not stage or 'assess' not in stage:
        continue
    output_path = p.with_name(p.name.replace('.json.gz', '-output.json.gz'))
    feedback = data['view'].get('repair_feedback') or {}
    wire_path = base / 'raw' / ('call-' + p.name[:3]) / 'request.json.gz'
    wire = read(wire_path) if wire_path.exists() else {}
    generation_checks.append({
        'number': int(p.name[:3]), 'stage': stage,
        'canonical_link_properties': list(keys(data['schema'], {'review_links', 'link_ref'})),
        'wire_link_properties': list(keys(wire.get('response_format', {}), {'review_links', 'link_ref'})),
        'repair_validation': feedback.get('validation'),
        'output_claims': len(read(output_path).get('claims', [])) if output_path.exists() else None,
        'output_link_keys': list(keys(read(output_path), {'review_links', 'link_ref'})) if output_path.exists() else None,
    })

raw = {'memory_events': memory, 'goals': goals, 'assessments': assessments, 'diagnostic_events': events}
ref = write_raw_json(ART / 'inspection-records.json.gz', raw)
summary = {
    'raw': ref, 'model_calls': 0,
    'memory_commands': [{k: x.get(k) for k in ('id', 'goal', 'request', 'utterance', 'kind', 'command')} for x in memory],
    'goal_count': len(goals),
    'assessment_generations': generation_checks,
    'saved_assessments': [{
        'run_id': x['run_id'], 'claims': len(x['assessment'].get('claims', [])),
        'answer_coverage': x['assessment'].get('answer_coverage'),
        'disposition': x['assessment'].get('disposition'),
        'review_links_version': x['assessment'].get('assessment_basis', {}).get('review_links_version'),
        'review_links_receipt': x['assessment'].get('review_links'),
        'failure': x['assessment'].get('model_proposal', {}).get('failure'),
    } for x in assessments],
    'rejected_events': [x for x in events if 'REJECT' in x['kind']],
}
put(ART / 'inspection-summary.json', summary)
print(json.dumps(summary, ensure_ascii=False))
