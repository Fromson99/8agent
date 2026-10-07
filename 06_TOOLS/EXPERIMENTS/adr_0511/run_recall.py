"""Fixed public query-planning/source-acquisition probe. Never loads gold."""
import json
import hashlib
import sys
import time
import traceback
from pathlib import Path

sys.dont_write_bytecode = True
R = Path(__file__).resolve().parents[3]
A = R/'04_EXPERIMENTS/ADR/ADR-0511-gemma-query-source-recall'
C = R/'02_BACKEND/lawrag/research/candidates/adr_0511/retrieval'
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
    import lawrag.research
    lawrag.research.__path__.insert(0,str(snapshot/'02_BACKEND/lawrag/research'))
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

def plan_queries(prod, matcher, store):
    """Only public questions and public document titles enter the external planner."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from lawrag.research.experiment_client import ExperimentClient
    from semantic_runtime.legal_agent.source_query_planning import SYSTEM, schema, validate
    grant=read(A/'artifacts/export-rebinding.json')
    auth=R/'08_DEPLOYMENT/CONFIG/legal-source-export.json'
    if (sha(auth)!=grant['source_authorization_sha256'] or not read(auth)['enabled'] or
        grant['source_store_sha256']!=store.manifest['store_sha256'] or
        set(prod['public_scope_document_ids'])-set(grant['scope_document_ids']) or
        grant['policy_sha256']!=sha(A/'artifacts/gemma-policy.json')):
        raise RuntimeError('Public-source planning authorization mismatch')
    names=sorted({matcher.documents[d] for d in prod['public_scope_document_ids']})
    cases=[{'case_id':c['case_id'],'question':c['question']} for c in prod['cases']]
    batches=[cases[i:i+6] for i in range(0,len(cases),6)]
    started=time.monotonic();plans={};receipts=[];case_batches={}
    def one(i,batch):
        out=A/'artifacts/planner'/f'batch-{i+1:02d}'
        client=ExperimentClient(R,out,max_calls=1,max_output_tokens=4096,
                                scoped_policy=A/'artifacts/gemma-policy.json')
        start=time.monotonic();receipt={'batch':i+1,'case_ids':[c['case_id'] for c in batch],'error':None}
        try:
            value=client.generate(SYSTEM,{'documents':names,'questions':batch},schema(receipt['case_ids'],names),phase='source-query-plan')
            resolved=validate(value,batch,names)
        except Exception as exc:
            receipt['error']={'type':type(exc).__name__,'message':str(exc)}
            resolved={c['case_id']:{'law_names':[],'queries':[]} for c in batch}
        receipt.update(calls=client.calls,usage=client.usage,seconds=time.monotonic()-start)
        write(out/'receipt.json',receipt)
        return resolved,receipt
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(one,i,b) for i,b in enumerate(batches)]
        for future in as_completed(futures):
            resolved,receipt=future.result();plans.update(resolved);receipts.append(receipt)
            case_batches.update({cid:receipt['batch'] for cid in receipt['case_ids']})
            print(json.dumps({'planner_batch':receipt['batch'],'calls':receipt['calls'],'error':receipt['error']},ensure_ascii=False),flush=True)
    result={'plans':plans,'batches':sorted(receipts,key=lambda x:x['batch']),'case_batches':case_batches,
            'seconds':time.monotonic()-started,'actual_source_text_sent':False,
            'model':'google/gemma-4-31b-it','physical_calls':sum(x['calls'] for x in receipts)}
    write(A/'artifacts/query-planning.json',result)
    return plans,result

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
        'max_tool_actions': 384, 'wall_seconds': 300, 'max_context_chars': 60000,
        'question_obligations_enabled': True, 'numbered_references_enabled': True}, require_model=True)
    if '--preflight' not in sys.argv:
        for run in manifest['runs']:
            (A/'artifacts'/run['id']).mkdir(exist_ok=False)
    store = Store(R/prod['generation'])
    runtime = R/'08_DEPLOYMENT/RELEASES/legal-agent-v5-20260922-r3/code'
    pipeline = Pipeline(runtime, store, implementation=policy.IMPLEMENTATION,
                        legal_agent_profile=settings, legal_agent_transport=NoModel())
    load_started = time.monotonic()
    agent = ServingDocumentAgent(pipeline, pipeline.term_agent.config)
    outputs = {r['id']: {'cases': {}, 'physical_model_calls': 0, 'planner_calls_artifact':'artifacts/query-planning.json'} for r in manifest['runs']}
    try:
        with agent.resources(prod['public_scope_document_ids']) as (index, tools, glossary, matcher):
            load_seconds = time.monotonic()-load_started
            if '--preflight' in sys.argv:
                from lawrag.research.experiment_client import ExperimentClient
                from semantic_runtime.legal_agent.source_query_planning import schema
                ExperimentClient(R, A/'artifacts/planner-preflight', max_calls=1, max_output_tokens=4096, scoped_policy=A/'artifacts/gemma-policy.json')
                print(json.dumps({'preflight':'pass','documents':len(prod['public_scope_document_ids']),'model_calls':0})); return
            plans, planning = plan_queries(prod, matcher, store)
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
                        'fulltext_sha256': matcher.fulltext.manifest['fulltext_sha256'],
                        'query_plan_sha256':digest(plans[cid]),'planner_model':'google/gemma-4-31b-it'}
                    request = {'question': case['question'], 'document_ids': prod['public_scope_document_ids'], 'use_llm': False}
                    context = RequestContext.create(query, request, binding, settings['wall_seconds'])
                    repo = ObligationRepository(out/'journal.sqlite', context, settings)
                    start = time.monotonic()
                    result = {'case_id': cid, 'error': None, 'physical_model_calls': 0, 'resource_load_seconds_shared': load_seconds, 'query_plan':plans[cid], 'planner_batch':planning['case_batches'].get(cid)}
                    try:
                        sources = TiersTools(store, tools, glossary, matcher, repo, context, settings)
                        sources.recall_query_plan = plans[cid]
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
