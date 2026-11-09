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
# Replay against the frozen MAIN161 candidate snapshot: the working tree has since moved
# (another session selected MAIN164 after this batch), so its pins no longer match its code.
SNAP = ROOT/json.loads((ROOT/'04_EXPERIMENTS/ADR/ADR-1424-main161-cm51-financial-qwen/artifacts/design/candidate-selected.json').read_text())['code_root']
sys.path[:0] = [str(SNAP/'02_BACKEND'), str(SNAP), str(ROOT/'05_TESTS'), str(ROOT/'05_TESTS/CONTRACTS')]
import importlib
for _pkg in ('lawrag', 'lawrag.core', 'lawrag.research', 'lawrag.pipeline', 'lawrag.runtime', 'lawrag.platform'):
    try:
        _m = importlib.import_module(_pkg)
    except ImportError:
        continue
    _rel = Path(*_pkg.split('.'))
    for _base in (SNAP/'02_BACKEND', ROOT/'02_BACKEND'):
        if str(_base/_rel) not in _m.__path__: _m.__path__.append(str(_base/_rel))  # serving bytes first, helpers from ROOT (as live.py)
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
import semantic_runtime.app as _app
_handled=[]
_lep=_app.legal_error_payload
def _lep_log(exc,*a,**k):
    import traceback
    _handled.append({'type':type(exc).__name__,'message':str(exc)[:500],'trace':traceback.format_exception(exc)[-6:]})
    return _lep(exc,*a,**k)
_app.legal_error_payload=_lep_log
from semantic_runtime.legal_agent import tool_availability as av
from test_bounded_source_main import settings
from test_legal_agent_double_harness import wire

case, out = sys.argv[1], Path(sys.argv[2])
cell = ROOT/'04_EXPERIMENTS/ADR/ADR-1424-main161-cm51-financial-qwen/artifacts/public-live'/(case+'-selected')
request = json.loads((cell/'turn-1/request.json').read_text())
recorded = [json.load(gzip.open(p))['choices'][0]['message']['content'] for p in sorted(cell.glob('raw/call-*/response.json.gz'))]
scope_ids = json.loads((cell/'binding.json').read_text())['scope']
gen = ROOT/json.loads((ROOT/'04_EXPERIMENTS/ADR/ADR-1424-main161-cm51-financial-qwen/artifacts/design/baseline.json').read_text())['release']['data_path']

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
from semantic_runtime.legal_agent import errors as _errors
raised=[]
_init=_errors.ProposalError.__init__
def _record(self,*a,**k):
    import traceback
    raised.append({'message':str(a[0]) if a else '','where':[f'{f.name}:{f.lineno}' for f in traceback.extract_stack(limit=6)[:-1]]})
    _init(self,*a,**k)
_errors.ProposalError.__init__=_record

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
    profile = json.loads((SNAP/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile.update(model_binding=t.binding)
    app = create_app(tmp, gen, contracts_root=SNAP, provider=object(), implementation='legal-agent-unified-v6',
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
    'proposal_errors': raised,
    'error_body': body if r.status_code!=200 else None,
    'handled_exceptions': _handled,
    'same_section_unread': [{k: u.get(k) for k in ('target_label', 'reason_code', 'source_id')} for u in section]},
    ensure_ascii=False, indent=1))
print(case, r.status_code, 'replayed', t.n, '/', len(recorded), 'refusals', len(refusals))
