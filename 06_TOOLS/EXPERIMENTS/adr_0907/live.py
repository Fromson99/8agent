"""One unchanged MAIN87 service request, audited through the common model client."""
from pathlib import Path
import gzip, copy, jsonschema, gc, ctypes
import asyncio, hashlib, importlib, importlib.util, json, os, resource, sys, time, traceback

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0907-closed-reference-charter-trace'
D = A / 'artifacts/design'
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def put(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

case = next(c for c in read(D/'cases.json') if c['id'] == sys.argv[1])
f = read(D/'freeze.json')
for name, expected in f['files'].items():
    assert sha(R/name) == expected, name
O = A/'artifacts/run-001'/case['id']
O.mkdir(parents=True, exist_ok=False)
sys.dont_write_bytecode = True
sys.path[:0] = [str(R), str(R/'02_BACKEND')]
os.environ.update(GENOS_RESIDENT_DATA='off', GENOS_AUTO_WARMUP='0', MALLOC_ARENA_MAX='1',MALLOC_TRIM_THRESHOLD_='65536',MALLOC_MMAP_THRESHOLD_='131072',AD_WORKER_ENABLED='0', TEAM_ID='risk_team', LAWRAG_WORKSPACE_ROOT=str(R), GENOS_RUNTIME_DIR=str(O/'runtime'))
for name in ('GENOS_LEGAL_AGENT_MAX_MODEL_ATTEMPTS', 'GENOS_LEGAL_AGENT_WALL_SECONDS'):
    if os.environ.get(name):
        raise RuntimeError('Unexpected budget override: '+name)

started = time.monotonic()
result = {'case_id': case['id'], 'environment': 'WSL local qualified candidate service.py with injected application and ASGI dispatch; active pointer unchanged',
          'in_sample': True, 'quality_certified': False, 'app_injected': True}
app = None
client = None
exit_status = 1
try:
    print(json.dumps({'case': case['id'], 'stage': 'service_bootstrap'}), flush=True)
    release=read(D/'baseline.json')['manifest']
    C=R/release['code_root']
    pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
    assert pointer==read(D/'baseline.json')['pointer']
    assert release['files']==f['serving_files']
    assert all(sha(C/n)==h for n,h in f['serving_files'].items())
    sys.path[:0]=[str(C/'02_BACKEND'),str(C)]
    from semantic_runtime.app import create_app
    from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
    transport=LocalGemmaTransport(C,R)
    native_profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
    native_profile['model_binding']=transport.binding
    app=create_app(R,R/release['data_path'],contracts_root=C,workspace_root=R,provider=object(),
        implementation='legal-agent-unified-v6',runtime_root=O/'runtime',
        legal_agent_profile=native_profile,legal_agent_transport=transport,
        release={'mode':'local-release','release_id':'qualified-reference-observation'})
    spec=importlib.util.spec_from_file_location('qualified_service_entry',C/'service.py')
    actual=importlib.util.module_from_spec(spec);spec.loader.exec_module(actual)
    actual._APP=app;actual._BINDING={'mode':'local-release','generation':87,'candidate_code_root':str(C)}
    assert Path(app.state.pipeline.store.path).resolve()==(R/release['data_path']).resolve()
    assert Path(sys.modules[type(app.state.pipeline).__module__].__file__).resolve().is_relative_to(C)
    put(O/'health.json',asyncio.run(actual.service({}, {'API_TYPE':'HEALTH'})))
    t = app.state.pipeline.term_agent.transport
    assert Path(t.code_root).resolve() == C.resolve()
    pkg = type(t).__module__.rsplit('.', 1)[0]
    local = importlib.import_module(pkg+'.local_gemma')
    errors = importlib.import_module(pkg+'.errors')
    structured_content = importlib.import_module(pkg+'.model_contract').structured_content
    import lawrag
    if str(R/'02_BACKEND/lawrag') not in lawrag.__path__:
        lawrag.__path__.append(str(R/'02_BACKEND/lawrag'))
    from lawrag.research.experiment_client import ExperimentClient, ExperimentFormatError, ExperimentProviderError, ExperimentTransportError
    profile = app.state.pipeline.term_agent.profile
    assert profile['max_model_attempts'] == 40 and profile['wall_seconds'] == 1800
    client = ExperimentClient(R, O/'raw', max_calls=40, max_output_tokens=profile['max_output_tokens'], max_repairs=0)
    put(O/'binding.json', {'pointer': pointer, 'service_module': str(Path(actual.__file__).relative_to(R)),
        'service_sha256': sha(Path(actual.__file__)), 'pipeline_module': str(Path(sys.modules[type(app.state.pipeline).__module__].__file__).relative_to(R)),
        'transport_module': type(t).__module__, 'profile': profile, 'code_root': release['code_root'],
        'data_path': release['data_path'], 'data_manifest_sha256': sha(R/release['data_path']/'manifest.json'),
        'runtime_root': str(O/'runtime'), 'app_injected': True, 'transport_instrumented': 'send_once only via ExperimentClient; authorization and gateway unchanged', 'search_selection_fingerprint':app.state.pipeline.store.selection.fingerprint, 'workflow_manifest':read(C/'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json')})

    def gz(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, 'wt', encoding='utf8') as out:
            json.dump(value, out, ensure_ascii=False, separators=(',', ':'))
    def size(value):
        return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode())
    generations=[]; calls=[]; active=[]
    gateway=importlib.import_module(pkg+'.gateway')
    original_generate=gateway.ModelGateway.generate
    def generate(self, phase, view, schema_name, **kwargs):
        number=len(generations)+1
        rec={'number':number,'phase':phase,'stage':view.get('source_stage',phase),'schema_name':schema_name}
        rec['input_card_counts']={k:len(view[k]) for k in ('sources','basis','exact_evidence','groups','laws','issues','evidence_options') if isinstance(view.get(k),(list,dict))}
        rec['source_labels']=[{k:x.get(k) for k in ('source_id','document_name','heading')} for x in view.get('sources',[]) if isinstance(x,dict)] if isinstance(view.get('sources'),list) else []
        generation_started=time.monotonic()
        generations.append(rec);active.append(rec)
        schema=self.protocol.schema(schema_name)
        gz(O/'canonical'/f'{number:03d}.json.gz', {'view':view,'schema':schema,'phase':phase})
        try:
            jsonschema.Draft202012Validator.check_schema(schema)
            value=original_generate(self,phase,view,schema_name,**kwargs)
            rec['decision']={k:value[k] for k in ('next_action','targets','reason','sufficiency_reason','disposition','needs_more') if k in value}
            rec['reference_decisions']=value.get('decisions',[])
            rec['accepted']=True;gz(O/'canonical'/f'{number:03d}-output.json.gz',value)
            return value
        except Exception as exc:
            rec.update(accepted=False,error_type=type(exc).__name__,error=str(exc));raise
        finally:
            rec['seconds']=time.monotonic()-generation_started
            active.pop();put(O/'generations.json',generations)
            gc.collect();ctypes.CDLL(None).malloc_trim(0)
    gateway.ModelGateway.generate=generate

    def find_stage(value):
        if isinstance(value, dict):
            if value.get('source_stage'):
                return value['source_stage']
            for child in value.values():
                found = find_stage(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = find_stage(child)
                if found:
                    return found
        return None

    def send_once(*, body, ticket):
        if body.get('model') != t.binding['model'] or body.get('stream') is not False:
            raise errors.ContractError('Request differs from selected model binding')
        phase = 'native-rag'
        for message in body.get('messages', []):
            try:
                phase = find_stage(json.loads(message.get('content', ''))) or phase
            except (ValueError, TypeError):
                pass
        number=client.calls+1
        send_started=time.monotonic()
        provider_body=local.provider_request(body)
        schema=provider_body.get('response_format',{}).get('json_schema',{}).get('schema',{})
        jsonschema.Draft202012Validator.check_schema(schema)
        rec={'call':number,'phase':phase,'generation':active[-1]['number'] if active else None,'schema_bytes':size(schema),'request_bytes':size(body),'schemas_valid':True}
        calls.append(rec);put(O/'calls.json',calls)
        gz(O/'wire'/f'{number:03d}.json.gz',body)
        print(json.dumps({'case':case['id'],'dispatch':number,'phase':phase,'schema_bytes':rec['schema_bytes']}),flush=True)
        try:
            raw = client.chat_completions(provider_body, phase=phase, timeout_seconds=min(180, ticket['remaining_seconds']))
        except ExperimentFormatError as exc:
            if exc.response:
                try:
                    structured_content(exc.response['body_json'], require_complete=True)
                except Exception as error:
                    error.response = exc.response
                    raise
            error = errors.ProposalError('local Qwen3.8 returned an incomplete response')
            error.response = exc.response
            raise error from exc
        except ExperimentProviderError as exc:
            status = (exc.response or {}).get('status_code', 0)
            raise errors.TransportError('experiment provider failure', retryable=status == 429, unknown=status >= 500, response=exc.response) from exc
        except ExperimentTransportError as exc:
            raise errors.TransportError(str(exc), retryable=exc.retryable, unknown=exc.unknown) from exc
        if raw['body_json'].get('model') != t.binding['model'] or raw['body_json'].get('provider') != 'Parasail':
            raise errors.ContractError('actual model/provider mismatch')
        rec.update(http_status=raw['status_code'],output_bytes=size(raw['body_json']),seconds=time.monotonic()-send_started)
        put(O/'calls.json',calls)
        print(json.dumps({'completed_call':number,'phase':phase}),flush=True)
        raw['acceptance'] = 'ACCEPTED'
        return raw

    t.send_once = send_once
    request = {'API_TYPE': case['api_type'], 'question': case['question'], 'use_llm': True,
               'session_id': 'adr0907-'+case['id'], 'request_id': 'adr0907-'+case['id']}
    if case.get('workflow_id'):
        request['workflow_id'] = case['workflow_id']
    if case['api_type']=='RAG_ASK':
        request={'API_TYPE':'RAG_ASK','json':{'question':case['question'],'document_ids':sorted(t.public_scope),'public_question':True,'use_llm':True}}
    put(O/'request.json', request)
    request_started=time.monotonic()
    response = asyncio.run(actual.service({}, request))
    result['request_seconds']=time.monotonic()-request_started
    put(O/'response.json', response)
    value = response.get('body', {})
    result.update(http_status=response.get('status'), status=value.get('status'), run_id=value.get('run_id'), model_calls_before_consumer_checks=client.calls)
    if case['api_type']=='WORKFLOW_RUN' and value.get('run_id'):
        saved = asyncio.run(actual.service({}, {'API_TYPE': 'WORKFLOW_STATUS', 'run_id': value['run_id'], 'session_id': value['session_id']}))
        put(O/'status-response.json', saved)
        result['checks'] = {'status_answer_identical': saved.get('body', {}).get('answer') == value.get('answer')}
        if value.get('status') in ('completed','partial','failed'):
            duplicate = asyncio.run(actual.service({}, request))
            put(O/'duplicate-response.json', duplicate)
            result['checks'].update(duplicate_answer_identical=duplicate.get('body', {}).get('answer') == value.get('answer'),
                                    duplicate_run_identical=duplicate.get('body', {}).get('run_id') == value['run_id'])
        else:
            result['duplicate_skipped'] = 'Not completed: no accidental new attempt or resumed model budget.'
        result['checks']['consumer_no_model_calls'] = client.calls == result['model_calls_before_consumer_checks']
        result['journal_root'] = str((app.state.workflow_runtime.root/value['run_id']).relative_to(R))
    result['consumer_check_scope']='One RAG request only; response and native journal retained. No WORKFLOW_STATUS or duplicate request.'
    result['active_pointer_unchanged']=pointer==read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
    exit_status = 0
except BaseException as exc:
    result.update(error=type(exc).__name__, message=str(exc))
    (O/'error.txt').write_text(traceback.format_exc())
finally:
    result.update(model_calls=client.calls if client else 0, usage=client.usage if client else [],
                  elapsed_seconds=time.monotonic()-started, peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    put(O/'result.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'usage'}, ensure_ascii=False), flush=True)
    if app:
        app.state.pipeline.store.close()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_status)
