"""One document comparison (문서 대사) request through the native API on the frozen candidate (ADR-1460: the external-search fix candidate r3); observational hooks only.

Modes: default sends to the real model once; ``--scripted`` runs the same wiring on the
fixture corpus with canned model responses (no network); ``--preflight`` builds the app
and checks authorization without sending. Pattern of ADR-1293/1424 runners.
"""
from common import *
import importlib, importlib.util, resource, time, traceback, base64
from copy import deepcopy

MODE = ('scripted' if '--scripted' in sys.argv else 'preflight' if '--preflight' in sys.argv else
        'resume-dry' if '--resume-dry' in sys.argv else 'resume' if '--resume' in sys.argv else
        'fresh' if '--fresh' in sys.argv else 'continue' if '--continue' in sys.argv else 'live')
# continue: send "문서 대사: 계속" in run-001's session (run-002+), only after the user decides to continue a stopped run.
# fresh: the same request in a new session (run-002+), after run-001's saved state became unusable.
# resume: continue run-001's saved workflow state through the product's resume API (run-002+).
# resume-dry: the same on a copy of that state with sending forbidden (checks it reaches a model call).
SENDS, RESUME = MODE in ('live', 'resume', 'fresh', 'continue'), MODE in ('resume', 'resume-dry')
GIB = 1024 ** 3
os.environ.update(OPENBLAS_NUM_THREADS='2', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', PYTHONDONTWRITEBYTECODE='1', AD_WORKER_ENABLED='0',
                  GENOS_AUTO_WARMUP='0', GENOS_RESIDENT_DATA='off', LAWRAG_WORKSPACE_ROOT=str(ROOT))
for name in ('DP', 'GENOS_GENERATION', 'GENOS_DATA_ROOT', 'GENOS_RAG_ONTOLOGY_CONFIG', 'GENOS_RAG_ONTOLOGY_ENABLED', 'TEAM_ID', 'AD_WORKSPACE',
             'GENOS_STATE_DIR', 'GENOS_SHARED_LOG_DIR', 'GENOS_DETAIL_LOG_DIR', 'GENOS_RAG_IMPLEMENTATION'):
    os.environ.pop(name, None)
for name, expected in read(DES / 'freeze.json')['files'].items():
    assert sha(ROOT / name) == expected, 'frozen file changed: ' + name
criteria, candidate = read(DES / 'criteria.json'), read(DES / 'candidate.json')
limits = criteria['limits']
case = read(DES / ('scripted-case.json' if MODE == 'scripted' else 'case.json'))
C = ROOT / candidate['code_root']
assert all(sha(C / n) == h for n, h in candidate['files'].items())
if RESUME or MODE in ('fresh', 'continue'):
    number = 2
    while (ART / ('run-%03d' % number)).exists() or (ART / 'preflight' / ('resume-dry-%d' % number)).exists():
        number += 1
    base = ART / ('run-%03d' % number if MODE in ('resume', 'fresh', 'continue') else 'preflight/resume-dry-%d' % number)
    assert not (ART / 'STOP_EXTERNAL.json').exists(), 'sending stopped'
    assert MODE == 'fresh' or (ART / 'run-001/runtime').is_dir(), 'nothing to resume'
else:
    base = ART / {'live': 'run-001', 'scripted': 'preflight/scripted', 'preflight': 'preflight/ready'}[MODE]
if MODE == 'live':
    assert not (ART / 'STOP_EXTERNAL.json').exists() and not (ART / 'run-001').exists(), 'this ADR sends one request once'
CAP = 10 ** 6   # no experiment call cap (user direction); the client still needs an integer


def busy():
    """Another experiment's model runner (live.py) is running; wait scripts and test runs do not block (user direction)."""
    found = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            command = (entry / 'cmdline').read_bytes().replace(b'\0', b' ').decode('utf-8', 'replace')
        except OSError:
            continue
        import re
        # Any experiment runner, also one started as "python live.py ..." from its own folder.
        if re.search(r'bin/python[0-9.]* (-X \S+ )?([^ ]*/)?live[.]py', command) and 'adr_1460' not in command:
            found.append(int(entry.name))
    return found


def memory():
    rows = {x.split(':')[0]: int(x.split()[1]) * 1024 for x in Path('/proc/meminfo').read_text().splitlines()
            if x.startswith(('MemAvailable:', 'SwapFree:'))}
    return rows['MemAvailable'], rows['SwapFree']


if SENDS:
    waited = 0
    while True:
        available, swap_free = memory()
        others = busy()
        if not others and available >= limits['ram_start_gib'] * GIB and swap_free >= limits.get('swap_free_start_gib', 0) * GIB:
            if waited:
                time.sleep(20)
                if busy():
                    continue
            break
        if waited == 0:
            print('WAIT host busy', others, round(available / GIB, 2), round(swap_free / GIB, 2), flush=True)
        if waited >= limits['wait_seconds']:
            put(ART / 'not-started.json', {'reason': 'host stayed busy or below resource floors', 'waited_seconds': waited,
                                           'available_gib': available / GIB, 'swap_free_gib': swap_free / GIB, 'busy_pids': others, 'model_calls': 0})
            raise SystemExit(3)
        time.sleep(30); waited += 30
    print('START after waiting', waited, 'seconds', flush=True)
base.mkdir(parents=True, exist_ok=False)
runtime = base / 'runtime'
if MODE in ('resume', 'continue'):
    runtime = ART / 'run-001/runtime'          # the one saved workflow state, continued in place
elif MODE == 'resume-dry':
    import shutil
    shutil.copytree(ART / 'run-001/runtime', runtime)
os.environ['GENOS_RUNTIME_DIR'] = str(runtime)
from resource_guard import Guard


class Idle:
    """No-network modes send nothing; the frozen guard applies to the live run only."""
    def check(self):
        return None

    def rebase(self):
        return None


guard = Guard(base) if SENDS else Idle()
if SENDS:
    guard.start()
from pinned_imports import install, verify_loaded
install(ART / 'transport')
import lawrag, lawrag.core, lawrag.research
for package, path in [(lawrag, '02_BACKEND/lawrag'), (lawrag.core, '02_BACKEND/lawrag/core'), (lawrag.research, '02_BACKEND/lawrag/research')]:
    package.__path__.extend([str(C / path), str(ROOT / path)])
sys.path[:0] = [str(C / '02_BACKEND'), str(ROOT)]
app = client = None
calls, generations, active = [], [], []
try:
    source = read(DES / ('scripted-source.json' if MODE == 'scripted' else 'comparison-source.json'))
    data, source_manifest = ROOT / source['data_path'], source['source_manifest']
    assert sha(data / 'store.sqlite') == source_manifest['store_sha256']
    profile = read(C / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
    assert profile['candidate_navigation']['supervisor_mode'] == 'enforce'
    from semantic_runtime.app import create_app
    from semantic_runtime.provider import Haiku
    from semantic_runtime.legal_agent.local_gemma import LocalQwen38Transport, provider_request
    from semantic_runtime.legal_agent import gateway, errors, workflow_execution
    from fastapi.testclient import TestClient
    auth_hash, allowed = sha(DES / 'authorization.json'), set(case['document_ids'])
    questions = (case['question'], case['question'].split(':', 1)[1].strip()) + (('계속',) if MODE == 'continue' else ())

    class Authorized(LocalQwen38Transport):
        """Experiment grant for the synthetic corpus only; the product grant is bound to the real generation."""
        @property
        def public_scope(self):
            return tuple(sorted(allowed))

        def authorize_workflow(self, request, binding):
            assert request['question'] in questions and request['workflow_id'] == 'risk_team_document_compare_workflow'
            assert set(request['document_ids']) == allowed and binding['generation_id'] == source_manifest['generation_id']
            assert binding['store_sha256'] == source_manifest['store_sha256']
            return {'kind': 'USER_AUTHORIZED_WORKFLOW', 'grant_sha256': self.grant_hash, 'policy_sha256': self.policy_hash,
                    'scope_document_ids': sorted(allowed), 'generation_id': source_manifest['generation_id'],
                    'store_sha256': source_manifest['store_sha256'], 'principal': request['principal'],
                    'public_question_asserted': False, 'experiment_authorization': auth_hash}

        def authorize(self, query, request, manifest, *, public_question):
            assert sha(DES / 'authorization.json') == auth_hash and sha(self.policy_path) == self.policy_hash
            scope = set(query['scope']['document_version_ids'])
            assert scope and scope <= allowed and manifest['generation_id'] == source_manifest['generation_id']
            assert manifest['store_sha256'] == source_manifest['store_sha256'] and manifest['export_allowed'] is False
            parent = workflow_execution.authorization()
            # Only the document comparison workflow and its child investigations may send.
            assert parent is not None and parent['experiment_authorization'] == auth_hash and parent['kind'] == 'USER_AUTHORIZED_WORKFLOW'
            return {**parent, 'scope_document_ids': sorted(scope)}

    transport = Authorized(C, ROOT)
    profile.update(model_binding=transport.binding, max_output_tokens=None)
    assert transport.provider_policy == read(DES / 'provider-policy.json')
    from lawrag.research.experiment_client import ExperimentClient
    from lawrag.research.openrouter_legal_adapter import send_reserved
    from lawrag.core import request_deadline
    verify_loaded(ART / 'transport')
    if MODE == 'scripted':
        sys.path[:0] = [str(ROOT / '05_TESTS'), str(ROOT / '05_TESTS/CONTRACTS')]
        import lawrag.pipeline  # the fixture chain builds its own tiny corpus helpers from the working pipeline package
        lawrag.pipeline.__path__.append(str(ROOT / '02_BACKEND/lawrag/pipeline'))
        os.environ['WORKFLOW_TEST_CODE_ROOT'] = str(C)
        spec = importlib.util.spec_from_file_location('adr1460_scripted', ROOT / '05_TESTS/CONTRACTS/test_document_compare_mode.py')
        fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
        scripted = fixture.DocTransport()

        def canned(*, body, ticket):
            response = scripted.send_once(body=body, ticket=ticket)
            # Canned content is returned under the pinned binding so the product's response-model check applies unchanged.
            response['body_json']['model'] = transport.binding['model']
            response['body_json']['choices'][0].setdefault('finish_reason', 'stop')
            return response
        transport.send_once = canned
    else:
        audited = ExperimentClient(ROOT, base / 'experiment-client', max_calls=CAP, max_repairs=0,
                                   provider_policy=DES / 'provider-policy.json')

        def send(*, body, ticket):
            if MODE == 'fresh':
                guard.wait_for_room()
            if not SENDS:
                raise RuntimeError('PREFLIGHT_EXTERNAL_SEND_FORBIDDEN')
            if (ART / 'STOP_EXTERNAL.json').exists():
                # Stop as a budget stop, not an integrity failure: the product saves finished groups.
                raise errors.BudgetExhausted('Unknown physical outcome: external sending stopped')
            verify_loaded(ART / 'transport')
            return send_reserved(audited, body=body, ticket=ticket, phase=active[-1] if active else 'request',
                                 error_module=errors, request_encoder=provider_request)
        transport.send_once = send
        original_post = request_deadline.post_json

        def post(url, **kwargs):
            guard.check(); payload = kwargs['json_body']
            assert payload['model'] == 'qwen/qwen3.8-27b' and not any(k in payload for k in ('max_tokens', 'max_output_tokens', 'max_completion_tokens'))
            number = len(calls) + 1; folder = base / 'raw' / ('call-%03d' % number); folder.mkdir(parents=True, exist_ok=False)
            row = {'number': number, 'stage': active[-1] if active else None, 'status': 'started', 'provider': payload['provider']}
            calls.append(row); put(base / 'calls.json', calls); gz(folder / 'request.json.gz', payload); begin = time.monotonic()
            print('MODEL', number, row['stage'], flush=True)
            try:
                response = original_post(url, **kwargs)
                try:
                    body = response.json()
                except ValueError:
                    body = {'non_json_body': response.text}
                gz(folder / 'response.json.gz', body)
                row.update(status='responded', http_status=response.status_code, usage=body.get('usage'), actual_provider=body.get('provider'),
                           finish_reason=((body.get('choices') or [{}])[0] or {}).get('finish_reason'))
                return response
            except Exception as error:
                row.update(status='unknown', error_type=type(error).__name__, transport_diagnostics=getattr(error, 'diagnostics', {}))
                if hasattr(error, 'partial_body'):
                    gz(folder / 'partial.json.gz', {'body_base64': base64.b64encode(error.partial_body).decode()})
                put(ART / 'STOP_EXTERNAL.json', {'call': number, 'reason': 'Unknown physical provider outcome', 'no_automatic_retry': True})
                raise
            finally:
                row['seconds'] = round(time.monotonic() - begin, 3); put(base / 'calls.json', calls)
        request_deadline.post_json = post
    original_generate = gateway.ModelGateway.generate

    def generate(self, phase, view, schema_name, **kwargs):
        number = len(generations) + 1; stage = view.get('source_stage', phase)
        row = {'number': number, 'stage': stage}; generations.append(row); active.append(stage)
        gz(base / 'canonical' / ('%03d.json.gz' % number), {'phase': phase, 'view': view, 'schema': self.protocol.schema(schema_name) if isinstance(schema_name, str) else schema_name})
        begin = time.monotonic()
        try:
            value = original_generate(self, phase, view, schema_name, **kwargs)
            gz(base / 'canonical' / ('%03d-output.json.gz' % number), value); row['status'] = 'accepted'
            return value
        except Exception as error:
            row.update(status='rejected', error_type=type(error).__name__, error=str(error)[:500]); raise
        finally:
            active.pop(); row['seconds'] = round(time.monotonic() - begin, 3); put(base / 'generations.json', generations)
    gateway.ModelGateway.generate = generate
    # A resumed run must keep the release binding of run-001 exactly, or the product refuses it.
    binding = {'mode': 'ADR1460-native-extfix-r3', 'case_id': case['id'], 'run_mode': 'live' if RESUME or MODE == 'continue' else MODE, 'quality_certified': False}
    app = create_app(runtime, data, contracts_root=C, release=binding,
                     provider=Haiku(C, runtime / 'provider', False, backend='source-only', trust_zone='internal'),
                     implementation='legal-agent-unified-v6', legal_agent_profile=profile, legal_agent_transport=transport,
                     workspace_root=ROOT, runtime_root=runtime,
                     memory_identity=lambda request: {'user_id': 'adr1460', 'team_id': 'risk_team', 'document_ids': sorted(allowed)})
    client = TestClient(app, raise_server_exceptions=False); client.__enter__()
    assert client.get('/health').status_code == 200
    loaded = {n: str(Path(m.__file__).resolve()) for n, m in sys.modules.items()
              if n.split('.')[0] in ('semantic_runtime', 'workflow') and getattr(m, '__file__', None)}
    assert all(Path(p).is_relative_to(C) for p in loaded.values()), 'product module outside the frozen candidate'
    guard.rebase()
    body = {'question': case['question'], 'document_ids': sorted(allowed), 'session_id': 'adr1460-' + ('live' if RESUME or MODE == 'continue' else base.name if MODE == 'fresh' else MODE),
            'request_id': base.name if MODE == 'continue' else 'initial',
            'use_llm': True, 'team_id': 'risk_team'}
    put(base / 'binding.json', {'code_root': str(C.relative_to(ROOT)), 'candidate_files': len(candidate['files']), 'product_modules_loaded': len(loaded),
                                'source': {k: source_manifest[k] for k in ('generation_id', 'store_sha256', 'export_allowed')},
                                'scope': sorted(allowed), 'supervisor_mode': profile['candidate_navigation']['supervisor_mode'],
                                'state_storage': 'isolated local SQLite under this run', 'mode': MODE})
    if MODE == 'preflight':
        put(base / 'result.json', {'ready': True, 'model_calls': 0, 'http_health': 200})
        print('PREFLIGHT_READY', flush=True)
    else:
        if RESUME:
            from semantic_runtime.legal_agent import journal_storage
            import re
            folders = [p for p in (runtime / 'workflows').iterdir() if re.fullmatch('[0-9a-f]{32}', p.name)]
            assert len(folders) == 1, folders
            with journal_storage.connect('file:' + str(folders[0] / 'journal.sqlite') + '?mode=ro', uri=True) as db:
                status, revision, saved = db.execute('SELECT status,revision,result_json FROM workflow_state WHERE singleton=1').fetchone()
            put(base / 'resume-target.json', {'run_id': folders[0].name, 'status': status, 'revision': revision, 'had_result': saved is not None})
            assert status == 'running' and saved is None, 'saved run is not an interrupted running run'
            resume = {'run_id': folders[0].name, 'session_id': body['session_id'], 'team_id': 'risk_team', 'expected_revision': revision}
            put(base / 'request.json', {'resume': resume, 'original_request': body}); begin = time.monotonic()
            response = client.post('/v1/workflows/resume', json=resume); elapsed = time.monotonic() - begin
        else:
            if MODE == 'continue':
                body['question'] = '문서 대사: 계속'
            put(base / 'request.json', body); begin = time.monotonic()
            response = client.post('/v1/rag/ask', json=deepcopy(body)); elapsed = time.monotonic() - begin
        value = response.json(); gz(base / 'response.json.gz', {'http_status': response.status_code, 'body': value})
        answer = value.get('answer') or {}
        text = answer.get('text', '') if isinstance(answer, dict) else str(answer)
        (base / 'answer.txt').write_text(text, 'utf-8')
        from collections import Counter
        stage_counts = Counter(('child' if g['stage'].startswith('source-') else g['stage']) for g in generations)
        result = {'case_id': case['id'], 'mode': MODE, 'http_status': response.status_code, 'status': value.get('status'), 'run_id': value.get('run_id'),
                  'workflow_id': value.get('workflow_id'), 'response_schema': value.get('response_schema'), 'request_seconds': round(elapsed, 3),
                  'physical_calls': len(calls) if SENDS else 0, 'unknown': sum(c['status'] == 'unknown' for c in calls),
                  'generations': len(generations), 'stage_counts': dict(stage_counts),
                  'rejected_generations': [g for g in generations if g.get('status') == 'rejected'],
                  'document_compare': value.get('document_compare'), 'stop_code': value.get('stop_code'),
                  'unresolved': value.get('unresolved'), 'answer_chars': len(text), 'error': value.get('message') or value.get('detail')}
        put(base / 'result.json', result)
        if response.status_code == 200:
            before = len(generations)
            again = client.post('/v1/rag/ask', json=deepcopy(body))
            result['duplicate'] = {'http_status': again.status_code, 'same_answer': again.json().get('answer') == value.get('answer'),
                                   'extra_generations': len(generations) - before, 'extra_physical_calls': (len(calls) - result['physical_calls']) if SENDS else 0}
            put(base / 'result.json', result)
        print('RESULT', json.dumps({k: result[k] for k in ('http_status', 'status', 'request_seconds', 'physical_calls', 'unknown', 'generations', 'stage_counts', 'document_compare')}, ensure_ascii=False), flush=True)
except Exception as error:
    put(base / 'runner-failure.json', {'type': type(error).__name__, 'error': str(error), 'traceback': traceback.format_exc(), 'model_calls': len(calls)})
    print('RUNNER_FAILURE', type(error).__name__, str(error)[:300], flush=True)
    raise
finally:
    if client is not None:
        client.__exit__(None, None, None)
    if app is not None:
        app.state.pipeline.store.close()
    if SENDS:
        guard.done.set(); guard.thread.join(timeout=2)
    put(base / 'resource-final.json', {'peak_rss_KiB': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                                        'candidate_unchanged': all(sha(C / n) == h for n, h in candidate['files'].items())})
