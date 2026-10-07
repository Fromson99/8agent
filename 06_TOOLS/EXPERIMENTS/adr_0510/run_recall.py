"""Fixed public retrieval-only probe. Never loads gold or calls a model."""
import json
import hashlib
import sys
import time
import traceback
from pathlib import Path

sys.dont_write_bytecode = True
R = Path(__file__).resolve().parents[3]
A = R/'04_EXPERIMENTS/ADR/ADR-0510-source-recall-first'
C = R/'02_BACKEND/lawrag/research/candidates/adr_0510/retrieval'
P = R/'02_BACKEND/lawrag/research/candidates/adr_0509/integrated/revisions/rev-001/snapshot'

def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, v):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2)+'\n')

def pin(mutable=False):
    if mutable:
        snapshot = C/'snapshot'
    else:
        frozen = read(A/'artifacts/frozen-design.json')
        for p, h in frozen['file_hashes'].items():
            if sha(R/p) != h:
                raise RuntimeError('Frozen input drift: '+p)
        revision = read(C/'candidate.json')['revisions'][-1]
        for f in revision['files']:
            if sha(R/f['frozen_path']) != f['snapshot_sha256']:
                raise RuntimeError('Candidate drift')
        snapshot = C/'revisions'/revision['revision_id']/'snapshot'
    sys.path[:0] = [str(P/'02_BACKEND'), str(R/'02_BACKEND')]
    import lawrag
    lawrag.__path__.append(str(R/'02_BACKEND/lawrag'))
    import semantic_runtime.legal_agent as package
    package.__path__.insert(0, str(snapshot/'02_BACKEND/semantic_runtime/legal_agent'))
    from semantic_runtime.legal_agent import question_obligations
    assert Path(question_obligations.__file__).is_relative_to(snapshot)
    return snapshot

class NoModel:
    binding = {'provider': 'offline', 'model': 'no-model-source-recall', 'adapter_version': 'disabled-v1',
               'endpoint_identity': 'none', 'trust_zone': 'internal', 'max_input_bytes': 2000000}
    def validate_model(self):
        return {'verified': False, 'mode': 'OFFLINE_SOURCE_RECALL_NO_MODEL'}
    def send_once(self, **kw):
        raise AssertionError('Retrieval probe must not send a model request')

def main():
    pin()
    from semantic_runtime.storage import Store
    from semantic_runtime.pipeline import Pipeline
    from semantic_runtime.document_agent import ServingDocumentAgent
    from semantic_runtime.contracts import digest
    from semantic_runtime.legal_agent.context import RequestContext
    from semantic_runtime.legal_agent.obligation_repository import ObligationRepository
    from semantic_runtime.legal_agent.workflow_tiers_tools import TiersTools
    from semantic_runtime.legal_agent.question_obligations import ObligationSession, SYSTEM, PROMPTS
    from semantic_runtime.legal_agent import workflow_tiers_policy as policy, obligation_protocol
    from semantic_runtime.legal_agent.gateway import ModelGateway
    prod = read(A/'product-cases.json')
    manifest = read(A/'실험/manifest.json')
    settings = policy.profile({**policy.DEFAULT_PROFILE, 'model_binding': NoModel.binding,
        'max_tool_actions': 192, 'wall_seconds': 300, 'max_context_chars': 60000,
        'question_obligations_enabled': True, 'numbered_references_enabled': True}, require_model=True)
    for run in manifest['runs']:
        (A/'artifacts'/run['id']).mkdir(exist_ok=False)
    store = Store(R/prod['generation'])
    runtime = R/'08_DEPLOYMENT/RELEASES/legal-agent-v5-20260922-r3/code'
    pipeline = Pipeline(runtime, store, implementation=policy.IMPLEMENTATION,
                        legal_agent_profile=settings, legal_agent_transport=NoModel())
    load_started = time.monotonic()
    agent = ServingDocumentAgent(pipeline, pipeline.term_agent.config)
    outputs = {r['id']: {'cases': {}, 'physical_model_calls': 0} for r in manifest['runs']}
    try:
        with agent.resources(prod['public_scope_document_ids']) as (index, tools, glossary, matcher):
            load_seconds = time.monotonic()-load_started
            lookup = {c['case_id']: c for c in prod['cases']}
            for run in manifest['runs']:
                for cid in run['case_ids']:
                    case = lookup[cid]
                    out = A/'artifacts'/run['id']/cid
                    out.mkdir()
                    query = pipeline.plan(case['question'], prod['public_scope_document_ids'])
                    binding = {'generation_id': store.manifest['generation_id'], 'store_sha256': store.manifest['store_sha256'],
                        'export_allowed': False, 'scope': query['scope'], 'model': NoModel.binding,
                        'domain_sha256': digest(policy.DOMAIN), 'profile_sha256': digest(settings),
                        'pipeline_sha256': sha(runtime/'00_SYSTEM/PIPELINE.json'),
                        'index_sha256': index.manifest['index_sha256'], 'glossary': glossary.binding,
                        'fulltext_sha256': matcher.fulltext.manifest['fulltext_sha256']}
                    request = {'question': case['question'], 'document_ids': prod['public_scope_document_ids'], 'use_llm': False}
                    context = RequestContext.create(query, request, binding, settings['wall_seconds'])
                    repo = ObligationRepository(out/'journal.sqlite', context, settings)
                    start = time.monotonic()
                    result = {'case_id': cid, 'error': None, 'physical_model_calls': 0, 'resource_load_seconds_shared': load_seconds}
                    try:
                        sources = TiersTools(store, tools, glossary, matcher, repo, context, settings)
                        gateway = ModelGateway(repo, context, settings, policy.DOMAIN, NoModel(),
                            message_protocol=obligation_protocol, system=SYSTEM, prompts=PROMPTS)
                        session = ObligationSession(context, repo, sources, gateway, settings, store.manifest['data_status'])
                        # This is the same preparation hook invoked before investigate in the candidate session.
                        value = session.prepare_source_recall()
                        assert session.prepare_source_recall() is value
                        result.update(value)
                        result['evidence'] = repo.evidence()
                        result['budget'] = repo.budget()
                        assert result['budget']['model_reserved'] == 0
                    except Exception as exc:
                        result['error'] = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
                    finally:
                        result['request_seconds'] = time.monotonic()-start
                        repo.close()
                        # A completed request's deadline handler must not leak into the next request.
                        for db in (store.db, tools.db, matcher.fulltext_db, *glossary.dbs.values()):
                            db.set_progress_handler(None, 0)
                    write(out/'result.json', result)
                    outputs[run['id']]['cases'][cid] = str((out/'result.json').relative_to(R))
                    write(A/'artifacts'/run['id']/'results.partial.json', outputs[run['id']])
                    print(json.dumps({'case': cid, 'read_complete': len(result.get('read_complete', [])),
                        'packets': len(result.get('packets', [])), 'seconds': round(result['request_seconds'], 2),
                        'error': result['error'] and result['error']['message']}, ensure_ascii=False), flush=True)
                write(A/'artifacts'/run['id']/'results.json', outputs[run['id']])
            glossary.check_unchanged()
    finally:
        store.close()

if __name__ == '__main__':
    main()
