"""One preregistered request through the active local service, isolated journals.

The audited client receives the native transport body unchanged. It only records
the physical request/response; model, provider and reader behavior are preserved.
"""
from pathlib import Path
import hashlib
import importlib
import json
import os
import sqlite3
import sys
import time
import traceback
import types

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0658-internal-accounting-manager-local-probe'
DESIGN = ADR / 'artifacts/design'
RUN = ADR / 'artifacts/run-001'
sys.dont_write_bytecode = True


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    frozen = json.loads((DESIGN / 'freeze.json').read_text())
    for name, expected in frozen['files'].items():
        assert sha(ROOT / name) == expected, name
    manifest = json.loads((ADR / '실험/manifest.json').read_text())
    assert manifest['design']['criteria_frozen_before_run'] is True
    RUN.mkdir(exist_ok=False)
    os.environ['GENOS_RUNTIME_DIR'] = str(RUN / 'runtime')
    os.environ['AD_WORKER_ENABLED'] = '0'
    for key in ('GENOS_GENERATION', 'GENOS_DATA_ROOT', 'GENOS_RAG_IMPLEMENTATION',
                'LEGAL_AGENT_PROFILE', 'LEGAL_AGENT_PROFILE_SHA256', 'GENOS_STATE_DIR'):
        os.environ.pop(key, None)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / '02_BACKEND'))
    from lawrag.research.experiment_client import ExperimentClient
    import service
    from fastapi.testclient import TestClient
    service.obs.configure()
    app = service.application()
    pipeline = app.state.pipeline
    assert service._BINDING['release_id'] == frozen['release_id']
    package = pipeline.__class__.__module__.rsplit('.', 1)[0]
    errors = importlib.import_module(package + '.legal_agent.errors')
    progress = importlib.import_module(package + '.progress')
    transport = pipeline.term_agent.transport
    client = ExperimentClient(ROOT, RUN / 'provider', max_calls=40,
                              max_output_tokens=6400, max_repairs=0)
    assert client.policy_hash == transport.policy_hash
    assert pipeline.term_agent.profile['max_model_attempts'] == 40
    put(RUN / 'profile.json', pipeline.term_agent.profile)
    put(RUN / 'service-binding.json', service._BINDING)

    def send_once(self, *, body, ticket):
        assert body['model'] == self.binding['model'] and body['stream'] is False
        number = client.calls + 1
        print(json.dumps({'event': 'physical-model-start', 'call': number,
                          'request_bytes': len(json.dumps(body, ensure_ascii=False).encode())}), flush=True)
        response = client.chat_completions(body, phase='product-' + str(number),
                                           timeout_seconds=ticket['remaining_seconds'])
        raw = response['body_json']
        if raw.get('provider') != 'Parasail' or raw.get('model') != self.binding['model']:
            raise errors.ContractError('model/provider binding mismatch')
        choices = raw.get('choices', [])
        if len(choices) != 1 or choices[0].get('finish_reason') != 'stop':
            error = errors.ProposalError('incomplete response')
            error.response = response
            raise error
        if (raw.get('usage', {}).get('completion_tokens_details') or {}).get('reasoning_tokens') or choices[0]['message'].get('reasoning'):
            raise errors.ContractError('reasoning unexpectedly enabled')
        print(json.dumps({'event': 'physical-model-finish', **client.usage[-1]}, ensure_ascii=False), flush=True)
        return response

    transport.send_once = types.MethodType(send_once, transport)
    events = []
    def event_sink(event):
        events.append(event)
        with (RUN / 'progress.jsonl').open('a') as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + '\n')
        if event.get('count') is not None or event.get('kind') == 'selected':
            print(json.dumps({'event': 'progress', 'kind': event.get('kind'),
                              'label': event.get('label'), 'count': event.get('count')}, ensure_ascii=False), flush=True)

    body = json.loads((DESIGN / 'request.json').read_text())
    put(RUN / 'request.json', body)
    started = time.monotonic()
    with TestClient(app) as api:
        put(RUN / 'health.json', api.get('/health').json())
        with service.obs.context(request_id='adr0658-run001'), progress.capture('adr0658-run001', RUN / 'runtime', event_sink):
            try:
                response = api.post('/v1/rag/ask', json=body)
                output = response.json()
                status = response.status_code
            except Exception as exc:
                output = {'error_type': type(exc).__name__, 'error': str(exc)}
                status = 500
                (RUN / 'error.txt').write_text(traceback.format_exc())
        result = {'case_id': 'accounting-manager-001', 'arm': 'baseline',
                  'http_status': status, 'request': body, 'response': output,
                  'seconds': time.monotonic() - started, 'physical_model_calls': client.calls,
                  'usage': client.usage, 'progress_events': len(events)}
        put(RUN / 'result.json', result)
    assert sha(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') == frozen['files']['01_DATA/ACTIVE/local/ACTIVE_RELEASE.json']
    print(json.dumps({k: result[k] for k in ('http_status', 'seconds', 'physical_model_calls', 'progress_events')}, ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
