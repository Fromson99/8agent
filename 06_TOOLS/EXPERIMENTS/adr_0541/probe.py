"""ADR-0541: paired Gemma query planning on all 61 fixed public cases."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
ROOT = next(p for p in Path(__file__).resolve().parents if (p/'00_SYSTEM/WORKSPACE.json').is_file())
sys.path.insert(0, str(ROOT/'02_BACKEND'))
# Reopen ADR-0539's pinned Kiwi v1 index with the frozen tokenizer modules.
# The live working tree now uses PeCab and would reject that index.
import semantic_runtime
LEGACY = ROOT/'08_DEPLOYMENT/RELEASES/legal-agent-v5-20260922-r3/code/02_BACKEND/semantic_runtime'
for module_name in ('term_morph', 'fulltext'):
    spec = importlib.util.spec_from_file_location('semantic_runtime.'+module_name, LEGACY/(module_name+'.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    setattr(semantic_runtime, module_name, module)
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-0541-reverse-hint-larger-sample'
CAND = ROOT/'02_BACKEND/lawrag/research/candidates/adr_0539/reverse-hints'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def candidate():
    manifest = read(CAND/'candidate.json')
    revision = manifest['revisions'][-1]
    for row in revision['files']:
        if sha(ROOT/row['frozen_path']) != row['snapshot_sha256']:
            raise ValueError('candidate snapshot drift')
    path = CAND/'revisions'/revision['revision_id']/'snapshot/02_BACKEND/semantic_runtime/legal_agent/source_query_planning.py'
    spec = importlib.util.spec_from_file_location('adr0539_query_plan', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight', action='store_true')
    args = parser.parse_args()
    design = read(ADR/'artifacts/frozen-design.json')
    for rel, expected in design['input_sha256'].items():
        if sha(ROOT/rel) != expected:
            raise ValueError('frozen input drift: '+rel)
    if not args.preflight and sha(Path(__file__)) != design['runner_sha256']:
        raise ValueError('runner drift')
    from semantic_runtime.storage import Store
    from semantic_runtime.pipeline import Pipeline
    from semantic_runtime.document_agent import ServingDocumentAgent
    from semantic_runtime.fulltext import question_terms
    from semantic_runtime.legal_agent.source_query_planning import SYSTEM, schema, validate
    from semantic_runtime.legal_agent.source_recall_global import query_variants
    client_spec = importlib.util.spec_from_file_location('experiment_client', ROOT/'02_BACKEND/lawrag/research/experiment_client.py')
    client_module = importlib.util.module_from_spec(client_spec)
    client_spec.loader.exec_module(client_module)
    ExperimentClient = client_module.ExperimentClient

    prod = read(ROOT/design['product_cases'])
    grant = read(ROOT/design['grant'])
    auth = read(ROOT/'08_DEPLOYMENT/CONFIG/legal-source-export.json')
    if (not auth['enabled'] or grant['destination']!='https://openrouter.ai/api/v1'
            or grant['model']!='google/gemma-4-31b-it'
            or set(prod['public_scope_document_ids']) != set(grant['scope_document_ids'])):
        raise ValueError('public export scope mismatch')
    store = Store(ROOT/prod['generation'])
    if store.manifest['store_sha256'] != grant['source_store_sha256']:
        raise ValueError('source store not bound to public export grant')
    from semantic_runtime.legal_agent import workflow_tiers_policy as policy
    class NoModel:
        binding = {'provider':'offline','model':'no-model-query-probe','adapter_version':'disabled-v1',
                   'endpoint_identity':'none','trust_zone':'internal','max_input_bytes':2000000}
        def validate_model(self):
            return {'verified':False,'mode':'OFFLINE_QUERY_PROBE_NO_MODEL'}
        def send_once(self, **kw):
            raise AssertionError('retrieval probe must not send a serving model request')
    settings = policy.profile({**policy.DEFAULT_PROFILE,'model_binding':NoModel.binding},require_model=True)
    runtime = ROOT/'08_DEPLOYMENT/RELEASES/legal-agent-v5-20260922-r3/code'
    pipeline = Pipeline(runtime, store, implementation=policy.IMPLEMENTATION,
                        legal_agent_profile=settings,legal_agent_transport=NoModel())
    agent = ServingDocumentAgent(pipeline, pipeline.term_agent.config)
    cand = candidate()
    cases = {x['case_id']:x for x in prod['cases']}
    case_order = design['case_order']
    output = {'schema_version':'adr0539-query-plan-probe-v1','cases':{},'generation':prod['generation'],
              'main_wiring_unchanged':True,'model':'google/gemma-4-31b-it'}
    try:
        with agent.resources(prod['public_scope_document_ids']) as (_, tools, _, matcher):
            names = sorted({matcher.documents[d] for d in prod['public_scope_document_ids']})
            allowed = {sid for sid,s in tools.sources.items() if s['document_id'] in prod['public_scope_document_ids']}
            for cid in case_order:
                question = cases[cid]['question']
                hints = cand.reverse_hints(question,matcher,tools,store,prod['public_scope_document_ids'],
                                           max_terms=design['max_terms'],max_cards=design['max_cards'])
                if args.preflight:
                    print(json.dumps({'case_id':cid,'hints':len(hints),'hint_chars':len(json.dumps(hints,ensure_ascii=False))},ensure_ascii=False),flush=True)
                    continue
                write(ADR/'artifacts/run-001'/cid/'reverse-hints.json', hints)
                output['cases'][cid]={'question':question,'hints':hints,'arms':{}}
                for arm in design['arm_order'][cid]:
                    mod = cand if arm=='hint-plan' else None
                    data = {'cases':[{'case_id':cid,'question':question}], 'law_names':names}
                    if mod:
                        data['cases'][0]['reverse_hints']=hints
                    start=time.monotonic()
                    client=ExperimentClient(ROOT, ADR/'artifacts/run-001'/cid/arm/'calls',max_calls=1)
                    value=client.generate(mod.SYSTEM if mod else SYSTEM,data,schema([cid],names),
                                          phase='query-plan')
                    plan=validate(value,data['cases'],names)[cid]
                    variants=list(dict.fromkeys(query_variants(question)+plan['queries']))
                    ranks=[]
                    protected=[]
                    broad=[]
                    for variant in variants:
                        terms=question_terms(variant)
                        ids=matcher.fulltext.rank(matcher.fulltext_db,terms,allowed) if terms else []
                        ranks.append({'query':variant,'terms':terms,'hit_count':len(ids),
                                      'top8':ids[:8],'top64':ids[:64]})
                        protected.extend(ids[:8]); broad.extend(ids[:64])
                    record={'input':data,'system':mod.SYSTEM if mod else SYSTEM,'output':value,
                            'plan':plan,'queries':ranks,'protected_union':list(dict.fromkeys(protected)),
                            'top64_union':list(dict.fromkeys(broad)),
                            'seconds':round(time.monotonic()-start,3),'usage':client.usage,
                            'calls':client.calls}
                    write(ADR/'artifacts/run-001'/cid/arm/'record.json',record)
                    output['cases'][cid]['arms'][arm]={'record':str((ADR/'artifacts/run-001'/cid/arm/'record.json').relative_to(ROOT)),
                                                        'plan':plan,'protected_union':record['protected_union'],
                                                        'top64_union':record['top64_union'],'usage':client.usage,
                                                        'seconds':record['seconds']}
                    print(json.dumps({'case_id':cid,'arm':arm,'queries':plan['queries'],
                                      'protected':len(record['protected_union']),'calls':client.calls},ensure_ascii=False),flush=True)
                (ADR/'artifacts/run-001/partial.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
        if not args.preflight:
            write(ADR/'artifacts/run-001/result.json',output)
    finally:
        store.close()


if __name__=='__main__':
    main()
