"""Post-selection deterministic scoring; product runner never reads grading-only.json."""
from common import *
import sys,statistics,re,collections
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.core.legal_coordinate import find_coordinates
m=read(ADR/'실험/manifest.json');frozen=read(ART/'design-freeze.json')
assert m['design']['success_criteria']==frozen['design']['success_criteria']
assert sha(ART/'grading-only.json')==m['dataset']['grading_only']['sha256']
cases=read(ART/'cases.json');gold={r['case_id']:r for r in read(ART/'grading-only.json')};docs=read(ART/'documents.json')
title_ids={d['title']:d['id'] for d in docs}
universe={(d['id'],f'제{i+1}조') for d in docs for i,_ in enumerate(d['texts'])}
def identities(rows):return {(r['doc_id'],r['node']) for r in rows}
def rows(values):return [{'doc_id':d,'node':n} for d,n in sorted(values)]
def visible(value):
    found=set()
    if isinstance(value,list):
        for item in value:found |= visible(item)
    elif isinstance(value,dict):
        did=value.get('document_id') or title_ids.get(value.get('document'))
        if did and (value.get('target') or value.get('read_action') or value.get('kind')=='structure'):
            text=value.get('coordinate') or value.get('article') or value.get('heading') or value.get('label') or ''
            for mention in find_coordinates(str(text)):
                if mention.coordinate.unit=='조':
                    node=mention.coordinate.replace_chain(()).canonical_surface()
                    if (did,node) in universe:found.add((did,node))
        for key,item in value.items():
            if key not in ('law_name_recovery','already_read','navigation_feedback'):found |= visible(item)
    return found
def stage(plan,before,after,expected,reason):
    added=after-before;discarded=before-after
    out={**plan,'executed':True,'skip_reason':None,'before':rows(before),'added':rows(added),'discarded':rows(discarded),'after':rows(after),
        'before_count':len(before),'added_count':len(added),'discarded_count':len(discarded),'after_count':len(after),
        'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},
        'discard_receipts':[{'identity':r,'reason':reason} for r in rows(discarded)],
        'discard_reason_counts':{reason:len(discarded)} if discarded else {},'gold_total':len(expected),
        'gold_before':len(before&expected),'gold_added':len(added&expected),'gold_discarded':len(discarded&expected),'gold_after':len(after&expected),
        'golden_recall':len(after&expected)/len(expected) if expected else None,
        'gold_before_identities':rows(before&expected),'gold_added_identities':rows(added&expected),'gold_after_identities':rows(after&expected),
        'discarded_gold':[{'identity':r,'reason':reason} for r in rows(discarded&expected)]}
    return out
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],
 'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,
 'runs':[{'run_id':'run-001','arms':[]}],
 'audit':{'identity_scope':'Unique canonical article-root sets; metadata name candidates stay separate and do not establish article presence. Raw repeated model views are retained in trial results; stage accounting uses their unique union.'}}
evaluations={};metrics={};usage=[]
for arm in ('baseline','candidate'):
    trials=[];case_ledgers=[];counts=[];gold_seen=0;denominator=0
    for c in cases:
        value=read(ART/'trials'/c['id']/arm/'result.json');expected=identities(gold[c['id']]['expected'])
        # v8 delivers verified originals without a separate legacy ADOPT/read_scopes record.
        # The frozen metric is original delivery, so use that authoritative result field.
        selected={(r['document_id'],find_coordinates(r['heading'])[0].coordinate.replace_chain(()).canonical_surface()) for r in value['sources']}
        steps=value['state'].get('action_chain',{}).get('steps',[])
        retries=[s for s in steps if s.get('action')=='RETRY_LAW_STRUCTURE']
        lookup_coordinate=find_coordinates(c['lookup'])[0].surface
        retry_preserved=all(s['structure_lookup']['name_retry']['structure_filter']['coordinate']==lookup_coordinate for s in retries)
        scope_ok=all(d in c['scope'] for d,n in selected)
        source_exact=True
        for evidence in value.get('result',{}).get('selected_evidence',[]):
            did=evidence['document_id'];doc=next(d for d in docs if d['id']==did)
            for span in evidence['spans']:
                block=doc['texts'][int(span['block_id'])]
                source_exact &= block[span['start_cp']:span['end_cp']]==span['text']
        success=value['error'] is None and selected==expected and (bool(value['sources']) if expected else not value['sources'])
        trials.append({'case_id':c['id'],'kind':gold[c['id']]['kind'],'pass':success,'expected':rows(expected),'selected':rows(selected),
            'used_name_retry':bool(retries),'coordinate_preserved':retry_preserved,'scope_ok':scope_ok,'original_exact':source_exact,
            'error':value['error'],'model_calls':value['model_calls'],'seconds':value['seconds']})
        initial=visible(value['initial']);investigated=initial | visible(value['observations']) | selected
        stages=[];before=set()
        for plan,after,reason in zip(m['design']['retrieval_stage_plan']['stages_by_arm'][arm],
              [universe,initial,investigated,selected,selected],
              ['SOURCE_INVENTORY','OUTSIDE_INITIAL_STRUCTURAL_RESULT','NOT_IN_SUBSEQUENT_VISIBLE_ROUTES','NOT_SELECTED_FOR_DELIVERY','NOT_DELIVERED']):
            stages.append(stage(plan,before,after,expected,reason));before=after
        case_ledgers.append({'schema_version':'retrieval-stage-ledger-v1','arm_id':arm,'case_id':c['id'],
            'accounting_unit':ledger['accounting_unit'],'computed_post_selection':True,'gold_visible_to_product':False,
            'gold_total':len(expected),'gold_identities':rows(expected),'stages':stages})
        counts.append(len(selected));gold_seen+=len(selected&expected);denominator+=len(expected);usage+=value['usage']
    ordered=sorted(counts)
    aggregate={'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),
        'presented_p95':ordered[round((len(ordered)-1)*.95)],'golden_recall':gold_seen/denominator,'selectivity':statistics.mean(counts)/len(universe)}
    metrics[arm]=aggregate;evaluations[arm]=trials
    ledger['runs'][0]['arms'].append({'arm_id':arm,'declared_stage_ids':[s['stage_id'] for s in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]],'cases':case_ledgers,'aggregate':aggregate})
ledger['artifact_sha256']=hashlib.sha256(json.dumps(ledger,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
save(ART/'retrieval-ledger.json',ledger)
b=evaluations['baseline'];c=evaluations['candidate']
checks={'candidate_minimum_6':sum(r['pass'] for r in c)>=6,
 'candidate_noninferior':sum(r['pass'] for r in c)>=sum(r['pass'] for r in b),
 'three_name_recoveries':sum(r['pass'] and r['used_name_retry'] for r in c[:4])>=3,
 'exact_controls':all(r['pass'] for r in c[4:6]),'no_source_controls':all(r['pass'] for r in c[6:]),
 'all_coordinates_preserved':all(r['coordinate_preserved'] for arm in evaluations.values() for r in arm),
 'all_scopes_preserved':all(r['scope_ok'] for arm in evaluations.values() for r in arm),
 'all_originals_exact':all(r['original_exact'] for arm in evaluations.values() for r in arm),
 'call_budget':sum(r['model_calls'] for arm in evaluations.values() for r in arm)<=128}
comparison=collections.Counter(('both_correct' if a['pass'] and z['pass'] else 'candidate_only' if z['pass'] else 'baseline_only' if a['pass'] else 'both_wrong') for a,z in zip(b,c))
save(ART/'analysis.json',{'strict_success':all(checks.values()),'checks':checks,'by_arm':evaluations,'retrieval':metrics,'comparison':dict(comparison),
 'physical_model_calls':sum(r['model_calls'] for arm in evaluations.values() for r in arm),'usage':usage,
 'classification':'Source navigation/task outcomes; no free-form legal-answer scoring, no LLM judge','criteria_frozen_sha256':sha(ART/'design-freeze.json')})
print(json.dumps({'checks':checks,'correct':{a:sum(r['pass'] for r in v) for a,v in evaluations.items()},'comparison':dict(comparison)},ensure_ascii=False))
