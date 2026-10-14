"""Unmodified selected local service; fresh state and exact audited requests."""
from pathlib import Path
import asyncio, hashlib, importlib, importlib.util, json, os, sys, time, traceback

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0686-risk-cm-public-scope-local-probe'
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT), str(ROOT / '02_BACKEND')]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

design = read(ADR / 'artifacts/design/frozen.json')
run = sys.argv[1]
assert run in design['runs']
case = next(c for c in design['cases'] if c['run_id'] == run)
for path, expected in design['bindings'].items():
    assert sha(ROOT / path) == expected, path
directory = ADR / 'artifacts' / run
directory.mkdir(exist_ok=False)
for name in ('GENOS_GENERATION', 'GENOS_DATA_ROOT', 'GENOS_LLM_KEY',
             'GENOS_LLM_URL', 'GENOS_LLM_SERVING_ID', 'GENOS_RAG_IMPLEMENTATION'):
    assert not os.environ.get(name), 'Local probe requires no GENOS environment binding'
os.environ['GENOS_RUNTIME_DIR'] = str(directory / 'runtime')
os.environ['AD_WORKER_ENABLED'] = '0'
os.environ['GENOS_SYSTEM_LOG_ENABLED'] = '0'
service = importlib.import_module('service.service')
app = service.application()
package = app.state.pipeline.__class__.__module__.rsplit('.', 1)[0]
module = importlib.import_module(package + '.legal_agent.local_gemma')
assert str(Path(module.__file__).resolve()).startswith(str(ROOT / design['release']['code_root']))
spec = importlib.util.spec_from_file_location('adr0686_audited_client', ROOT / '02_BACKEND/lawrag/research/experiment_client.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
client = audit.ExperimentClient(ROOT, directory / 'provider', max_calls=40,
                               max_output_tokens=6400, max_repairs=0)
transport = app.state.pipeline.term_agent.transport
assert transport.policy['model'] == design['model']

def send_once(*, body, ticket):
    print('MODEL_START', run, client.calls + 1, flush=True)
    result = client.chat_completions(module.provider_request(body),
        phase='product-' + str(client.calls + 1), timeout_seconds=ticket['remaining_seconds'])
    raw = result['body_json']
    assert raw.get('provider') == 'Parasail' and raw.get('model') == transport.binding['model']
    print('MODEL_DONE', run, client.calls, client.usage[-1]['seconds'], flush=True)
    return result

# Audit adapter preserves the service's prompt, schema adaptation, model,
# settings and output contract. It supplies no alternate product context.
transport.send_once = send_once
body = {'question': case['question'], 'document_ids': list(transport.public_scope),
        'public_question': True, 'use_llm': True}
put(directory / 'request.json', body)
put(directory / 'profile.json', app.state.pipeline.term_agent.profile)
start = time.monotonic()
row = {'run_id': run, 'arm': 'baseline', 'case_id': case['case_id'],
       'question': body['question'], 'entrypoint': 'service.service',
       'environment': 'WSL local selected MAIN45; fresh isolated runtime',
       'model': client.model, 'public_scope_count': len(transport.public_scope),
       'memory_seed': 'empty', 'genos_execution': False,
       'pointer_before': sha(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')}

async def execute():
    health = await service.service({}, {'API_TYPE': 'HEALTH'})
    assert health['status'] == 200
    binding = health['body']['release']
    assert binding['generation'] == 45 and binding['release_id'] == design['pointer']['release_id']
    put(directory / 'health.json', health)
    row['execution_binding'] = binding
    print('ASK_START', run, flush=True)
    response = await service.service({}, {'API_TYPE': 'RAG_ASK', 'json': body})
    put(directory / 'response.json', response)
    row['http_status'] = response['status']
    row['output'] = response.get('body')

try:
    asyncio.run(execute())
except Exception as exc:
    row.update(http_status=500, exception_type=type(exc).__name__, exception=str(exc))
    (directory / 'error.txt').write_text(traceback.format_exc())
finally:
    row.update(seconds=time.monotonic() - start, model_calls=client.calls, usage=client.usage,
               pointer_after=sha(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'))
    put(directory / 'result.json', row)
    print('RESULT', json.dumps({k: v for k, v in row.items() if k not in ('output', 'usage', 'execution_binding')}, ensure_ascii=False), flush=True)
