"""Actual unified v6 API experiment, exact baseline forks, no product gold."""
import argparse
import json
import logging
import shutil
import sqlite3
import sys
import time
import traceback
from common import ROOT, ADR, DESIGN, RUN, read, put, sha, verify, verify_freeze, check_payload, candidate

sys.dont_write_bytecode = True

def database(path):
    if not path.is_file(): return {}
    out = {}
    with sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        for table in ('goal', 'event', 'head', 'node', 'route', 'knowledge', 'wiki', 'judgment_ref', 'request'):
            out[table] = []
            for row in db.execute('SELECT * FROM ' + table):
                r = dict(row)
                for k in ('state', 'command', 'before_state', 'after_state', 'payload', 'ref', 'response'):
                    if isinstance(r.get(k), str):
                        try: r[k] = json.loads(r[k])
                        except ValueError: pass
                out[table].append(r)
    return out

def main(case_id, arm, preflight):
    logging.getLogger('genos').setLevel(logging.WARNING)
    if not preflight: verify_freeze()
    cp, c, rev, code = candidate(arm)
    sys.path.insert(0, str(code / '02_BACKEND'))
    from semantic_runtime.app import create_app
    from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
    from semantic_runtime.legal_agent.errors import TransportError, ContractError, ProposalError
    from lawrag.research.experiment_client import ExperimentClient, ExperimentProviderError
    from fastapi.testclient import TestClient
    assert Path(create_app.__code__.co_filename).is_relative_to(code)
    binding = verify(all_files=preflight); allowed = set(binding['scope_document_ids'])
    case = next(x for x in read(DESIGN / 'inputs.json') if x['case_id'] == case_id)
    directory = ADR / 'artifacts/preflight' / case_id / arm if preflight else RUN / case_id / arm
    assert not directory.exists(), 'One frozen run only; no hidden rerun'
    directory.mkdir(parents=True)
    client = ExperimentClient(ROOT, directory / 'provider', max_calls=160, max_output_tokens=6400, max_repairs=0)
    class AuditedTransport(LocalGemmaTransport):
        def send_once(self, *, body, ticket):
            assert not preflight, 'No model calls allowed in preflight'
            verify()
            for message in body['messages']:
                if message['role'] == 'user':
                    try: check_payload(json.loads(message['content']), allowed)
                    except json.JSONDecodeError: pass
            try:
                envelope = client.chat_completions(body, phase='physical-' + str(client.calls + 1),
                                                    timeout_seconds=ticket['remaining_seconds'])
            except ExperimentProviderError as exc:
                raise TransportError(str(exc), retryable=False, response=exc.response) from exc
            except Exception as exc:
                raise TransportError(type(exc).__name__, retryable=False, unknown=True) from exc
            data = envelope['body_json']
            if data.get('provider') != 'Parasail' or data.get('model') != self.binding['model']:
                raise ContractError('Pinned provider/model mismatch')
            choices = data.get('choices') or []
            if len(choices) != 1 or choices[0].get('finish_reason') != 'stop':
                exc = ProposalError('Incomplete response'); exc.response = envelope; raise exc
            if (((data.get('usage') or {}).get('completion_tokens_details') or {}).get('reasoning_tokens')
                    or choices[0].get('message', {}).get('reasoning')):
                raise ContractError('Reasoning unexpectedly enabled')
            return envelope
    transport = AuditedTransport(code, ROOT)
    profile = read(code / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
    profile['model_binding'] = transport.binding
    principal = {'user_id': 'CM_EXPERIMENT_USER', 'team_id': 'cm_public', 'document_ids': sorted(allowed)}
    runtime = directory / 'runtime'
    if not preflight and arm != 'baseline':
        origin = RUN / case_id / 'baseline/runtime'
        assert (RUN / case_id / 'baseline/products.json').is_file()
        shutil.copytree(origin, runtime)
        hashes = {str(f.relative_to(origin)): sha(f) for f in origin.rglob('*') if f.is_file() and not f.name.endswith(('-wal', '-shm'))}
        assert all(sha(runtime / p) == h for p, h in hashes.items())
        put(directory / 'fork-receipt.json', {'origin': str(origin.relative_to(ROOT)), 'sha256': hashes,
            'immutable_origin_journals_preserved': True, 'baseline_product_sha256': sha(RUN / case_id / 'baseline/products.json')})
    app = create_app(directory, ROOT / binding['generation'], contracts_root=code, provider=object(),
        implementation='legal-agent-unified-v6', legal_agent_profile=profile, legal_agent_transport=transport,
        runtime_root=runtime, memory_identity=lambda request: principal)
    if preflight:
        with TestClient(app) as api: health = api.get('/health').json()
        put(directory / 'result.json', {'ready': True, 'health': health, 'model_calls': client.calls,
            'import_root': str(code.relative_to(ROOT)), 'principal_public_docs': len(allowed)})
        print('Preflight ready ' + case_id + '/' + arm, flush=True); return
    products = []
    turns = [case['question']] if arm == 'baseline' else case['control_turns'] if arm == 'unguided' else case['guides']
    def post(api, text, turn, session=None):
        body = {'question': text, 'memory': True, 'public_question': True,
                'session_id': session or case_id, 'request_id': arm + '-' + str(turn)}
        call_start = client.calls; start = time.monotonic()
        try:
            response = api.post('/v1/rag/ask', json=body); output = response.json()
            status = response.status_code
        except Exception as exc:
            output = {'status': 'ERROR', 'error_type': type(exc).__name__, 'error': str(exc)}; status = 500
            (directory / ('exception-' + str(turn) + '.txt')).write_text(traceback.format_exc())
        row = {'case_id': case_id, 'arm': arm, 'turn': turn, 'input': body, 'http_status': status,
               'output': output, 'seconds': time.monotonic() - start,
               'provider_attempt_start': call_start + 1, 'provider_attempt_end': client.calls,
               'db': database(runtime / 'case-memory/cases-v3.sqlite')}
        put(directory / ('turn-' + str(turn) + '.json'), row)
        print(json.dumps({'case': case_id, 'arm': arm, 'turn': turn, 'status': output.get('status'),
            'http': status, 'calls': client.calls - call_start, 'seconds': round(row['seconds'], 1)}, ensure_ascii=False), flush=True)
        return row
    with TestClient(app, raise_server_exceptions=True) as api:
        for i, text in enumerate(turns, 1):
            row = post(api, text, i); products.append(row); put(directory / 'products.json', products)
        if arm == 'guided' and products[-1]['http_status'] == 200 and products[-1]['output'].get('status') == 'READY':
            confirmation = post(api, '이 최종 답을 이번 경험으로 확정해서 기억해줘.', 'confirm')
            secondary = {'confirmation': confirmation}
            eid = confirmation['output'].get('experience_id')
            secondary['queries'] = {}
            for kind in ('user_wiki', 'legal_wiki', 'experience'):
                if kind == 'experience' and not eid: continue
                body = {'query_kind': kind, **({'experience_id': eid} if kind == 'experience' else {'question': ''})}
                response = api.post('/v1/rag/memory/query', json=body)
                secondary['queries'][kind] = {'input': body, 'http_status': response.status_code, 'output': response.json()}
            if eid:
                secondary['reuse'] = post(api, case['question'], 'reuse', session=case_id + '-new')
            put(directory / 'secondary.json', secondary)
    put(directory / 'summary.json', {'complete': True, 'provider_attempts': client.calls, 'usage': client.usage,
        'product_turns': len(products), 'seconds': sum(x['seconds'] for x in products), 'main_unchanged': True})

if __name__ == '__main__':
    from pathlib import Path
    p = argparse.ArgumentParser(); p.add_argument('--case', required=True, choices=['cm-051', 'cm-003'])
    p.add_argument('--arm', required=True, choices=['baseline', 'unguided', 'guided']); p.add_argument('--preflight', action='store_true')
    a = p.parse_args(); main(a.case, a.arm, a.preflight)
