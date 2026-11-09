"""Post-run diagnosis, no network and no paid call.

Replays one cell's recorded Qwen outputs, in order, through the app built from the
working code (the five product files equal MAIN161) on the real selected generation,
and logs every tool_availability.article_plan refusal so a same-section candidate
recorded as NO_EXECUTABLE_ENDPOINT_SCOPE shows its exact underlying reason.
Usage: replay_diag.py <case_id> <out.json>
"""
import json, sys, tempfile, gzip
from pathlib import Path
ROOT = Path('/home/jin/8-AGENT')
sys.path[:0] = [str(ROOT/'02_BACKEND'), str(ROOT), str(ROOT/'05_TESTS'), str(ROOT/'05_TESTS/CONTRACTS')]
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import tool_availability as av
from test_bounded_source_main import settings
from test_legal_agent_double_harness import wire

case, out = sys.argv[1], Path(sys.argv[2])
cell = ROOT/'04_EXPERIMENTS/ADR/ADR-1423-main161-integration-r5-qwen-r2/artifacts/public-live'/(case+'-selected')
request = json.loads((cell/'turn-1/request.json').read_text())
recorded = [json.load(gzip.open(p))['choices'][0]['message']['content'] for p in sorted(cell.glob('raw/call-*/response.json.gz'))]
scope_ids = json.loads((cell/'binding.json').read_text())['scope']
active = json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
gen = ROOT/json.loads((ROOT/active['manifest_path']).read_text())['data_path']

refusals = []; original = av.article_plan
def logged(s, identity):
    got, why = original(s, identity)
    if why or not got:
        src = s.tools.sources.get(identity['source_id']) or {}
        refusals.append({'identity': identity, 'reason': why, 'source_known': bool(src),
                         'source_unit_id': src.get('unit_id'), 'source_blocks': len(src.get('blocks', [])),
                         'document_in_scope': src.get('document_id') in s.scope if src else None})
    return got, why
av.article_plan = logged

class Replay:
    binding = settings()['model_binding']
    def __init__(self): self.n = 0; self.phases = []
    def validate_model(self): return {'verified': True, 'synthetic': True}
    def send_once(self, *, body, ticket):
        self.phases.append(json.loads(body['messages'][1]['content']).get('view', {}).get('source_stage'))
        content = recorded[self.n]; self.n += 1
        return wire(content)

t = Replay()
with tempfile.TemporaryDirectory() as tmp:
    profile = json.loads((ROOT/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile.update(model_binding=t.binding)
    app = create_app(tmp, gen, contracts_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
        legal_agent_profile=profile, legal_agent_transport=t, runtime_root=Path(tmp)/'runtime',
        memory_identity=lambda _: {'user_id': 'u', 'team_id': 'financial_team', 'document_ids': scope_ids})
    try:
        with TestClient(app) as api:
            r = api.post('/v1/rag/ask', json={k: request[k] for k in ('session_id', 'request_id', 'question', 'document_ids') if k in request})
            body = r.json()
    finally:
        app.state.pipeline.store.close()
reply = ((body.get('assembly') or {}).get('term_agent') or {}).get('guided_reply') or {}
section = [u for u in reply.get('unread_connections', []) if u.get('relation') == 'SAME_SECTION']
out.write_text(json.dumps({'case': case, 'http': r.status_code, 'replayed': t.n, 'recorded': len(recorded),
    'same_answer_text': ((body.get('answer') or {}).get('text') if isinstance(body.get('answer'), dict) else None) ==
        json.load(gzip.open(cell/'turn-1/response.json.gz'))['body']['answer']['text'],
    'article_plan_refusals': refusals,
    'same_section_unread': [{k: u.get(k) for k in ('target_label', 'reason_code', 'source_id')} for u in section]},
    ensure_ascii=False, indent=1))
print(case, r.status_code, 'replayed', t.n, '/', len(recorded), 'refusals', len(refusals))
