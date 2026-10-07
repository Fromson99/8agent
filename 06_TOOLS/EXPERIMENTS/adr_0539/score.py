"""Offline-only scorer for the frozen ADR-0539 query-planning probe."""
import hashlib
import json
from pathlib import Path
import sqlite3
import statistics

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'00_SYSTEM/WORKSPACE.json').is_file())
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-0539-reverse-hints-before-fulltext'


def read(path):
    return json.loads(path.read_text())


def write(path, data):
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def sorted_ids(ids):
    return sorted(ids,key=canonical)


def stage(stage_id,kind,parents,before,after,gold,reason):
    prior = {canonical(x):x for x in before}
    current = {canonical(x):x for x in after}
    added = {} if parents else current
    if not parents:
        prior={}
    discarded = {k:v for k,v in prior.items() if k not in current}
    gold_map={canonical(x):x for x in gold}
    gb={k:v for k,v in prior.items() if k in gold_map}
    ga={k:v for k,v in added.items() if k in gold_map}
    gd={k:v for k,v in discarded.items() if k in gold_map}
    gh={k:v for k,v in current.items() if k in gold_map}
    return {'stage_id':stage_id,'kind':kind,'parent_stage_ids':parents,
            'executed':True,'skip_reason':'','before':sorted_ids(prior.values()),
            'added':sorted_ids(added.values()),'discarded':sorted_ids(discarded.values()),
            'after':sorted_ids(current.values()),'before_count':len(prior),'added_count':len(added),
            'discarded_count':len(discarded),'after_count':len(current),
            'occurrence_counts':{'before':len(prior),'after':len(current),
                                 'canonical_collapsed_before':0,'canonical_collapsed_after':0},
            'discard_receipts':[{'identity':v,'reason':reason} for v in sorted_ids(discarded.values())],
            'discard_reason_counts':{reason:len(discarded)} if discarded else {},
            'gold_total':len(gold),'gold_before':len(gb),'gold_added':len(ga),
            'gold_discarded':len(gd),'gold_after':len(gh),
            'golden_recall':len(gh)/len(gold) if gold else None,
            'gold_before_identities':sorted_ids(gb.values()),
            'gold_added_identities':sorted_ids(ga.values()),
            'discarded_gold':[{'identity':v,'reason':reason} for v in sorted_ids(gd.values())],
            'gold_after_identities':sorted_ids(gh.values())}


def main():
    design=read(ADR/'artifacts/frozen-design.json')
    result=read(ADR/'artifacts/run-001/result.json')
    targets=read(ADR/'artifacts/offline-targets.json')['targets']
    scope=set(read(ROOT/design['product_cases'])['public_scope_document_ids'])
    generation=ROOT/result['generation']
    db=sqlite3.connect('file:'+str((generation/'navigation/navigation.sqlite').resolve())+'?mode=ro',uri=True)
    maps={}
    for sid,did,raw in db.execute('SELECT id,document_id,json FROM source'):
        if did not in scope:
            continue
        unit=json.loads(raw).get('unit_id')
        if unit is not None and str(unit).isdigit():
            maps[sid]={'doc_id':did,'node':int(unit)}
    db.close()
    corpus=sorted_ids(maps.values())
    arms=[]
    scores={}
    for arm in ('baseline','hint-plan'):
        cases=[]; counts=[]; gold8=gold64=0; tokens=[];seconds=[];cost=0
        for cid in design['case_order']:
            item=result['cases'][cid]['arms'][arm]
            target_ids=targets[cid]
            if not all(x in maps for x in target_ids):
                raise ValueError('offline target missing from frozen corpus')
            gold=sorted_ids(maps[x] for x in target_ids)
            broad=sorted_ids(maps[x] for x in item['top64_union'] if x in maps)
            protected=sorted_ids(maps[x] for x in item['protected_union'] if x in maps)
            stages=[stage('public-corpus','source',[],[],corpus,gold,''),
                    stage('query-top64','retrieve',['public-corpus'],corpus,broad,gold,'outside_query_top64'),
                    stage('protected-top8','present',['query-top64'],broad,protected,gold,'outside_query_top8')]
            cases.append({'schema_version':'retrieval-stage-ledger-v1','case_id':cid,
                          'arm_id':arm,'accounting_unit':'case_id + canonical article-root coordinate',
                          'computed_post_selection':True,'gold_visible_to_product':False,
                          'gold_total':len(gold),'gold_identities':gold,'stages':stages})
            counts.append(len(protected));gold8+=stages[-1]['gold_after'];gold64+=stages[-2]['gold_after']
            usage=item['usage'][0];tokens.append(usage['input_tokens']);seconds.append(usage['seconds'])
            cost+=usage['cost_usd']
        arms.append({'arm_id':arm,'declared_stage_ids':['public-corpus','query-top64','protected-top8'],
                     'cases':cases,'aggregate':{'case_count':len(cases),'note':'Public canonical article roots; two public non-coordinate source rows excluded from ledger identity set.'}})
        scores[arm]={'protected_gold':gold8,'top64_gold':gold64,'gold_total':sum(len(targets[c]) for c in design['case_order']),
                     'presented_counts':counts,'presented_total':sum(counts),'presented_mean':statistics.mean(counts),
                     'presented_p50':statistics.median(counts),
                     'presented_p95':sorted(counts)[min(len(counts)-1,round((len(counts)-1)*.95))],
                     'input_tokens':sum(tokens),'call_latency_p50_seconds':statistics.median(seconds),
                     'call_latency_p95_seconds':sorted(seconds)[min(len(seconds)-1,round((len(seconds)-1)*.95))],
                     'cost_usd':cost,'physical_calls':len(cases)}
    ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':'ADR-0539',
            'experiment_id':'ADR-0539-experiment-v1','accounting_unit':'case_id + canonical article-root coordinate',
            'computed_post_selection':True,'gold_visible_to_product':False,
            'runs':[{'run_id':'run-001','arms':arms}],
            'audit':{'public_source_count':len(maps)+2,'canonical_source_count':len(maps),
                     'gold_source':'artifacts/offline-targets.json, joined only after model calls'}}
    ledger['artifact_sha256']=sha(ledger)
    write(ADR/'artifacts/run-001/retrieval-stage-ledger.json',ledger)
    write(ADR/'artifacts/run-001/scores.json',scores)
    print(json.dumps(scores,ensure_ascii=False))


if __name__=='__main__':
    main()
