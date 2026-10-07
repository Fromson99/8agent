"""Offline frozen search comparison; no model, API, registry or generation writes."""
import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

import apply as installer
import transform
import codespace_data

PATCH = Path(__file__).resolve().parent

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def verify_package():
    spec = json.loads((PATCH/'PATCH_MANIFEST.json').read_bytes())
    for name, expected in spec['assets'].items():
        if installer.sha((PATCH/name).read_bytes()) != expected:
            raise ValueError('package hash mismatch: '+name)
    return spec

@contextmanager
def capture(obs):
    records = []
    original = obs.event
    def event(logger, name, **fields):
        if name in ('fulltext.sql.timings', 'fulltext.location.timings'):
            records.append({'event': name, **fields})
        return original(logger, name, **fields)
    obs.event = event
    try:
        yield records
    finally:
        obs.event = original

def one(pipeline, plan, query, fn, runtime, obs):
    request = {'question': query, 'document_ids': plan['scope']['document_version_ids'], 'use_llm': False}
    opened = time.perf_counter()
    with pipeline.term_agent.open_session(request, query=plan, runtime=runtime) as session:
        setup_ms = (time.perf_counter()-opened)*1000
        tool = session.sources
        args = {'target': tool.root, 'query': query, 'mode': 'fulltext'}
        locations = []
        original_page = tool.page
        def page(values, offset):
            locations[:] = values
            return original_page(values, offset)
        tool.page = page
        with capture(obs) as events:
            start = time.perf_counter()
            items, nxt, evidence, extra = fn(tool, args, 0)
            total_ms = (time.perf_counter()-start)*1000
        timings = [r for r in events if r['event']=='fulltext.location.timings']
        if len(timings)!=1 or timings[0]['mapping_status']!='completed':
            raise ValueError('missing successful location metrics')
        # Handles are request-bound. Compare their resolved coordinates and the
        # actual preview fields, preserving all other returned card content.
        def stable(value):
            if isinstance(value, dict):
                return {k: stable(v) for k,v in value.items() if k!='preview_hash'}
            if isinstance(value, (list,tuple)):
                return [stable(v) for v in value]
            if isinstance(value, str):
                try:
                    resolved = tool.resolve(value)
                except Exception:
                    return value
                return stable({k:v for k,v in resolved.items() if k!='binding'})
            return value
        receipt = extra['search_receipt']
        from semantic_runtime.contracts import digest as runtime_digest
        for card in items:
            node = tool.resolve(card['target'])
            if card['preview_hash'] != runtime_digest([node,card['preview_spans'],session.context.binding_hash]):
                raise ValueError('preview binding hash mismatch')
            for span in card['preview_spans']:
                text = session.sources.store.source(node['document_id'],span['block_id'])['text']
                if text[span['start_cp']:span['end_cp']]!=span['text'] or installer.sha(text.encode())!=span['block_hash'] or installer.sha(span['text'].encode())!=span['span_hash']:
                    raise ValueError('preview text/span hash mismatch')
        comparison = {'locations': locations, 'items': stable(items), 'next': nxt,
                      'evidence': stable(evidence), 'receipt': stable(receipt)}
        return {'setup_ms': round(setup_ms,3), 'search_ms': round(total_ms,3),
                'result_sha256': digest(comparison), 'locations_sha256': digest(locations),
                'total': receipt['total'], 'page_count': len(items),
                'location': timings[0], 'fts': [r for r in events if r['event']=='fulltext.sql.timings']}

def summarize(rows, cases, pairs, threshold=20.0):
    result = []
    for case in cases:
        subset = [r for r in rows if r['case_id']==case['case_id']]
        baseline = [r for r in subset if r['arm']=='baseline']
        candidate = [r for r in subset if r['arm']=='metadata-location']
        identical = len({r['result_sha256'] for r in subset})==1
        base = statistics.median(r['location']['elapsed_ms'] for r in baseline)
        new = statistics.median(r['location']['elapsed_ms'] for r in candidate)
        reduction = (1-new/base)*100 if base>0 else 0
        body_zero = all(r['location']['source_sql_count']==0 for r in candidate)
        informative = all(r['total']>0 for r in subset)
        paired = [b['location']['elapsed_ms']>=c['location']['elapsed_ms'] for b,c in zip(baseline,candidate)]
        result.append({'case_id': case['case_id'], 'same_results': identical, 'nonempty': informative,
                       'candidate_location_body_sql_zero': body_zero,
                       'baseline_location_p50_ms': round(base,3), 'candidate_location_p50_ms': round(new,3),
                       'location_reduction_percent': round(reduction,2),
                       'baseline_search_p50_ms': round(statistics.median(r['search_ms'] for r in baseline),3),
                       'candidate_search_p50_ms': round(statistics.median(r['search_ms'] for r in candidate),3),
                       'faster_pairs': sum(paired), 'pairs': pairs,
                       'observed_location_improvement': identical and body_zero and informative and reduction>=threshold and sum(paired)>=pairs-1})
    return result

def run(root, gen, out, matrix, pairs, selection_check=None, selection=None):
    from semantic_runtime import observability as obs
    from semantic_runtime import pipeline as pipeline_module
    from semantic_runtime.storage import Store
    from semantic_runtime.legal_agent import workflow_relations_tools as relations
    from semantic_runtime.legal_agent.domain import load_bound
    config = json.loads((root/'00_SYSTEM/PIPELINE.json').read_bytes())
    settings = next(n for n in config['profiles']['legal-agent-rag-v5']['nodes'] if n['id']=='retrieve')['parameters']['term_agent']['legal_agent']
    original_profile = load_bound(root, settings['profile'])
    profile = deepcopy(original_profile)
    profile.update(model_binding=None, wall_seconds=1800)
    code = installer.prepare(root, verify_package()) # validates all selected pins; no writes
    before = (PATCH/'baseline.py').read_bytes()
    after = (PATCH/'candidate.py').read_bytes()
    functions = {'baseline': transform.function(before, vars(relations)),
                 'metadata-location': transform.function(after, vars(relations))}
    if transform.ast_sha((root/transform.TARGET).read_bytes()) not in (transform.ast_sha(before),transform.ast_sha(after)):
        raise ValueError('checkout search does not match frozen arms')
    generation_raw = (gen/'manifest.json').read_bytes()
    code_pins = {'00_SYSTEM/PIPELINE.json': installer.sha((root/'00_SYSTEM/PIPELINE.json').read_bytes())}
    code_pins[settings['profile']['path']] = settings['profile']['sha256']
    code_pins[settings['domain']['path']] = settings['domain']['sha256']
    for entry in config['engines'].values():
        manifest = json.loads((root/entry['manifest']).read_bytes())
        code_pins[entry['manifest']] = entry['sha256']
        code_pins.update(manifest['files'])
    print('OFFLINE_PREPARE: source/nav/fulltext verification and request resources; no model calls',flush=True)
    store = Store(gen)
    try:
        pipeline = pipeline_module.Pipeline(root, store, provider=object(), implementation='legal-agent-tools-v5', legal_agent_profile=profile)
        cases = []
        plans = {}
        for i, case in enumerate(matrix,1):
            if set(case)!={'team','query'} or not isinstance(case['query'],str) or not case['query'].strip():
                raise ValueError('case must contain only team and nonempty query')
            case_id = 'case-%02d'%i
            plan = pipeline.plan(case['query'], team_id=case['team'])
            plans[case_id] = plan
            cases.append({'case_id':case_id, 'team':case['team'], 'query_sha256':digest(case['query']),
                          'document_ids_sha256':digest(plan['scope']['document_version_ids']),
                          'document_count':len(plan['scope']['document_version_ids'])})
        frozen = {'adr_id':'ADR-0549', 'experiment_id':'ADR-0549-experiment-v1', 'run_id':out.name,
                  'frozen_before_measurement':True, 'created_at':datetime.now(timezone.utc).isoformat(),
                  'code_root':str(root), 'generation':str(gen), 'generation_manifest_sha256':installer.sha(generation_raw),
                  'base_commit':subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),
                  'tracked_code_dirty':subprocess.run(['git','-C',str(root),'diff','--quiet','HEAD'],check=False).returncode!=0,
                  'patch_manifest_sha256':installer.sha((PATCH/'PATCH_MANIFEST.json').read_bytes()),
                  'generation_id':store.manifest['generation_id'], 'code_pins':code_pins,
                  'data_status':store.manifest['data_status'],
                  'data_selection':selection,
                  'baseline_sha256':installer.sha(before), 'candidate_sha256':installer.sha(after),
                  'matrix_sha256':digest(matrix), 'cases':cases, 'pairs':pairs,
                  'order':'AB,BA alternating', 'profile':profile,
                  'selected_profile_sha256':digest(original_profile), 'profile_overrides':{'model_binding':None,'wall_seconds':1800}, 'llm_calls':0,
                  'os_cache_policy':'no cache flush; fresh request SourceMap; same process metadata reuse',
                  'criterion':'identical results; nonempty; candidate location SQL 0; median location reduction >=20%; faster in >=pairs-1 pairs',
                  'decision_eligible':False, 'workflow_verified':False}
        installer.atomic(out/'FROZEN_PLAN.json',installer.dump(frozen))
        rows = []
        for case, raw in zip(cases,matrix):
            for pair in range(pairs):
                order = ('baseline','metadata-location') if pair%2==0 else ('metadata-location','baseline')
                for arm in order:
                    row = one(pipeline, plans[case['case_id']], raw['query'], functions[arm], out/'runtime', obs)
                    row.update(case_id=case['case_id'],arm=arm,pair=pair+1)
                    rows.append(row)
                    installer.atomic(out/'RESULTS_PARTIAL.json',installer.dump(rows))
                    print(json.dumps({'case_id':row['case_id'],'arm':arm,'pair':pair+1,'total':row['total'],
                                      'location_ms':row['location']['elapsed_ms'],'body_sql':row['location']['source_sql_count']},ensure_ascii=False),flush=True)
        if (gen/'manifest.json').read_bytes()!=generation_raw:
            raise ValueError('generation changed during comparison')
        for name, expected in code_pins.items():
            if installer.sha((root/name).read_bytes())!=expected:
                raise ValueError('code changed during comparison: '+name)
        installer.prepare(root, verify_package())
        if selection_check is not None and not selection_check():
            raise ValueError('selected generation changed during comparison')
        summary = summarize(rows,cases,pairs)
        result = {'status':'COMPLETE','plan_sha256':installer.sha((out/'FROZEN_PLAN.json').read_bytes()),
                  'cases':summary,'rows':rows,'llm_calls':0,'workflow_verified':False,
                  'limits':'warm-cache isolated offline search comparison; no answer/loading/NFS diagnosis or serving latency certification'}
        installer.atomic(out/'RESULTS.json',installer.dump(result))
        print(json.dumps({'status':'COMPLETE','cases':summary,'results':str(out/'RESULTS.json')},ensure_ascii=False),flush=True)
        if any(not r['same_results'] or not r['candidate_location_body_sql_zero'] for r in summary):
            raise ValueError('search contract or read reduction failed; do not deploy')
    finally:
        store.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--deploy-root',type=Path,required=True)
    parser.add_argument('--generation',type=Path)
    parser.add_argument('--generation-index',type=int)
    parser.add_argument('--matrix',type=Path)
    parser.add_argument('--pairs',type=int,default=4)
    args = parser.parse_args()
    if not 2<=args.pairs<=20:
        raise ValueError('pairs must be 2..20')
    root = args.deploy_root.expanduser().resolve(strict=True)
    git_root = subprocess.check_output(['git','-C',str(root),'rev-parse','--show-toplevel'],text=True).strip()
    if Path(git_root).resolve()!=root:
        raise ValueError('deploy-root must be the existing Git root')
    os.environ['LAWRAG_WORKSPACE_ROOT']=str(root)
    sys.path.insert(0,str(root/'02_BACKEND'))
    verify_package()
    config = json.loads((root/'00_SYSTEM/PIPELINE.json').read_bytes())
    term_config = next(n for n in config['profiles']['legal-agent-rag-v5']['nodes'] if n['id']=='retrieve')['parameters']['term_agent']
    selection = codespace_data.select(root,term_config,explicit=args.generation,index=args.generation_index)
    gen = Path(selection['path'])
    print('OFFLINE_DATA_SELECTED',json.dumps(selection,ensure_ascii=False),flush=True)
    matrix = json.loads((args.matrix or PATCH/'MATRIX.json').read_bytes())
    if not isinstance(matrix,list) or not matrix:
        raise ValueError('matrix must be a nonempty array')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = root/'TRANSFER'/installer.PATCH_ID/('offline-'+stamp)
    out.mkdir(parents=True)
    try:
        run(root,gen,out,matrix,args.pairs,selection_check=lambda:codespace_data.unchanged(selection),selection=selection)
    except BaseException as exc:
        installer.atomic(out/'FAILED.json',installer.dump({'status':'FAILED','error_type':type(exc).__name__,'workflow_verified':False}))
        raise
    print('OFFLINE_RESULTS',out,flush=True)

if __name__=='__main__':
    main()
