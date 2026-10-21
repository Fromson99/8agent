"""Offline exact-set grading; never imported by the product trial runner."""
from common import *
import statistics,collections
m=read(ADR/'실험/manifest.json');f=read(ART/'design-freeze.json')
assert m['design']['success_criteria']==f['design']['success_criteria']
assert sha(ART/'grading-only.json')==m['dataset']['grading_only']['sha256']
cases=read(ART/'cases.json');gold={r['case_id']:r for r in read(ART/'grading-only.json')};docs=read(ART/'documents.json');docmap={d['id']:d for d in docs}
universe={(d['id'],int(n['id'])) for d in docs for n in d['nodes'] if n['parent'] is None}
def articles(blocks):
    out=set()
    for d,b in blocks:
        for n in docmap[d]['nodes']:
            if n['parent'] is None and n['span'][0]<=int(b)<n['span'][1]:out.add((d,int(n['id'])))
    return out
def rows(values):return sorted([{'doc_id':d,'node':n} for d,n in values],key=lambda r:json.dumps(r,sort_keys=True,separators=(',',':')))
def blocks(values):return [{'document_id':d,'block_id':b} for d,b in sorted(values)]
def stage(plan,before,after,expected,reason):
    added=after-before;discarded=before-after
    return {**plan,'executed':True,'skip_reason':None,'before':rows(before),'added':rows(added),'discarded':rows(discarded),'after':rows(after),
      'before_count':len(before),'added_count':len(added),'discarded_count':len(discarded),'after_count':len(after),
      'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},
      'discard_receipts':[{'identity':r,'reason':reason} for r in rows(discarded)],'discard_reason_counts':{reason:len(discarded)} if discarded else {},
      'gold_total':len(expected),'gold_before':len(before&expected),'gold_added':len(added&expected),'gold_discarded':len(discarded&expected),'gold_after':len(after&expected),
      'golden_recall':len(after&expected)/len(expected) if expected else None,'gold_before_identities':rows(before&expected),'gold_added_identities':rows(added&expected),'gold_after_identities':rows(after&expected),
      'discarded_gold':[{'identity':r,'reason':reason} for r in rows(discarded&expected)]}
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':[]}],
 'audit':{'identity_scope':'Unique stored article-root numeric IDs. Exact block-set metrics are primary; article recall cannot certify a range within one article. read stage means source READ consumer, not answer generation or model acknowledgement.'}}
evaluations={};metrics={};usage=[]
for arm in ('baseline','candidate'):
    trials=[];records=[];counts=[];seen=0;denom=0
    for c in cases:
        r=read(ART/'trials'/c['id']/arm/'result.json');g=gold[c['id']]
        expected={(x['document_id'],str(x['block_id'])) for x in g['expected_blocks']};actual={(x['document_id'],str(x['block_id'])) for x in r['blocks']}
        exact=True
        for b in r['blocks']:
            text=docmap[b['document_id']]['texts'][int(b['block_id'])]
            exact &= text[b['start_cp']:b['end_cp']]==b['text'] and b['start_cp']==0 and b['end_cp']==len(text)
        scope_ok=all(d in c['scope'] for d,b in actual)
        negative_ok=g['negative'] and not actual and (r['error'] is None or r['error']['type'] in ('UnresolvedScope','SelectionError'))
        passed=negative_ok or not g['negative'] and r['error'] is None and actual==expected and exact
        item={'case_id':c['id'],'route':c['route'],'kind':g['kind'],'pass':passed,'expected':blocks(expected),'actual':blocks(actual),
            'extra':blocks(actual-expected),'missing':blocks(expected-actual),'original_exact':exact,'scope_ok':scope_ok,'error':r['error'],'model_calls':r['model_calls'],'seconds':r['seconds']}
        trials.append(item);selected=articles(actual);wanted=articles(expected)
        requested=set()
        for p in r['requested_units']:
            node=next(n for n in docmap[p['document_id']]['nodes'] if n['id']==p['unit_id']);requested |= articles({(p['document_id'],str(b)) for b in range(*node['span'])})
        # Direct READ decisions may not carry a separate location operation.
        requested |= selected
        before=set();stages=[]
        for plan,after,reason in zip(m['design']['retrieval_stage_plan']['stages_by_arm'][arm],[universe,requested,selected],['SOURCE_INVENTORY','NOT_SELECTED_BY_STRUCTURED_DECISION','NOT_READ_OR_REJECTED']):
            stages.append(stage(plan,before,after,wanted,reason));before=after
        records.append({'schema_version':'retrieval-stage-ledger-v1','arm_id':arm,'case_id':c['id'],'accounting_unit':ledger['accounting_unit'],'computed_post_selection':True,'gold_visible_to_product':False,'gold_total':len(wanted),'gold_identities':rows(wanted),'stages':stages})
        counts.append(len(selected));seen+=len(selected&wanted);denom+=len(wanted);usage+=r['usage']
    metric={'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':sorted(counts)[round((len(counts)-1)*.95)],'golden_recall':seen/denom if denom else None,'selectivity':statistics.mean(counts)/len(universe)}
    evaluations[arm]=trials;metrics[arm]=metric
    ledger['runs'][0]['arms'].append({'arm_id':arm,'declared_stage_ids':[s['stage_id'] for s in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]],'cases':records,'aggregate':metric})
ledger['artifact_sha256']=hashlib.sha256(json.dumps(ledger,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest();save(ART/'retrieval-ledger.json',ledger)
b=evaluations['baseline'];c=evaluations['candidate']
checks={'minimum_29':sum(x['pass'] for x in c)>=29,'noninferior':sum(x['pass'] for x in c)>=sum(x['pass'] for x in b),
 'critical_cases':all(x['pass'] for x in c if x['kind'] in ('exclusion','single_control','fact_not_read_exclusion','multiple_documents')),
 'no_extra_candidate_blocks':all(not x['extra'] for x in c),'safe_negatives':all(x['pass'] for x in c if x['kind'] in ('missing','empty')),
 'all_originals_exact':all(x['original_exact'] for ts in evaluations.values() for x in ts),
 'all_scopes_preserved':all(x['scope_ok'] for ts in evaluations.values() for x in ts),
 'fixture_valid':read(ART/'fixture-preflight.json')['passed'],
 'budget':sum(x['model_calls'] for ts in evaluations.values() for x in ts)<=128 and all(x['model_calls']<=2 for ts in evaluations.values() for x in ts)}
comparison=collections.Counter('both_correct' if a['pass'] and z['pass'] else 'candidate_only' if z['pass'] else 'baseline_only' if a['pass'] else 'both_wrong' for a,z in zip(b,c))
save(ART/'analysis.json',{'strict_success':all(checks.values()),'checks':checks,'by_arm':evaluations,'retrieval':metrics,'comparison':dict(comparison),'physical_model_calls':sum(x['model_calls'] for ts in evaluations.values() for x in ts),'usage':usage,'criteria_frozen_sha256':sha(ART/'design-freeze.json')})
print(json.dumps({'checks':checks,'correct':{a:sum(r['pass'] for r in ts) for a,ts in evaluations.items()},'comparison':dict(comparison)},ensure_ascii=False))
