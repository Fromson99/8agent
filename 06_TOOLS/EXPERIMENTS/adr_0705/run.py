"""One frozen request, phase timings and local function profiling; no gold input."""
from pathlib import Path
import argparse, cProfile, functools, hashlib, importlib, json, os, pstats, sys, threading, time, traceback

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0705-cm-max-call-bottleneck-probe'
D = A / 'artifacts/design'
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def put(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

parser = argparse.ArgumentParser()
parser.add_argument('--setup-only', action='store_true')
args = parser.parse_args()
f = read(D / 'freeze.json')
for name, expected in f['files'].items():
    assert sha(R/name) == expected, name
code = R / f['code_root']
out = A / 'artifacts' / ('setup-check' if args.setup_only else 'run-001')
out.mkdir(parents=True, exist_ok=False)
assert not any(os.environ.get(k) for k in ('GENOS_GENERATION', 'GENOS_DATA_ROOT', 'GENOS_STATE_DIR', 'LEGAL_AGENT_PROFILE'))
assert not any(os.environ.get(k) for k in ('GENOS_RAG_MAX_MODEL_ATTEMPTS','GENOS_RAG_MAX_TOOL_ACTIONS','GENOS_RAG_WALL_SECONDS','GENOS_RAG_SEARCH_ROUNDS','GENOS_RAG_ASSESSMENT_REENTRY_LIMIT'))
sys.dont_write_bytecode = True
sys.path.insert(0, str(code/'02_BACKEND'))
from lawrag.research.experiment_client import ExperimentClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport, provider_request
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.workflow_tiers_policy import profile as validate_profile
from semantic_runtime.stage_runner import StageRunner
from semantic_runtime.pipeline import Pipeline
from fastapi.testclient import TestClient

clock0 = time.perf_counter()
spans = []
local = threading.local()
def measure(name, fn):
    @functools.wraps(fn)
    def wrapped(*a, **kw):
        stack = getattr(local, 'stack', [])
        local.stack = stack
        row = {'id': len(spans), 'name': name, 'thread': threading.get_ident(),
               'parent': stack[-1] if stack else None, 'start': time.perf_counter()-clock0}
        if name.endswith('.completion_stage') and len(a)>1: row['stage'] = a[1]
        spans.append(row)
        stack.append(row['id'])
        try: return fn(*a, **kw)
        except BaseException as exc:
            row['error_type'] = type(exc).__name__
            raise
        finally:
            row['seconds'] = time.perf_counter()-clock0-row['start']
            stack.pop()
    return wrapped

targets = {
    'legal_agent.case_repository': {'CaseRepository': ['context','direct_request','resolve','validate_response']},
    'legal_agent.corrected_memory': {'Memory': ['context','resolve','_execute','stage_committed']},
    'legal_agent.memory_binding': {'RuntimeModel': ['ensure','invoke']},
    'legal_agent.completion_execution': {'CompletionExecution': ['completion_stage']},
    'legal_agent.law_navigation': {'Investigation': ['build_view','execute_tool','request_decision','batch_pages','run']},
    'legal_agent.law_candidates': {None: ['structured_discovery','discover','prepare']},
    'legal_agent.unit_reading': {None: ['acquire_batch','read','ensure_context']},
    'runtime_cache': {'ProcessCache': ['get_or_build']},
    'stage_runner': {'StageRunner': ['verify_profile']},
}
for modname, classes in targets.items():
    module = importlib.import_module('semantic_runtime.'+modname)
    for classname, methods in classes.items():
        owner = getattr(module, classname) if classname else module
        for method in methods:
            assert hasattr(owner, method), (modname, classname, method)
            name = modname+'.'+(classname+'.' if classname else '')+method
            setattr(owner, method, measure(name, getattr(owner, method)))

original_run = Pipeline.run
@functools.wraps(original_run)
def profiled_run(*a, **kw):
    profile = cProfile.Profile()
    profile.enable()
    try: return original_run(*a, **kw)
    finally:
        profile.disable()
        profile.dump_stats(str(out/'pipeline.prof'))
        stats = pstats.Stats(profile)
        rows = [{'file': file, 'line': line, 'function': function, 'primitive_calls': cc,
                 'calls': nc, 'self_seconds': tt, 'cumulative_seconds': ct}
                for (file,line,function),(cc,nc,tt,ct,callers) in stats.stats.items()]
        put(out/'function-profile.json', sorted(rows,key=lambda x:x['cumulative_seconds'],reverse=True))
Pipeline.run = measure('pipeline.Pipeline.run', profiled_run)

client = ExperimentClient(R, out/'provider', max_calls=40, max_output_tokens=6400, max_repairs=0)
class Transport(LocalGemmaTransport):
    def send_once(self, *, body, ticket):
        view = json.loads(body['messages'][1]['content'])['view']
        phase = view.get('source_stage', view['phase'])
        number = client.calls+1
        print('MODEL_START', number, phase, flush=True)
        call = measure('model.'+str(number)+'.'+phase, client.chat_completions)
        result = call(provider_request(body), phase='product-'+str(number)+'-'+phase,
                      timeout_seconds=ticket['remaining_seconds'])
        raw = result['body_json']
        if raw.get('provider') != 'Parasail' or raw.get('model') != self.binding['model']:
            raise ContractError('provider binding')
        print('MODEL_DONE', number, client.usage[-1]['seconds'], flush=True)
        return result

transport = Transport(code, R)
policy = read(code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
policy.update(model_binding=transport.binding, max_output_tokens=transport.policy['max_output_tokens'])
policy = validate_profile(policy, require_model=True)
assert policy['max_output_tokens'] == 6400 and policy['max_model_attempts'] == 40
case = read(D/'dataset.json')['cases'][0]
principal = {'user_id':'adr0705-diagnostic', 'team_id':'public-laws', 'authenticated':True,
             'document_ids':list(transport.public_scope)}
body = {'question':case['question'], 'document_ids':list(transport.public_scope), 'public_question':True,
        'use_llm':True, 'session_id':'adr0705-cm018', 'request_id':'adr0705-run001-cm018'}
put(out/'request.json', body)
put(out/'profile.json', policy)
start = time.perf_counter()
row = {'case_id':'cm-018', 'arm':'measured-main48', 'field_execution':False, 'code_root':str(code),
       'source_generation':f['source_generation'], 'active_pointer_before':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
       'profiling_enabled':True, 'profile_sha256':hashlib.sha256(json.dumps(policy,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
try:
    app = create_app(out, R/f['source_generation'], contracts_root=code, workspace_root=R,
                     provider=object(), implementation='legal-agent-unified-v6', legal_agent_profile=policy,
                     legal_agent_transport=transport, runtime_root=out/'runtime', memory_identity=lambda _:principal)
    StageRunner(app.state.pipeline).verify_profile()
    with TestClient(app) as api:
        ready = time.perf_counter()
        row['app_setup_seconds'] = ready-start
        if args.setup_only:
            row.update(setup_only=True,http_status=200)
        else:
            row['request_start'] = ready-clock0
            print('ASK_START cm-018', flush=True)
            response = api.post('/v1/rag/ask',json=body)
            row.update(http_status=response.status_code, output=response.json(), request_seconds=time.perf_counter()-ready)
except BaseException as exc:
    row.update(http_status=500, error_type=type(exc).__name__, error=str(exc), elapsed_seconds=time.perf_counter()-start)
    (out/'error.txt').write_text(traceback.format_exc())
finally:
    row.update(total_seconds=time.perf_counter()-start, model_calls=client.calls, usage=client.usage,
               active_pointer_after=sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'))
    put(out/'timing-spans.json', spans)
    put(out/'result.json', row)
    print('RESULT',json.dumps({k:v for k,v in row.items() if k not in ('output','usage')},ensure_ascii=False),flush=True)
