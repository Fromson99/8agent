"""One question on one arm through that arm's own service.py, local SQLite photo-rule test generation,
fresh Qwen through the frozen experiment transport; observational hooks only (from ADR-1462 live.py).

  live.py <case_id> <baseline|candidate> [--preflight]
"""
from common import *
import asyncio, importlib, importlib.util, time, traceback, base64, resource
from copy import deepcopy
from contextlib import contextmanager
case_id, arm = sys.argv[1], sys.argv[2]; preflight = '--preflight' in sys.argv
assert arm in ('baseline', 'candidate')
case = next(c for c in read(DES/'live-cases.json') if c['id'] == case_id)
base = ART/('ready' if preflight else 'live')/(case_id+'-'+arm); base.mkdir(parents=True, exist_ok=False)
assert not (ART/'STOP_EXTERNAL.json').exists()
active_pointer = read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release = read(ROOT/active_pointer['manifest_path']); spec_arm = read(DES/'arms.json')[arm]; C = ROOT/spec_arm['code_root']; files = spec_arm['files']
assert all(sha(C/n) == h for n, h in files.items()), 'arm code changed'
for p, h in read(DES/'freeze-live.json')['files'].items(): assert sha(ROOT/p) == h, p
gen_spec = read(DES/'generation.json'); GEN = ROOT/gen_spec['path']; assert sha(GEN/'manifest.json') == gen_spec['manifest_sha256']
metadata = read(GEN/'manifest.json'); assert sha(GEN/'store.sqlite') == metadata['store_sha256']
os.environ.update(GENOS_RUNTIME_DIR=str(base/'runtime'), AD_WORKER_ENABLED='0', GENOS_AUTO_WARMUP='0', GENOS_RESIDENT_DATA='off', LAWRAG_WORKSPACE_ROOT=str(ROOT),
                  OPENBLAS_NUM_THREADS='2', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', PYTHONDONTWRITEBYTECODE='1')
for k in ('DP', 'GENOS_GENERATION', 'GENOS_DATA_ROOT', 'GENOS_RAG_ONTOLOGY_CONFIG', 'GENOS_RAG_ONTOLOGY_ENABLED', 'TEAM_ID', 'AD_WORKSPACE', 'GENOS_STATE_DIR',
          'GENOS_SHARED_LOG_DIR', 'GENOS_DETAIL_LOG_DIR', 'GENOS_RAG_IMPLEMENTATION', 'GENOS_RAG_INITIAL_SEARCH', 'GENOS_DELEGATION_LINKS'):
    os.environ.pop(k, None)
key_env = read(C/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')['key_env']
if not os.environ.get(key_env):
    from dotenv import dotenv_values
    value = dotenv_values(ROOT/'.env').get(key_env); assert value, 'workspace credential missing'
    os.environ[key_env] = value
from resource_guard import Guard
guard = Guard(base); guard.start()
from pinned_imports import install, verify_loaded
install(ART/'transport')
assert not any(k == 'semantic_runtime' or k.startswith('semantic_runtime.') for k in sys.modules)
sys.path[:0] = [str(C/'02_BACKEND'), str(C), str(ROOT)]
import lawrag, lawrag.core, lawrag.research
for pkg, p in [(lawrag, '02_BACKEND/lawrag'), (lawrag.core, '02_BACKEND/lawrag/core'), (lawrag.research, '02_BACKEND/lawrag/research')]:
    pkg.__path__.extend([str(C/p), str(ROOT/p)])
from lawrag.research.experiment_client import ExperimentClient
from lawrag.research.openrouter_legal_adapter import send_reserved
from lawrag.core import request_deadline
verify_loaded(ART/'transport')
def gz(p, v):
    ref = write_raw_json(p, v); put(Path(str(p)+'.ref.json'), {'raw_json': ref})
app = None; calls = []; generations = []; stages = []
try:
    spec = importlib.util.spec_from_file_location('arm_service', C/'service.py'); entry = importlib.util.module_from_spec(spec)
    sys.modules['arm_service'] = entry; spec.loader.exec_module(entry)
    original_local = entry._local_release
    def local_release():
        saved = entry._ROOT; entry._ROOT = ROOT
        try: code_root, generation, binding = original_local()
        finally: entry._ROOT = saved
        import hashlib as _h
        binding = dict(binding, release_id=spec_arm['label'], experiment_arm=arm,
                       code_sha256=_h.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                       profile_sha256=sha(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'),
                       data_manifest_sha256=sha(GEN/'manifest.json'), source_generation_id=metadata['generation_id'],
                       fulltext_manifest_sha256=(metadata.get('fulltext') or {}).get('manifest_sha256'),
                       experiment_generation=gen_spec['path'])
        return C.resolve(), GEN.resolve(), binding
    entry._local_release = local_release
    app = entry.application(); assert Path(app.state.pipeline.contracts.root).resolve() == C.resolve()
    package = type(app.state.pipeline).__module__.rsplit('.', 1)[0]
    mod = lambda name: importlib.import_module(package+'.legal_agent.'+name)
    agent = app.state.pipeline.term_agent; t = agent.transport; gateway = mod('gateway'); errors = mod('errors'); local = mod('local_gemma')
    assert t.provider_policy == read(DES/'provider-policy.json')
    if arm == 'candidate': assert hasattr(mod('linked_documents'), 'locations')
    else:
        try: mod('linked_documents'); raise AssertionError('baseline has linked_documents')
        except ModuleNotFoundError: pass
    allowed = set(case['document_ids'])
    # Team membership as the origin projection supplies it for RAW/internal/<team>/ documents
    # (the scope-file structuring put team only under source_metadata); data files unchanged.
    store = app.state.pipeline.store
    store._projected_teams = {d: frozenset({'risk_team'}) for d in allowed}
    importlib.import_module(package+'.team_scope')._CACHE.clear()
    put(base/'scope-selection.json', {'documents': sorted(allowed), 'reference_answers_used': False})
    assert 'oracledb' not in sys.modules
    views = importlib.import_module(package+'.chat_adapter').views()
    question = case['steps'][0]['question']
    body = views._request_body(question, {'applied_fields': {'mode': '내규'}, 'team_id': 'risk_team', 'session_id': 'adr1484-'+case_id+'-'+arm,
                                          'request_id': 'adr1484-'+case_id+'-'+arm+'-1', 'document_ids': sorted(allowed), 'memory': True,
                                          'public_question': True, 'use_llm': True})
    body['public_question'] = True
    authhash = sha(DES/'authorization.json'); authorization = read(DES/'authorization.json')
    def authorize(query, request, manifest, *, public_question):
        # The product grant names public documents only. This experiment sends the photo-rule test
        # generation under the user's scoped authorization (setup authorization.json): same checks of
        # policy files and generation, scope must be inside the authorized documents.
        assert sha(DES/'authorization.json') == authhash
        scope = set(query['scope']['document_version_ids']); assert scope and scope <= set(authorization['documents'])
        assert manifest['generation_id'] == metadata['generation_id'] and manifest['store_sha256'] == metadata['store_sha256']
        assert manifest['export_allowed'] is False and request['use_llm']
        return {'grant_sha256': t.grant_hash, 'policy_sha256': t.policy_hash, 'public_question_asserted': True,
                'scope_document_ids': sorted(scope), 'experiment_authorization': authhash}
    t.authorize = authorize
    # Entry check (app.external_documents) reads transport.public_scope; same authorized list.
    t.grant = dict(t.grant, public_document_ids=sorted(authorization['documents']))
    audited = ExperimentClient(ROOT, base/'experiment-client', max_calls=40, max_repairs=0, provider_policy=DES/'provider-policy.json')
    limits = read(DES/'criteria.json')['limits']
    def send(*, body, ticket):
        assert not preflight, 'preflight never sends'
        if (ART/'STOP_EXTERNAL.json').exists() or (base/'STOP_EXTERNAL.json').exists(): raise errors.ContractError('Previous unknown: external sending stopped')
        allcalls = [c for p in (ART/'live').glob('*/calls.json') for c in read(p)]
        if len(allcalls) >= limits['physical_total'] or sum((c.get('usage') or {}).get('cost', 0) for c in allcalls) >= limits['reported_cost_usd']:
            raise errors.BudgetExhausted('Frozen experiment total budget')
        verify_loaded(ART/'transport')
        return send_reserved(audited, body=body, ticket=ticket, phase=stages[-1] if stages else 'request', error_module=errors, request_encoder=local.provider_request)
    t.send_once = send
    original_post = request_deadline.post_json
    def post(url, **kw):
        guard.check(); payload = kw['json_body']; assert payload['model'] == 'qwen/qwen3.8-27b' and payload['reasoning'] == {'effort': 'none'}
        assert not any(k in payload for k in ('max_tokens', 'max_output_tokens', 'max_completion_tokens'))
        n = len(calls)+1; out = base/'raw'/f'call-{n:03d}'; out.mkdir(parents=True, exist_ok=False)
        row = {'number': n, 'case_id': case_id, 'arm': arm, 'stage': stages[-1] if stages else None, 'canonical_number': len(generations), 'status': 'started', 'provider': payload['provider']}
        calls.append(row); put(base/'calls.json', calls); gz(out/'request.json.gz', payload); begin = time.monotonic()
        print('MODEL', case_id, arm, n, row['stage'], flush=True)
        try:
            response = original_post(url, **kw)
            try: value = response.json()
            except ValueError: value = {'non_json': response.text}
            gz(out/'response.json.gz', value)
            row.update(status='unknown' if response.status_code >= 500 else 'responded', http_status=response.status_code, usage=value.get('usage'),
                       actual_provider=value.get('provider'), actual_model=value.get('model'))
            if row['status'] == 'unknown': put(base/'STOP_EXTERNAL.json', {'cell': base.name, 'call': n, 'reason': 'remote5xx'})
            return response
        except Exception as exc:
            row.update(status='unknown', error_type=type(exc).__name__, transport_diagnostics=getattr(exc, 'diagnostics', {}))
            if hasattr(exc, 'partial_body'): gz(out/'partial.json.gz', {'body_base64': base64.b64encode(exc.partial_body).decode()})
            put(base/'STOP_EXTERNAL.json', {'cell': base.name, 'call': n, 'reason': 'Unknown physical outcome', 'no_automatic_retry': True}); raise
        finally:
            row['seconds'] = time.monotonic()-begin; put(out/'finished.json', row); put(base/'calls.json', calls)
    request_deadline.post_json = post
    original_generate = gateway.ModelGateway.generate
    def generate(self, phase, view, schema_name, **kwargs):
        n = len(generations)+1; stage = view.get('source_stage', phase); row = {'number': n, 'stage': stage}; generations.append(row); stages.append(stage)
        gz(base/'canonical'/f'{n:03d}.json.gz', {'phase': phase, 'view': view, 'schema': self.protocol.schema(schema_name)})
        try:
            v = original_generate(self, phase, view, schema_name, **kwargs); gz(base/'canonical'/f'{n:03d}-output.json.gz', v); row['status'] = 'accepted'; return v
        except Exception as exc:
            row.update(status='rejected', error_type=type(exc).__name__, error=str(exc)); raise
        finally:
            stages.pop(); put(base/'generations.json', generations)
    gateway.ModelGateway.generate = generate
    loaded = {n: Path(m.__file__).resolve() for n, m in list(sys.modules.items()) if n.split('.')[0] in ('semantic_runtime', package) and getattr(m, '__file__', None)}
    def same_bytes(path):
        if path.is_relative_to(C.resolve()): return str(path.relative_to(C.resolve())) in files and sha(path) == files[str(path.relative_to(C.resolve()))]
        return False
    offenders = sorted(str(v) for v in loaded.values() if not same_bytes(v))
    assert loaded and not offenders, ('every loaded semantic_runtime module must equal the arm inventory bytes', offenders[:8])
    put(base/'binding.json', {'arm': arm, 'loaded_semantic_modules': len(loaded), 'code_root': str(C), 'scope': sorted(allowed), 'profile': agent.profile,
                              'source': metadata, 'root_binding': entry._BINDING, 'selected_pointer': active_pointer, 'source_storage': 'photo-rule test generation (local SQLite)'})
    health = asyncio.run(entry.service({}, {'API_TYPE': 'HEALTH'})); assert health['status'] == 200
    guard.rebase()
    if preflight:
        put(base/'result.json', {'ready': True, 'model_calls': 0, 'http_health': 200, 'arm': arm}); print('PREFLIGHT_READY', case_id, arm, flush=True)
    else:
        turn = base/'turn-1'; turn.mkdir(); put(turn/'request.json', body); begin = time.monotonic()
        response = asyncio.run(entry.service({}, deepcopy(body))); elapsed = time.monotonic()-begin
        value = response.get('body') or {}; gz(turn/'response.json.gz', {'http_status': response['status'], 'body': value})
        answer = value.get('answer') or {}; text = answer.get('text', '') if isinstance(answer, dict) else str(answer); (turn/'answer.txt').write_text(text)
        reply = ((value.get('assembly') or {}).get('term_agent') or {}).get('guided_reply') or {}
        result = {'needs_guidance': reply.get('needs_guidance'), 'case_id': case_id, 'arm': arm, 'question': question, 'http_status': response['status'],
                  'request_seconds': elapsed, 'physical_calls': len(calls), 'unknown': sum(c['status'] == 'unknown' for c in calls),
                  'status': value.get('status'), 'claims': len(answer.get('claims', [])) if isinstance(answer, dict) else 0}
        if response['status'] == 200:
            (turn/'public-answer.txt').write_text(views._public_answer_text(value)); count = len(calls)
            again = asyncio.run(entry.service({}, deepcopy(body)))
            dupe = {'http_status': again['status'], 'same_answer': again.get('body', {}).get('answer') == value.get('answer'), 'extra_model_calls': len(calls)-count}
            put(turn/'duplicate.json', dupe); result['duplicate'] = dupe
        put(turn/'result.json', result); put(base/'result.json', {'case_id': case_id, 'arm': arm, 'turns': [result], 'physical_calls': len(calls), 'unknown': result['unknown']})
        print('LIVE_RESULT', json.dumps(result, ensure_ascii=False), flush=True)
except Exception as exc:
    put(base/'runner-failure.json', {'error_type': type(exc).__name__, 'error': str(exc), 'traceback': traceback.format_exc(), 'model_calls': len(calls)}); raise
finally:
    if app is not None: app.state.pipeline.store.close()
    guard.done.set(); guard.thread.join(2)
    put(base/'resource-final.json', {'sample': guard.check(), 'peak_rss_KiB': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                                     'arm_code_unchanged': all(sha(C/n) == h for n, h in files.items()), 'oracle_driver_loaded': 'oracledb' in sys.modules})
