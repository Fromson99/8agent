"""Read-only, fixed-root Gemma probe of the frozen ADR-0534 incoming gate."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
ROOT = next(p for p in Path(__file__).resolve().parents if (p / '00_SYSTEM/WORKSPACE.json').is_file())
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0535-gemma-reverse-gate-explosion-probe'
DESIGN = ADR / 'artifacts/frozen-design.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def pinned_runtime():
    bootstrap = load('adr0531_bootstrap', ROOT / '06_TOOLS/EXPERIMENTS/adr_0531/bootstrap.py')
    overlay = bootstrap.load_candidate()
    candidate = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0534/gated-reference'
    revision = read(candidate / 'candidate.json')['revisions'][-1]
    for row in revision['files']:
        path = ROOT / row['frozen_path']
        if sha(path) != row['snapshot_sha256']:
            raise ValueError('ADR-0534 frozen candidate drift: ' + str(path))
    snapshot = candidate / 'revisions' / revision['revision_id'] / 'snapshot/02_BACKEND/semantic_runtime'
    gate = load('semantic_runtime.reference_gate', snapshot / 'reference_gate.py')
    return overlay, gate.GatedReferenceNavigator


def roots():
    fixed = read(ROOT / '04_EXPERIMENTS/ADR/ADR-0526-frame-anchor-owner-repair/artifacts/fixed-start-roots.json')
    historical = ROOT / '04_EXPERIMENTS/ADR/ADR-0523-gemma-scoped-exploration-probe/artifacts/run-001/cm-009/guarded/graph.json.gz'
    with gzip.open(historical, 'rt') as stream:
        old = json.load(stream)
    fixed['cm-009'] = [{'source_id': x['extent']['source_id'], 'document_id': x['extent']['document_id'],
                        'block_ids': x['extent']['block_ids'], 'query': x['query'], 'reason': x['reason']}
                       for x in old['roots']]
    return {case: fixed[case] for case in ('cm-025', 'cm-040', 'cm-009')}


def source_scope(db):
    scope = read(ROOT / '04_EXPERIMENTS/ADR/ADR-0523-gemma-scoped-exploration-probe/product-cases.json')['public_scope_document_ids']
    grant = read(ROOT / '04_EXPERIMENTS/ADR/ADR-0523-gemma-scoped-exploration-probe/artifacts/export-rebinding.json')
    if set(scope) != set(grant['scope_document_ids']):
        raise ValueError('Public document scope changed')
    if sha(ROOT / '08_DEPLOYMENT/CONFIG/legal-source-export.json') != grant['source_authorization_sha256']:
        raise ValueError('Base export authorization changed')
    for item in grant['document_provenance']:
        if sha(ROOT / '01_DATA/RAW' / item['raw_relative_path']) != item['raw_sha256']:
            raise ValueError('Public RAW provenance changed: ' + item['document_id'])
    placeholders = ','.join('?' for _ in scope)
    sources = {source['id']: source for (raw,) in db.execute(
        'SELECT json FROM source WHERE document_id IN (' + placeholders + ')', scope)
        for source in [json.loads(raw)]}
    if {s['document_id'] for s in sources.values()} - set(scope):
        raise ValueError('Source escaped public scope')
    return scope, sources


def anchors(nav, sources, case_roots):
    chosen = {}
    for case, rows in case_roots.items():
        selected = []
        for row in rows:
            source = sources.get(row['source_id'])
            if source is None or source['document_id'] != row['document_id']:
                raise ValueError('Historical root not in public scope')
            if sorted(str(b['block_id']) for b in source['blocks']) != sorted(map(str, row['block_ids'])):
                raise ValueError('Historical root blocks changed')
            selected.append(nav.root(row['source_id'], query=row['query'], reason=row['reason'],
                                     block_ids=row['block_ids']))
        chosen[case] = selected
    article363 = next(s for s in sources.values() if s.get('document_name') == '상법'
                      and s.get('heading', '').startswith('제363조 '))
    chosen['cm-040-forward-363'] = [nav.root(article363['id'], query=case_roots['cm-040'][0]['query'],
                                         reason='제433조가 제363조 통지를 정방향으로 인용')]
    return chosen


def pages(nav, selected):
    result = {}
    for case, rows in selected.items():
        result[case] = []
        for root in rows:
            page = nav.incoming_candidates(root['extent'], limit=100)
            if page['next_offset'] is not None:
                raise ValueError('Candidate page exceeds frozen 100-item limit')
            result[case].append(page)
    return result


def invoke_gemma(policy_path, output, max_calls):
    from dotenv import dotenv_values
    from lawrag.research.experiment_client import OpenRouterProxyClient
    policy = read(policy_path)
    if policy['schema_version'] != 'user-authorized-openrouter-product-v1' or policy['adr_id'] != 'ADR-0535':
        raise ValueError('Wrong Gemma policy')
    if (policy['model'] != 'google/gemma-4-31b-it' or policy['provider_routing'] !=
            {'only':['parasail/fp8'], 'order':['parasail/fp8'], 'quantizations':['fp8'],
             'allow_fallbacks':False, 'require_parameters':True} or
            policy['allowed_upstream_providers'] != ['Parasail'] or
            policy['reasoning'] != {'enabled':False} or policy['source_scope'] != ['public'] or
            policy['fallback_allowed'] is not False):
        raise ValueError('Gemma route or scope changed')
    key = os.environ.get('OPEN_ROUTER') or dotenv_values(ROOT / '.env').get('OPEN_ROUTER')
    if not key:
        raise ValueError('OPEN_ROUTER is unavailable')
    client = OpenRouterProxyClient.__new__(OpenRouterProxyClient)
    client.root = ROOT
    client.output = output
    client.proxy = policy
    client.policy = policy
    client.model = policy['model']
    client._key = key
    client.max_calls = max_calls
    client.calls = 0
    client.usage = []
    client.transport = None
    client.max_output_tokens = policy['max_output_tokens']
    client.schema_in_prompt = False
    client.max_repairs = 0
    client.policy_hash = sha(policy_path)
    output.mkdir(parents=True, exist_ok=False)
    return client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if args.preflight == args.run:
        parser.error('Choose exactly one of --preflight or --run')
    design = read(DESIGN)
    for path, expected in design['input_sha256'].items():
        if sha(ROOT / path) != expected:
            raise ValueError('Frozen input drift: ' + path)
    if args.run and sha(Path(__file__)) != design['runner_sha256']:
        raise ValueError('Runner changed after freeze')
    overlay, Navigator = pinned_runtime()
    generation = ROOT / design['generation']
    with overlay.closing(overlay.open_research_overlay(generation)) as db:
        scope, sources = source_scope(db)
        nav = Navigator(db, sources, scope, design['binding'])
        selected = anchors(nav, sources, roots())
        views = pages(nav, selected)
        shape = {case: [{'anchor': p['anchor']['source_id'], 'candidates': p['total'],
                         'view_hash': p['view_hash']} for p in ps] for case, ps in views.items()}
        if args.preflight:
            print(json.dumps(shape, ensure_ascii=False, indent=2))
            return
        output = ADR / 'artifacts/run-001'
        output.mkdir(parents=True, exist_ok=False)
        client = invoke_gemma(ADR / 'artifacts/gemma-policy.json', output / 'calls', design['max_calls'])
        result = {'schema_version':'adr0535-gemma-gate-probe-v1', 'case_order':design['case_order'],
                  'anchors':shape, 'model':client.model, 'cases':{}, 'failures':[],
                  'main_wiring_unchanged':True}
        for case in design['case_order']:
            case_out = {'root_count':len(selected[case]), 'anchors':[]}
            if case in ('cm-025','cm-040','cm-009'):
                graph = nav.walk(selected[case], max_states=500, max_seconds=30)
                case_out['forward_graph'] = {'status':graph['status'], 'sources':len(graph['source_ids']),
                                             'states':len(graph['states']), 'edges':len(graph['edges']),
                                             'pending':len(graph['pending']),
                                             'incoming_edges':sum(e['direction']=='incoming' for e in graph['edges'])}
            for idx, page in enumerate(views[case]):
                item = {'anchor':page['anchor']['source_id'], 'candidate_count':page['total'],
                        'view_hash':page['view_hash']}
                if page['items']:
                    def ask(system, view, schema):
                        return client.generate(system, view, schema, phase=case.replace('-', '') + str(idx))
                    try:
                        answer = nav.review_incoming(page, query=selected[case][idx]['query'], invoke=ask)
                        item['decision'] = answer['model_decision']
                        item['selected'] = [{'candidate_id':c['candidate_id'], 'document_name':c['document_name'],
                                             'heading':c['heading'], 'locator':c['locator'],
                                             'reason':next(x['reason'] for x in answer['model_decision']['selected']
                                                           if x['candidate_id']==c['candidate_id'])}
                                            for c in page['items'] if c['candidate_id'] in answer['selected_candidate_ids']]
                        item['root_spans'] = [r['extent'].get('spans') for r in answer['roots']]
                    except Exception as exc:
                        item['error'] = {'type':type(exc).__name__, 'message':str(exc)}
                        result['failures'].append({'case':case, 'anchor':item['anchor'], **item['error']})
                case_out['anchors'].append(item)
                write(output / (case + '-' + str(idx) + '.json'), item)
            result['cases'][case] = case_out
            (output / 'partial.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
            print(case, case_out.get('forward_graph'), 'calls', client.calls, flush=True)
        result['model_calls'] = client.calls
        result['usage'] = client.usage
        result['cost_usd'] = sum(x.get('cost_usd') or 0 for x in client.usage)
        write(output / 'result.json', result)


if __name__ == '__main__':
    main()
