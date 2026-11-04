"""Read-only post-run evidence retention audit; no product or model calls."""
from common import *
from collections import Counter

rows=[]
for case in read(DES/'live-cases.json'):
    cid=case['id'];base=ART/'public-live'/(cid+'-bounded')
    if not (base/'resource-final.json').exists():continue
    trace=read(ART/(cid+'-navigation-trace.json.gz'))
    records=read(ART/(cid+'-inspection-records.json.gz'))
    frames=[]
    for p in sorted((base/'canonical').glob('[0-9][0-9][0-9].json.gz')):
        item=read(p);v=item['view'];outp=p.with_name(p.name.replace('.json.gz','-output.json.gz'))
        out=read(outp) if outp.exists() else None
        frames.append({'number':int(p.name[:3]),'stage':v.get('source_stage',item['phase']),
            'sources':[{'id':s.get('id'),'source_id':s.get('source_id'),'heading':s.get('heading'),
                'article_complete':s.get('article_complete'),'evidence_refs':s.get('evidence_refs',[]),
                'block_ids':list(dict.fromkeys(str(x.get('block_id')) for x in s.get('spans',[])))} for s in v.get('sources',[])],
            'evidence_options_count':len(v.get('evidence_options',[])),
            'investigation_stop_reason':v.get('investigation_stop_reason'),
            'finish_connection_review':v.get('finish_connection_review'),
            'repair_feedback':v.get('repair_feedback'),
            'output':None if out is None else {k:out[k] for k in ('choice','directive','reason','remaining_scope','claims','gaps','answer_progress') if k in out}})
    events=[e for e in trace['events'] if any(t in e['kind'] for t in ('SUPERVIS','ASSESS','REJECT','HANDOFF'))]
    row={'case_id':cid,'frames':frames,'events':events,
        'event_counts':dict(Counter(e['kind'] for e in trace['events'])),
        'saved_assessments':records['assessments'],
        'interpretation_rule':'Original acquisition, delivery, semantic acceptance, structural validation and publication are separate. Original-only output is not deletion; page stop is not supervisor semantic rejection.'}
    ref=write_raw_json(ART/(cid+'-retention-audit.json.gz'),row)
    rows.append({'case_id':cid,'raw':ref,'event_counts':row['event_counts'],
        'supervisor_calls':sum('supervisor' in f['stage'] for f in frames),
        'assessment_calls':sum('assess' in f['stage'] for f in frames),
        'saved_assessment_count':len(records['assessments']),
        'final_claim_counts':[len(x['assessment'].get('claims',[])) for x in records['assessments']]})
historical=[]
for path,note in [
 ('09_ARTIFACTS/AUDITS/20261104-assessment-direct-live/실제질문_멀티턴_실험결과.txt','ADR1325: 365 original acquired; extra unrelated paragraph included in USE scope; repeated SCOPE_USE_UNSUPPORTED_RANGE; source-only fallback, no original deletion.'),
 ('04_EXPERIMENTS/ADR/ADR-1341-page-cycle-charter-live/artifacts/semantic-review.json','ADR1341: 434 not acquired; supervisor accepted wrong general-rule application; final SCOPE_CLAIM_EVIDENCE twice. Not an example with all required originals found.')]:
    p=ROOT/path;historical.append({'path':path,'sha256':sha(p),'note':note,'new_model_calls':0})
put(ART/'retention-audit-summary.json',{'cells':rows,'historical':historical,'product_changes':0,'new_model_calls':0})
print(json.dumps(rows,ensure_ascii=False))
