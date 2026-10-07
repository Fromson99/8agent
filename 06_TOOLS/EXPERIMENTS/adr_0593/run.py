"""Explicit frozen injection; products complete before gold is loaded."""
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'02_BACKEND'));sys.dont_write_bytecode=True
from lawrag.research.experiment_client import ExperimentClient
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0593-rag-chain-native-kind-repair'
DESIGN=ADR/'artifacts/design'
ARMS=['CURRENT_ONLY','CHAIN']

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))

def load_candidate(cid,arm):
    p=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0593'/cid
    m=json.loads((p/'candidate.json').read_text());r=m['revisions'][-1]
    assert m['arm_id']==arm
    paths={}
    for f in r['files']:
        q=ROOT/f['frozen_path'];assert sha(q)==f['snapshot_sha256']
        paths[f['snapshot_path'].split('/snapshot/',1)[1]]=q
    def load(name,path):
        spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod
    mod=load('adr0593_'+arm,paths['02_BACKEND/semantic_runtime/legal_agent/chain_prototype.py'])
    native=load('semantic_runtime.legal_agent.adr0593_'+arm,paths['02_BACKEND/semantic_runtime/legal_agent/repository.py'])
    mod.NativeRepository=native.WorkRepository
    return mod

def snap(store):
    return {r['id']:{'state':store.goal(r['id']),'heads':{s:(store.head(r['id'],s) or {}).get('id') for s in store_stages()},'route':store.current_route(r['id'])} for r in store.db.execute('SELECT id FROM goal ORDER BY id')}
def store_stages():return ['INTENT','PLAN','RECALL','READ','SELECT','ASSESS','COMPOSE']

def grade(rows,gold):
    grades=[]
    for case in rows:
        spec=gold[case['case_id']];out={'case_id':case['case_id'],'arms':{}}
        for arm,items in case['arms'].items():
            checks=[]
            for key,expected in spec['checkpoints'].items():
                item=items[int(key)-1];o=item['observed'];config=o.get('config') or {};answer=o.get('answer') or {};assessment=o.get('assessment') or {}
                for field,value in expected.items():
                    observed=answer.get('procedure') if field=='procedure' else assessment.get('needs_check') if field=='needs_check' else ('|' in answer.get('text','') and '\n' in answer.get('text','')) if field=='table' else config.get(field)
                    checks.append({'turn':int(key),'field':field,'expected':value,'observed':observed,'pass':observed==value})
            if spec.get('must_backtrack_turn'):
                o=items[spec['must_backtrack_turn']-1]['observed']
                checks.append({'turn':spec['must_backtrack_turn'],'field':'original_turn_used','expected':True,'observed':1 in (o.get('command') or {}).get('original_refs',[]),'pass':1 in (o.get('command') or {}).get('original_refs',[])})
            for turn in spec.get('presentation_turns',[]):
                prev=items[turn-2]['snapshots'].get('G1',{}).get('heads',{});now=items[turn-1]['snapshots'].get('G1',{}).get('heads',{})
                ok=all(prev.get(s)==now.get(s) and prev.get(s) is not None for s in store_stages()[:-1]) and items[turn-1]['observed'].get('executed')==['COMPOSE']
                checks.append({'turn':turn,'field':'presentation_preserves_upstream','expected':True,'observed':ok,'pass':ok})
            if spec.get('preserve_goal'):
                a,b=spec['preserve_between'];gid=spec['preserve_goal'];before=items[a-1]['snapshots'][gid]['heads'];after=items[b-1]['snapshots'][gid]['heads'];ok=before==after
                checks.append({'field':'unrelated_goal_preserved','expected':True,'observed':ok,'pass':ok})
            if spec.get('wiki_target'):
                gid=spec['preserve_bundle'];ok=items[1]['snapshots'][gid]['heads']==items[-1]['snapshots'][gid]['heads']
                checks.append({'field':'other_bundle_preserved','expected':True,'observed':ok,'pass':ok})
                link=case['structural'][arm]['links'];ok=next((r['bundle']==spec['wiki_target'] for r in link if r['intent']==spec['wiki_target']),False)
                checks.append({'field':'wiki_link_fixed','expected':True,'observed':ok,'pass':ok})
            if spec.get('reuse_required'):
                ok=any(i['observed'].get('status')=='REUSED' for i in items)
                checks.append({'field':'actual_next_request_consumption','expected':True,'observed':ok,'pass':ok})
            if spec.get('fault_turn'):
                item=items[spec['fault_turn']-1];s=item['snapshots']['G1'];ok=item['observed']['status']=='ERROR' and s['state']['status']=='PENDING' and s['route'] is None
                checks.append({'field':'failed_correction_blocks_old_route','expected':True,'observed':ok,'pass':ok})
            if spec.get('reingest_required'):
                audit=items[-1]['observed'].get('reingest') or {};ok=bool(audit.get('blocked_retired')) and audit.get('ontology_route')==items[-1]['observed'].get('route_id')
                checks.append({'field':'old_intake_does_not_resurrect','expected':True,'observed':ok,'pass':ok})
            structural=case['structural'][arm]
            for field in ['closed_routes','stale_publication_blocked','native_dependency_recorded','single_active_route_per_goal']:
                checks.append({'field':field,'expected':True,'observed':structural[field],'pass':structural[field]})
            out['arms'][arm]={'checks':checks,'passed':sum(c['pass'] for c in checks),'total':len(checks),'all_pass':all(c['pass'] for c in checks)}
        grades.append(out)
    return grades

def ledger(rows,gold,manifest):
    plans=manifest['design']['retrieval_stage_plan']['stages_by_arm'];arms=[];summary={}
    identities=lambda values:sorted([{'doc_id':s.rsplit('/',1)[0],'node':{'main':1,'exception':2,'documents':3}[s.rsplit('/',1)[1]]} for s in set(values)],key=canonical)
    for arm in ARMS:
        cases=[];counts=[];goldhit=goldtotal=0;bef=filtered=0
        for case in rows:
            # Canonical ledger is final consumed-route snapshot, not sum of repeat reads.
            trace=next((i['observed']['retrieval'] for i in reversed(case['arms'][arm]) if i['observed'].get('retrieval')),{'source':[],'scope':[],'query':[],'selected':[],'present':[]})
            gids=set(gold[case['case_id']]['gold_sources']);stages=[];previous=set()
            for plan in plans[arm]:
                sid=plan['stage_id'];after=set(trace[sid]);before=set(previous);added=after-before;discarded=before-after
                reason={'scope':'outside_current_scope','query':'outside_query_plan','selected':'not_selected_by_model','present':'not_presented','source':'source_catalogue'}[sid]
                receipts=[{'identity':x,'reason':reason} for x in identities(discarded)]
                row={**plan,'executed':True,'skip_reason':None,'before':identities(before),'added':identities(added),'discarded':identities(discarded),'after':identities(after),
                    'before_count':len(before),'added_count':len(added),'discarded_count':len(discarded),'after_count':len(after),
                    'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},'discard_receipts':receipts,'discard_reason_counts':{reason:len(discarded)} if discarded else {},
                    'gold_total':len(gids),'gold_before':len(before&gids),'gold_added':len(added&gids),'gold_discarded':len(discarded&gids),'gold_after':len(after&gids),'golden_recall':len(after&gids)/len(gids),
                    'gold_before_identities':identities(before&gids),'gold_added_identities':identities(added&gids),'gold_after_identities':identities(after&gids),'discarded_gold':[{'identity':x,'reason':reason} for x in identities(discarded&gids)]}
                stages.append(row);previous=after
            cases.append({'schema_version':'retrieval-stage-ledger-v1','arm_id':arm,'case_id':case['case_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'gold_total':len(gids),'gold_identities':identities(gids),'stages':stages})
            counts.append(len(previous));goldhit+=len(previous&gids);goldtotal+=len(gids);bef+=len(trace['source']);filtered+=len(trace['query'])
        summary[arm]={'before_filter':bef,'after_filter':filtered,'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':sorted(counts)[round((len(counts)-1)*.95)],'golden_recall':goldhit/goldtotal,'selectivity':statistics.mean(counts)/6}
        arms.append({'arm_id':arm,'declared_stage_ids':[p['stage_id'] for p in plans[arm]],'cases':cases,'aggregate':summary[arm]})
    data={'schema_version':'retrieval-stage-ledger-v1','adr_id':'ADR-0593','experiment_id':'ADR-0593-experiment-v1','accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':arms}],'audit':{'scope':'Final available/consumed route of each sequence; per-turn before/after and exact model inputs are separate products','sources':'six synthetic units; no real article corpus','canonical_identity_mapping':{'main':1,'exception':2,'documents':3}}}
    data['artifact_sha256']=hashlib.sha256(canonical(data).encode()).hexdigest()
    return data,summary

def main():
    for name,h in json.loads((DESIGN/'freeze.json').read_text()).items():
        if sha(ROOT/name)!=h:raise RuntimeError('frozen design/runner drift: '+name)
    run=ADR/'artifacts/run-001'
    if run.exists():raise RuntimeError('run exists; no overwrite or hidden repeat')
    run.mkdir();client=ExperimentClient(ROOT,run/'provider',max_calls=320,max_output_tokens=1400,max_repairs=0)
    inputs=json.loads((DESIGN/'inputs.json').read_text());docs=json.loads((DESIGN/'RAW/documents.json').read_text())
    modules={a:load_candidate('stage-chain' if a=='CHAIN' else 'current-context',a) for a in ARMS}
    rows=[]
    for ci,product in enumerate(inputs):
        cid=product['case_id'];row={'case_id':cid,'arms':{},'structural':{}}
        for arm in (ARMS if ci%2==0 else list(reversed(ARMS))):
            folder=run/cid/arm;turnno=0;call_no=0
            def invoke(system,data,schema,phase):
                nonlocal call_no
                call_no+=1
                return client.generate(system,data,schema,phase=f'{cid}-{arm}-t{turnno:02d}-{call_no:03d}-{phase}')
            mod=modules[arm];store=mod.ChainStore(folder,docs,invoke,history=arm=='CHAIN');observations=[]
            for ti,turn in enumerate(product['turns'],1):
                turnno=ti;started=time.perf_counter()
                try:observed=store.process(turn)
                except Exception as e:
                    g=store.goal(turn['goal'])
                    observed={'status':'ERROR','error_type':type(e).__name__,'error':str(e),'config':g and g['config'],'executed':list(store.executed)}
                item={'turn':ti,'product_input':turn,'observed':observed,'seconds':time.perf_counter()-started,'snapshots':snap(store)}
                write(folder/f'turn-{ti:02d}.json',item);observations.append(item)
                print(json.dumps({'case':cid,'arm':arm,'turn':ti,'total':len(product['turns']),'status':observed['status'],'executed':observed.get('executed',[]),'procedure':(observed.get('answer') or {}).get('procedure')},ensure_ascii=False),flush=True)
            routes=[dict(r) for r in store.db.execute("SELECT * FROM route WHERE status='ACTIVE'")]
            closed=True
            for r in routes:
                ids=set(json.loads(r['manifest'])['nodes'])
                closed=closed and all(set(store.node(n)['parents'])<=ids for n in ids)
            stale_blocked=True
            for r in routes:
                try:store.publish_guard(r['goal'],r['revision']-1);stale_blocked=False
                except mod.GuardError:pass
            native_edges=0
            import sqlite3
            for p in folder.glob('journals/*/journal.sqlite'):
                db=sqlite3.connect(p);native_edges+=db.execute('SELECT COUNT(*) FROM dependency').fetchone()[0];db.close()
            structural={'closed_routes':closed and bool(routes),'stale_publication_blocked':stale_blocked and bool(routes),'native_dependency_recorded':native_edges>0,'native_edge_count':native_edges,'single_active_route_per_goal':all(v[0]==1 for v in store.db.execute("SELECT COUNT(*) FROM route WHERE status='ACTIVE' GROUP BY goal")),'links':[dict(r) for r in store.db.execute('SELECT * FROM link')],'active_routes':routes}
            write(folder/'structural.json',structural);row['structural'][arm]=structural;row['arms'][arm]=observations;store.close()
        rows.append(row);write(run/'product-progress.json',rows)
    # Products and context are now immutable; gold is first read below.
    gold=json.loads((DESIGN/'gold.json').read_text());grades=grade(rows,gold)
    m=json.loads((ADR/'실험/manifest.json').read_text());accounting,summary=ledger(rows,gold,m)
    write(run/'retrieval-stage-ledger.json',accounting)
    by_arm={a:{'checks_passed':sum(g['arms'][a]['passed'] for g in grades),'checks_total':sum(g['arms'][a]['total'] for g in grades),'sequences_passed':sum(g['arms'][a]['all_pass'] for g in grades),'sequences_total':len(grades),'runtime_errors':sum(i['observed']['status']=='ERROR' for r in rows for i in r['arms'][a])} for a in ARMS}
    paired={k:0 for k in ['candidate_only','baseline_only','both_correct','both_incorrect']}
    for g in grades:
        a=g['arms']['CURRENT_ONLY']['all_pass'];b=g['arms']['CHAIN']['all_pass'];paired['both_correct' if a and b else 'candidate_only' if b else 'baseline_only' if a else 'both_incorrect']+=1
    usage={'calls':len(client.usage),'input_tokens':sum(u.get('input_tokens',0) or 0 for u in client.usage),'output_tokens':sum(u.get('output_tokens',0) or 0 for u in client.usage),'reported_cost_usd':sum(u.get('usage',{}).get('cost',0) or 0 for u in client.usage),'reasoning_tokens':sum(u.get('reasoning_tokens',0) or 0 for u in client.usage)}
    latencies={a:{'p50':statistics.median(v:=[i['seconds'] for r in rows for i in r['arms'][a]]),'p95':sorted(v)[min(len(v)-1,int(.95*len(v)))]} for a in ARMS}
    result={'schema_version':'rag-chain-sequential-probe-v1','run_id':'run-001','data_kind':'SYNTHETIC','products':rows,'grades':grades,'summary':{'by_arm':by_arm,'paired':paired,'usage':usage,'turn_latency_seconds':latencies,'retrieval':summary},'limits':m['design']['limits']}
    write(run/'result.json',result)
    print(json.dumps(result['summary'],ensure_ascii=False),flush=True)

if __name__=='__main__':main()
