"""Preserve observed rejection/reentry cause without changing frozen product."""
from common import *
P=ART/'known-query/candidate';events=read(P/'events-audit.json')
inputs={}; current=None; rejections=[]; final_reviews=[]
for e in events:
    v=e['payload']
    if e['kind']=='MEMORY_MODEL_INPUT':
        current=v
    if e['kind']=='ASSESSMENT_GAP_REENTRY_PLANNED':
        final_reviews.append({'seq':e['seq'],'kind':e['kind'],'payload':v})
    if e['kind']!='OUTPUT_DECISION_STATE' or v.get('status')!='REJECTED':continue
    ctx=(current or {}).get('data',{}).get('read_judgments',{})
    heads={h['id']:h for h in ctx.get('judgments',[])}
    rows=[]
    for row in v.get('proposal',{}).get('read_review',{}).get('judgments',[]):
        prior=heads.get(row['judgment_id'],{})
        rows.append({'id':row['judgment_id'],'operation':row['operation'],'finding_nonempty':bool(row['finding']),
            'finding_exactly_matches_prior':row['finding']==prior.get('finding'),
            'use_matches_prior':row['use']==prior.get('use'),'has_new_need':bool(row['missing']),
            'heading':prior.get('heading')})
    originals=[{'id':h['id'],'material':sorted(h['material'])} for h in ctx.get('current_originals',[])]
    original_hash=hashlib.sha256(json.dumps(sorted(originals,key=lambda h:h['id']),sort_keys=True).encode()).hexdigest()
    rejections.append({'seq':e['seq'],'phase':(current or {}).get('phase'),'decision_key':v['decision_key'],
        'attempt':v['attempt'],'error':v['error'],'choice':v.get('proposal',{}).get('choice'),
        'source_material_hash':original_hash,'judgments':rows})
report={'rejections':rejections,'reentry_plans':final_reviews,
    'same_error_count':len(rejections),'distinct_decision_keys':len({r['decision_key'] for r in rejections}),
    'distinct_source_material_hashes':len({r['source_material_hash'] for r in rejections}),
    'root_cause':'KEEP validator requires finding empty even for exact repetition of an unchanged prior finding. Prompt asks to write finding and describes KEEP without its empty-field condition; generic repair feedback did not resolve it.',
    'repeat_path':'After first bounded stop, ASSESS requested the still missing97 original. Reentry generated a new decision key with unchanged presented original material; one initial+repair cycle repeated the same KEEP failure.',
    'scope':'Observed execution/schema failure, not an LLM failure to identify the needed original. No fix or second model run in this ADR.',
    'followup':'Prospectively isolate a follow-up to remove redundant KEEP content generation from the wire contract while preserving prior findings/reasons/evidence and audit, and bind same-cause retry budgets across ASSESS reentry.'}
save(ART/'failure-review.json',report)
print(json.dumps({k:v for k,v in report.items() if k not in ('rejections','reentry_plans')},ensure_ascii=False,indent=2))
