"""Prospective synthetic native SourceRecall -> native selector -> Gemma answer probe.

Explicit research runner only. Never reads offline gold or changes MAIN.
Purpose recognition is an extra physical model call charged to the candidate.
"""
from __future__ import annotations
from contextlib import contextmanager
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-0567-investigation-ontology-journal'
CANDIDATE = ROOT/'02_BACKEND/lawrag/research/candidates/adr_0567/graph'
DESIGN = ADR/'artifacts/design'
sys.dont_write_bytecode = True
for p in (ROOT/'02_BACKEND', ROOT/'05_TESTS', ROOT/'05_TESTS/CONTRACTS'):
    sys.path.insert(0, str(p))
os.environ.setdefault('LAWRAG_WORKSPACE_ROOT', str(ROOT))


def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p, v):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2)+'\n')


def verify():
    m = read(ADR/'실험/manifest.json')
    if not m['design']['criteria_frozen_before_run']: raise ValueError('unfrozen design')
    for p, h in m['design']['frozen_inputs'].items():
        if sha(ROOT/p) != h: raise ValueError('input drift: '+p)
    for p, h in read(DESIGN/'code-pins.json').items():
        if sha(ROOT/p) != h: raise ValueError('runtime drift: '+p)
    c = m['design']['code_isolation']['candidates'][0]
    if sha(ROOT/c['manifest_path']) != c['manifest_sha256']: raise ValueError('candidate drift')
    rev = read(CANDIDATE/'candidate.json')['revisions'][-1]
    for f in rev['files']:
        if sha(ROOT/f['frozen_path']) != f['snapshot_sha256']: raise ValueError('revision drift')
    return rev


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def build_fixture(out):
    from conftest import term_glossary
    from test_document_release import source
    from lawrag.pipeline.term_generation import build_generation
    from lawrag.core.legal_coordinate import find_coordinates
    out.mkdir(parents=True, exist_ok=False)
    corpus = read(DESIGN/'corpus.json')['documents']
    glossary = term_glossary.__wrapped__(out)
    raw = source(out/'raw.sqlite', [(d['id'], d['name'], [a['text'] for a in d['articles']]) for d in corpus])
    with sqlite3.connect(raw) as db:
        for d in corpus:
            db.execute('UPDATE document SET json=? WHERE document_id=?',
                       (json.dumps({'classification':'SYNTHETIC','version':d['version'],
                                    'evidence_role':d['role']}, ensure_ascii=False), d['id']))
            for i, a in enumerate(d['articles']):
                unit = json.loads(db.execute('SELECT json FROM source_unit WHERE document_id=? AND unit_id=?',
                                            (d['id'], str(i))).fetchone()[0])
                coord = find_coordinates(unit['surface'])[0].coordinate
                unit.update(title=a['title'], legal_coordinate=coord.as_dict(), coordinate_scope='body',
                            coordinate_key='body:'+coord.canonical_surface())
                db.execute('UPDATE source_unit SET json=? WHERE document_id=? AND unit_id=?',
                           (json.dumps(unit, ensure_ascii=False), d['id'], str(i)))
    build_generation(raw, glossary, out/'built', serving=True)
    return out/'built/generation'


class SyntheticTransport:
    def __init__(self, generation, live):
        self.manifest = read(generation/'manifest.json')
        self.binding = {'provider':'openrouter-experiment' if live else 'fixture',
                        'model':'google/gemma-4-31b-it' if live else 'synthetic-contract',
                        'adapter_version':'adr0567-synthetic-v1','endpoint_identity':'approved-experiment-policy',
                        'trust_zone':'external' if live else 'internal','max_input_bytes':2_000_000}
    def validate_model(self): return {'verified':True,'model':self.binding['model']}
    def authorize(self, query, request, manifest, *, public_question):
        if manifest['store_sha256'] != self.manifest['store_sha256'] or not public_question:
            raise ValueError('synthetic grant mismatch')
        if set(query['scope']['document_version_ids'])-set(d['id'] for d in read(DESIGN/'corpus.json')['documents']):
            raise ValueError('non-synthetic document')
        return {'classification':'SYNTHETIC','store_sha256':manifest['store_sha256']}
    def validate_authorization(self, context):
        if context.binding.get('external_authorization',{}).get('store_sha256') != self.manifest['store_sha256']:
            raise ValueError('synthetic authorization missing')
    def send_once(self, **kwargs): raise RuntimeError('explicit audited ExperimentClient only')


@contextmanager
def session(out, generation, case, live):
    from semantic_runtime.app import create_app
    from semantic_runtime.legal_agent.workflow_tiers_policy import DEFAULT_PROFILE
    transport = SyntheticTransport(generation, live)
    profile = {**DEFAULT_PROFILE,'model_binding':transport.binding,
               'bounded_source_selection_enabled':False,'final_review_enabled':False,
               'max_model_attempts':20,'wall_seconds':900,'max_read_chars':3000}
    app = create_app(out, generation, contracts_root=ROOT, provider=object(),
                     implementation='legal-agent-tools-v5',legal_agent_profile=profile,
                     legal_agent_transport=transport)
    pipeline = app.state.pipeline
    try:
        request = {'question':case['question'],'document_ids':case['documents'],'use_llm':True}
        with pipeline.term_agent.open_session(request,query=pipeline.plan(case['question'],case['documents']),
                     runtime=out/'runtime',external_public_question=live) as s:
            # A shared prospective search plan isolates the access-policy delta.
            # Neither arm executes request routing, obligation planning or Compose.
            s.sources.recall_query_plan = case['query_plan']
            yield s
    finally: pipeline.store.close()


def catalogue(s):
    result = {}
    for sid, row in s.sources.matcher.sources.items():
        blocks = s.sources.tools.sources[sid]['blocks']
        text = '\n'.join(b['text'] for b in blocks)
        result[sid] = {'document_id':row['document_id'],'unit_id':row['unit_id'],
                       'text_sha256':hashlib.sha256(text.encode()).hexdigest()}
    return result


def create_graph(module, out, cat):
    g = module.Graph(out, create=True)
    g.concept('purpose:applicable','PURPOSE','적용규정 탐색')
    g.concept('purpose:inventory','PURPOSE','자료 전체 목록·종류')
    g.concept('purpose:performance','PURPOSE','업무 실적 정보')
    g.concept('class:regulation','DATA_CLASS','규범·정의·예외·절차')
    g.concept('class:performance','DATA_CLASS','업무 실적 통계')
    proof = {'basis':'사전 설계한 합성 조사: 실적 수치는 적용대상 규범이 아님',
             'reference':'ADR-0566 design ontology.json','classification':'SYNTHETIC_CURATED_NOT_LOG_LEARNED'}
    g.relate('exclude-performance','purpose:applicable','EXCLUDES','class:performance',
             status='ACTIVE',proof=proof)
    for sid, row in cat.items():
        resource = row['document_id'].split(':')[0]+':unit:'+row['unit_id']
        g.add_resource(resource, resource)
        kind = 'class:regulation' if row['document_id']=='mock-regulation:v1' else 'class:performance'
        # Drift document has only a stale membership. Current origin is different.
        origin = '0'*64 if row['document_id']=='mock-drift:v2' else row['text_sha256']
        g.classify(resource,kind,origin,proof=proof)
        g.bind_node('synthetic-generation-v1',sid,resource,row['text_sha256'])
    g.close()


def apply_policy(s, graph, graph_module, classifier, cat):
    started = time.perf_counter()
    purpose = {'APPLICABILITY':'purpose:applicable','INVENTORY':'purpose:inventory',
               'PERFORMANCE':'purpose:performance'}.get(classifier['purpose'])
    if classifier['confidence'] != 'HIGH': purpose = None
    resources = {row[0] for row in graph.db.execute('SELECT DISTINCT resource_id FROM node')
                 if any(c['document_id'] in s.sources.scope and
                        c['document_id'].split(':')[0]+':unit:'+c['unit_id']==row[0] for c in cat.values())}
    try:
        policy = graph.compile(purpose,'synthetic-generation-v1',resources,'discover')
    except graph_module.RevalidationRequired as exc:
        policy = graph.compile(None,'synthetic-generation-v1',resources,'discover')
        policy['fallback_reason'] = str(exc)
    allowed = set(policy['allowed_node_ids'])
    s.sources.investigation_allowed_source_ids = allowed
    # A read adapter checks the same DB-derived scope at the native action boundary.
    # Ancestor/document READ must not encompass any excluded descendants.
    execute = s.sources.execute
    def guarded(action, action_id, **kwargs):
        if action['tool']=='read':
            target = s.sources.resolve(action['args']['target'])
            descendants = {sid for sid,c in cat.items() if c['document_id']==target.get('document_id')
                           and (target.get('unit_id') is None or c['unit_id']==target['unit_id'])}
            if target.get('source_id'): descendants = {target['source_id']}
            if not descendants or descendants-allowed:
                raise graph_module.AccessDenied('native READ would cross the compiled ontology scope')
        return execute(action,action_id,**kwargs)
    s.sources.execute = guarded
    policy['compile_and_install_seconds'] = time.perf_counter()-started
    return policy


@contextmanager
def recall_module(arm, frozen):
    name = 'semantic_runtime.legal_agent.source_recall_global'
    import semantic_runtime.legal_agent.source_recall as baseline
    import semantic_runtime.legal_agent.source_recall_global as global_baseline
    if arm=='baseline': yield baseline; return
    base = frozen/'02_BACKEND/semantic_runtime/legal_agent'
    global_candidate = load(name,base/'source_recall_global.py')
    candidate = load('semantic_runtime.legal_agent.adr0567_recall',base/'source_recall.py')
    sys.modules[name] = global_candidate
    try: yield candidate
    finally: sys.modules[name] = global_baseline


def one(case, arm, generation, graph_path, gm, frozen, out, live):
    out.mkdir(parents=True, exist_ok=False)
    from lawrag.research.experiment_client import ExperimentClient
    from semantic_runtime.legal_agent.source_selection import select_sources
    client = ExperimentClient(ROOT,out/'calls',max_calls=5,max_output_tokens=1536,
                              schema_in_prompt=True,max_repairs=0) if live else None
    r = {'case_id':case['id'],'arm':arm,'status':'incomplete','error':None,'model_calls':0,
         'classifier':None,'policy':None,'fts':[],'usage':[]}
    wall = time.perf_counter()
    try:
        with session(out,generation,case,live) as s:
            # Projection receipts are prepared once during fixture construction,
            # as ingestion would do. Never load all originals per online request.
            cat = read(graph_path.with_name('source-catalogue.json')); r['catalogue'] = cat
            if arm=='graph':
                t = time.perf_counter()
                classifier = client.generate(read(DESIGN/'prompts.json')['classifier'],
                    {'question':case['question'],'purpose_catalogue':read(DESIGN/'ontology.json')['purposes']},
                    read(DESIGN/'schemas.json')['classifier'],phase='purpose-recognition') if live else {'purpose':'APPLICABILITY','confidence':'HIGH','reason':'contract'}
                r['classifier'] = classifier; r['recognition_seconds'] = time.perf_counter()-t
                graph = gm.Graph(graph_path)
                try: r['policy'] = apply_policy(s,graph,gm,classifier,cat)
                finally: graph.close()
            r['pre_recall_seconds'] = time.perf_counter()-wall
            original_rank = s.sources.matcher.fulltext.rank
            def measured_rank(db,terms,allowed=None,limit=None):
                t = time.perf_counter()
                value = original_rank(db,terms,allowed,limit)
                r['fts'].append({'terms':terms,'eligible_scope_count':len(allowed or []),
                                 'returned_ids':value,'seconds':time.perf_counter()-t})
                return value
            s.sources.matcher.fulltext.rank = measured_rank
            with recall_module(arm,frozen) as rm:
                t = time.perf_counter(); record = rm.SourceRecall(s.sources).prepare()
                r['recall_seconds'] = time.perf_counter()-t
            record['evidence'] = s.sources.repo.evidence()
            write(out/'recall.json',record)
            r['read_ids'] = sorted({e['source_id'] for e in record['evidence']})
            r['read_chars'] = sum(len(p['text']) for e in record['evidence'] for p in e['spans'])
            r['read_actions'] = len(record['actions']); r['limits'] = record['limits']
            if not live:
                r['status']='CONTRACT_OK'; r['presented_ids']=[]; r['selected_ids']=[]
            else:
                def invoke(system,data,schema,phase,timeout):
                    return client.generate(system,data,schema,phase=phase)
                t = time.perf_counter()
                selection = select_sources(case['question'],record,invoke,remaining_seconds=480)
                r['selection_seconds'] = time.perf_counter()-t
                write(out/'selection.json',selection)
                r['selected_ids'] = selection['final_ids']
                originals = [e for p in selection['final_packets'] for e in p['evidence']]
                r['presented_ids'] = sorted({e['source_id'] for e in originals})
                t = time.perf_counter()
                schema = read(DESIGN/'schemas.json')['answer']
                schema['properties']['claims']['items']['properties']['source_ids']['items']['enum'] = r['presented_ids'] or ['NO_SOURCE']
                r['answer'] = client.generate(read(DESIGN/'prompts.json')['answer'],
                    {'question':case['question'],'originals':originals},schema,phase='answer')
                r['answer_seconds'] = time.perf_counter()-t
                r['status'] = 'ANSWER'
    except Exception as exc:
        r['status']='ERROR';r['error']={'type':type(exc).__name__,'message':str(exc),
                                       'traceback':traceback.format_exc()}
    r['seconds'] = time.perf_counter()-wall
    if client: r.update(usage=client.usage,model_calls=client.calls)
    write(out/'result.json',r)
    print(json.dumps({'case':case['id'],'arm':arm,'status':r['status'],
                      'read':len(r.get('read_ids',[])),'calls':r['model_calls'],
                      'seconds':round(r['seconds'],2),'error':r['error'] and r['error']['type']},ensure_ascii=False),flush=True)
    return r


def main():
    parser = argparse.ArgumentParser();parser.add_argument('--live',action='store_true')
    parser.add_argument('--contracts',action='store_true');args = parser.parse_args()
    rev = verify();frozen = CANDIDATE/'revisions'/rev['revision_id']/'snapshot'
    gm = load('adr0567_graph',frozen/'02_BACKEND/lawrag/core/investigation_graph.py')
    out = ADR/'artifacts'/('run-001' if args.live else 'native-contracts')
    out.mkdir(exist_ok=False)
    generation = build_fixture(out/'fixture')
    cases = read(DESIGN/'cases.json')['cases']
    with session(out/'catalogue',generation,cases[0],False) as s: cat = catalogue(s)
    create_graph(gm,out/'ontology.sqlite',cat)
    write(out/'source-catalogue.json',cat)
    # Genuine alternate arm order, one call sequence at a time, no shared caches.
    results = []
    for i, case in enumerate(cases if args.live else cases[:1]):
        for arm in (['baseline','graph'] if i%2==0 else ['graph','baseline']):
            r = one(case,arm,generation,out/'ontology.sqlite',gm,frozen,
                    out/'cases'/case['id']/arm,args.live)
            results.append(r);write(out/'partial.json',{'results':results})
    write(out/'result.json',{'status':'complete','classification':'SYNTHETIC','results':results,
          'usage':[u for r in results for u in r['usage']],
          'full_default_request_executed':False,'native_recall_and_selection_executed':True,
          'main_changed':False,'learned_exclusions_from_logs':False})
    if any(r['status']=='ERROR' for r in results): sys.exit(2)


if __name__=='__main__': main()
