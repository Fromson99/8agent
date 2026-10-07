"""Prospective compact catalogue concept IDs and small complete-pool selection."""
from contextlib import contextmanager
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0570-provider503-frozen-replay'
DESIGN=ADR/'artifacts/design'
CANDIDATES={arm:ROOT/'02_BACKEND/lawrag/research/candidates/adr_0569/combined' for arm in ['baseline','replay']}
ARMS=['baseline','replay']
sys.dont_write_bytecode=True
for p in [ROOT/'02_BACKEND',ROOT/'05_TESTS',ROOT/'05_TESTS/CONTRACTS']:
    sys.path.insert(0,str(p))

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
parent=load('adr0570_frozen_fixture_helpers',ROOT/'06_TOOLS/EXPERIMENTS/adr_0567/run.py')
parent.ADR=ADR;parent.DESIGN=DESIGN
read=parent.read;write=parent.write;sha=parent.sha
build_fixture=parent.build_fixture;session=parent.session;catalogue=parent.catalogue;create_graph=parent.create_graph

def verify():
    m=read(ADR/'실험/manifest.json')
    if not m['design']['criteria_frozen_before_run']:raise ValueError('design not frozen')
    for p,h in m['design']['frozen_inputs'].items():
        if sha(ROOT/p)!=h:raise ValueError('frozen input drift: '+p)
    for p,h in read(DESIGN/'code-pins.json').items():
        if sha(ROOT/p)!=h:raise ValueError('baseline drift: '+p)
    for ci in m['design']['code_isolation']['candidates']:
        if sha(ROOT/ci['manifest_path'])!=ci['manifest_sha256']:raise ValueError('candidate drift')
    frozen={}
    for arm,path in CANDIDATES.items():
        rev=read(path/'candidate.json')['revisions'][-1]
        for f in rev['files']:
            if sha(ROOT/f['frozen_path'])!=f['snapshot_sha256']:raise ValueError('revision drift')
        frozen[arm]=path/'revisions'/rev['revision_id']/'snapshot'
    return frozen

def modules(frozen):
    return {'graph':load('adr0570_graph',frozen/'02_BACKEND/lawrag/core/investigation_graph.py'),
        'scope':load('adr0570_scopes',frozen/'02_BACKEND/lawrag/core/investigation_actions.py'),
        'plan':load('semantic_runtime.legal_agent.adr0570_plan',frozen/'02_BACKEND/semantic_runtime/legal_agent/source_query_planning.py'),
        'fts':load('semantic_runtime.adr0570_fulltext',frozen/'02_BACKEND/semantic_runtime/fulltext.py'),
        'selection':load('semantic_runtime.legal_agent.adr0570_selection',
            frozen/'02_BACKEND/semantic_runtime/legal_agent/source_selection.py' if (frozen/'02_BACKEND/semantic_runtime/legal_agent/source_selection.py').exists() else ROOT/'02_BACKEND/semantic_runtime/legal_agent/source_selection.py')}

@contextmanager
def recall_module(arm,frozen):
    import semantic_runtime.legal_agent.source_recall as baseline
    import semantic_runtime.legal_agent.source_recall_global as global_baseline
    name='semantic_runtime.legal_agent.source_recall_global';root=frozen/'02_BACKEND/semantic_runtime/legal_agent'
    global_candidate=load(name,root/'source_recall_global.py')
    candidate=load('semantic_runtime.legal_agent.adr0570_recall',root/'source_recall.py')
    sys.modules[name]=global_candidate
    try:yield candidate
    finally:sys.modules[name]=global_baseline

def projection(generation,out):
    path=generation/'fulltext/fulltext.sqlite'
    # Metadata-only generation binding, prepared offline, no per-request corpus READ.
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        rows={sid:rowid for rowid,sid in db.execute('SELECT rowid,source_id FROM source_fts')}
    write(out/'fts-projection.json',{'fulltext_sha256':sha(path),'source_rowids':rows})

def planned(client,s,case,arm,m):
    names=sorted({name for did,name in s.sources.matcher.documents.items() if did in s.sources.scope})
    data={'question':case['question'],'law_names':names,'capabilities':m['plan'].CAPABILITIES}
    concepts=read(DESIGN/'concept-catalogue.json');ids=[c['id'] for c in concepts]
    data['investigation_concepts']=concepts
    schema=m['plan'].action_catalogue_schema(names,ids);system=m['plan'].ACTION_SYSTEM
    plan=client.generate(system,data,schema,phase='source-query-plan')
    m['plan'].validate_action_catalogue(plan,names,ids)
    return plan

def prepare_scopes(s,m,cat,graph_path,actions):
    g=m['graph'].Graph(graph_path)
    try:scopes=m['scope'].ActionScopes(g,m['graph'],cat,s.sources.scope,actions)
    finally:g.close()
    scopes.install(s.sources,cat)
    return scopes

def one(case,arm,generation,out,assets,m,frozen,live):
    from lawrag.research.experiment_client import ExperimentClient
    select_sources=m['selection'].select_sources
    from semantic_runtime.fulltext import expression
    out.mkdir(parents=True,exist_ok=False)
    client=ExperimentClient(ROOT,out/'calls',max_calls=4,max_output_tokens=1536,
        schema_in_prompt=True,max_repairs=0) if live else None
    r={'case_id':case['id'],'arm':arm,'status':'incomplete','error':None,'fts':[],
       'classifier':None,'policy':None,'usage':[],'model_calls':0,'standalone_purpose_calls':0}
    wall=time.perf_counter()
    try:
        with session(out,generation,case,live) as s:
            cat=read(assets/'source-catalogue.json');r['catalogue']=cat
            t=time.perf_counter()
            if live:plan=planned(client,s,case,arm,m)
            else:
                qs=case['query_plan']['queries']
                plan={'mode':'SEARCH','queries':qs,'law_names':[]}
                plan['query_concepts']=['purpose:applicable']*len(qs)
            r['plan']=plan;r['plan_seconds']=time.perf_counter()-t
            if plan['mode'] not in ('SEARCH','BROWSE'):raise ValueError('frozen source question incorrectly routed')
            if plan['mode']=='BROWSE':
                a={'tool':'browse','args':{'target':s.sources.root,'relation':'self','view':'children','depth':1,'cursor':None},
                    'reason':'실제 문서 목록·종류 확인','question_refs':['Q1'],'expected_information':'현재 허용된 문서 목록'}
                r['browse']=s.sources.execute(a,'catalogue-browse',actor='SYSTEM_POLICY')
                # Shared source-stage continuation for explicit example originals.
                s.sources.recall_query_plan={'law_names':[],'queries':[case['question']]}
            else:s.sources.recall_query_plan={k:plan[k] for k in ('law_names','queries')}
            r['effective_query_plan']=s.sources.recall_query_plan
            scopes=None
            t=time.perf_counter()
            actions=m['plan'].as_actions(plan)
            r['normalized_actions']=actions
            scopes=prepare_scopes(s,m,cat,assets/'ontology.sqlite',actions)
            r['policy']=scopes.receipt();r['scope_seconds']=time.perf_counter()-t
            proj=read(assets/'fts-projection.json')
            if proj['fulltext_sha256']!=s.sources.matcher.fulltext.manifest['fulltext_sha256']:
                raise ValueError('stale backend rowid projection')
            index=s.sources.matcher.fulltext;original_rank=index.rank
            def measured(db,terms,allowed=None,limit=None):
                t=time.perf_counter();rowids=None
                if allowed is None:raise ValueError('compiled source scope required before SQL')
                rowids=[proj['source_rowids'][sid] for sid in sorted(allowed)]
                value=m['fts'].FulltextIndex.rank(index,db,terms,allowed,limit,eligible_rowids=rowids)
                weights=index.manifest['ranking']['bm25_weights']
                rank=f"bm25(0,{float(weights['heading'])},{float(weights['body'])})"
                sql='SELECT source_id,rank FROM source_fts WHERE source_fts MATCH ? AND rank MATCH ?'
                params=[expression(terms),rank]
                if rowids is not None:
                    sql+=' AND rowid IN ('+','.join('?' for _ in rowids)+')';params+=rowids
                sql+=' ORDER BY rank'
                # EXPLAIN is plan inspection; does not run a second ranked search.
                queryplan=[row[3] for row in db.execute('EXPLAIN QUERY PLAN '+sql,params)] if rowids!=[] else []
                r['fts'].append({'terms':terms,'eligible_scope_count':len(allowed or []),'returned_ids':value,
                    'seconds':time.perf_counter()-t,'sql_scope_applied':rowids is not None,
                    'sql':sql,'scope_rowids':rowids,'query_plan':queryplan})
                return value
            index.rank=measured
            try:
                with recall_module(arm,frozen) as rm:
                    t=time.perf_counter();record=rm.SourceRecall(s.sources).prepare();r['recall_seconds']=time.perf_counter()-t
            finally:index.rank=original_rank  # shared cached object restored even on failure
            record['evidence']=s.sources.repo.evidence();record['query_plan']=s.sources.recall_query_plan
            write(out/'recall.json',record)
            r.update(read_ids=sorted({e['source_id'] for e in record['evidence']}),
                     read_chars=sum(len(p['text']) for e in record['evidence'] for p in e['spans']),
                     read_actions=len(record['actions']),limits=record['limits'])
            if not live:r.update(status='CONTRACT_OK',selected_ids=[],presented_ids=[])
            else:
                def invoke(system,data,schema,phase,timeout):return client.generate(system,data,schema,phase=phase)
                t=time.perf_counter();selection=select_sources(case['question'],record,invoke,remaining_seconds=480)
                r['selection_seconds']=time.perf_counter()-t;write(out/'selection.json',selection)
                r['selected_ids']=selection['final_ids']
                originals=[e for p in selection['final_packets'] for e in p['evidence']]
                r['presented_ids']=sorted({e['source_id'] for e in originals})
                schema=read(DESIGN/'schemas.json')['answer']
                schema['properties']['claims']['items']['properties']['source_ids']['items']['enum']=r['presented_ids'] or ['NO_SOURCE']
                t=time.perf_counter();r['answer']=client.generate(read(DESIGN/'prompts.json')['answer'],
                    {'question':case['question'],'originals':originals},schema,phase='answer')
                r['answer_seconds']=time.perf_counter()-t;r['status']='ANSWER'
    except Exception as exc:r.update(status='ERROR',error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()})
    r['seconds']=time.perf_counter()-wall
    if client:r.update(model_calls=client.calls,usage=client.usage)
    write(out/'result.json',r)
    print(json.dumps({'case':case['id'],'arm':arm,'status':r['status'],'reads':len(r.get('read_ids',[])),
        'calls':r['model_calls'],'seconds':round(r['seconds'],2),'error':r['error'] and r['error']['type']},ensure_ascii=False),flush=True)
    return r

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');parser.add_argument('--contracts',action='store_true')
    args=parser.parse_args();frozen=verify();m={arm:modules(path) for arm,path in frozen.items()}
    out=ADR/'artifacts'/('run-001' if args.live else 'native-contracts');out.mkdir(exist_ok=False)
    generation=build_fixture(out/'fixture');cases=read(DESIGN/'cases.json')['cases']
    with session(out/'catalogue',generation,cases[0],False) as s:cat=catalogue(s)
    write(out/'source-catalogue.json',cat);create_graph(m['baseline']['graph'],out/'ontology.sqlite',cat);projection(generation,out)
    results=[]
    for i,case in enumerate(cases if args.live else cases[:1]):
        order=ARMS[i%3:]+ARMS[:i%3]
        for arm in order:
            results.append(one(case,arm,generation,out/'cases'/case['id']/arm,out,m[arm],frozen[arm],args.live))
            write(out/'partial.json',{'results':results})
    write(out/'result.json',{'status':'complete','classification':'SYNTHETIC','results':results,
        'usage':[u for r in results for u in r['usage']],'main_changed':False,
        'existing_catalogue_call_executed':args.live,'standalone_purpose_calls':0,
        'full_default_request_executed':False,'native_recall_and_selection_executed':True})
    if any(r['status']=='ERROR' for r in results):sys.exit(2)

if __name__=='__main__':main()
