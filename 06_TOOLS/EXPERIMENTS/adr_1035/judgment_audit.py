"""Offline retained-judgment audit. Does not load the corpus or call a model."""
from common import *
from collections import Counter
P=ART/'known-query/candidate'
calls=read(P/'calls-audit.json'); events=read(P/'events-audit.json')
commits=[e for e in events if e['kind']=='READ_JUDGMENT_RECORDED']
heads={}; transitions=[]
for e in commits:
    v=e['payload']; rows=[]
    for change in v['changes']:
        before=change['previous']; after=change['current']; jid=after['id']
        rows.append({'id':jid,'previous_matches_prior_commit':before==heads.get(jid),
            'previous_version':(before or {}).get('version'),'version':after['version'],
            'document_name':after.get('document_name'),'heading':after.get('heading'),
            'use':after['use'],'finding':after['finding'],'reason':after['reason']})
        heads[jid]=after
    transitions.append({'seq':e['seq'],'key':v['key'],'choice':v['choice'],'changes':rows,
        'review':v['review'],'next_actions':v['next_actions'],
        'additional_model_call':v['additional_model_call']})
views=[]; previous_ids=set(); previous_needs=set(); previous_conflicts=set()
for c in calls:
    ctx=c.get('read_judgments')
    if ctx is None:continue
    ids={h['id'] for h in ctx['judgments']}; needs={n['id'] for n in ctx['needs']}; conflicts={n['id'] for n in ctx['conflicts']}
    proposal=c['proposal']; review=proposal.get('read_review'); final=proposal.get('read_judgment_review')
    row={'call':c['call'],'stage':c['source_stage'],'required':ctx.get('required',[]),
        'heads':[{k:h.get(k) for k in ('id','version','document_name','heading','use','finding','reason','original_available')} for h in ctx['judgments']],
        'needs':ctx['needs'],'conflicts':ctx['conflicts'],
        'lost_prior_judgment_ids':sorted(previous_ids-ids),'lost_prior_need_ids':sorted(previous_needs-needs),
        'lost_prior_conflict_ids':sorted(previous_conflicts-conflicts),
        'proposed_judgment_ids':[h['judgment_id'] for h in (review or {}).get('judgments',[])],
        'missing_required_proposals':sorted(set(ctx.get('required',[]))-{h['judgment_id'] for h in (review or {}).get('judgments',[])}),
        'final_review':final}
    if final:
        row['final_id_coverage']='Use canonical validated receipt: provider projection may omit singleton IDs and empty arrays.'
    views.append(row);previous_ids=ids;previous_needs=needs;previous_conflicts=conflicts
assessments=[e['payload']['assessment'] for e in events if e['kind']=='ASSESSMENT_VALIDATED']
receipts=[a.get('read_judgment_review') for a in assessments if a.get('read_judgment_review')]
native_views=[]; committed={}; observed_needs=set(); observed_conflicts=set()
for event in events:
    if event['kind']=='READ_JUDGMENT_RECORDED':
        for change in event['payload']['changes']:
            committed[change['current']['id']]=change['current']
    if event['kind']!='MEMORY_MODEL_INPUT':continue
    ctx=event['payload'].get('data',{}).get('read_judgments')
    if ctx is None:continue
    offered={h['id']:h for h in ctx['judgments']}
    needs={n['id'] for n in ctx['needs']}; conflicts={n['id'] for n in ctx['conflicts']}
    mismatches=[jid for jid,h in committed.items()
        if jid not in offered or any(offered[jid].get(k)!=v for k,v in h.items())]
    native_views.append({'seq':event['seq'],'phase':event['payload']['phase'],
        'committed_head_count':len(committed),'offered_head_count':len(offered),
        'committed_head_mismatches':mismatches,
        'lost_need_ids':sorted(observed_needs-needs),'lost_conflict_ids':sorted(observed_conflicts-conflicts),
        'required':ctx.get('required',[]),
        'judgments':[{k:h.get(k) for k in ('id','version','document_name','heading','use','finding','reason')} for h in ctx['judgments']],
        'needs':ctx['needs'],'conflicts':ctx['conflicts']})
    observed_needs=needs;observed_conflicts=conflicts
report={'committed_reviews':len(commits),'committed_judgment_heads':len(heads),
    'committed_versions':sum(len(t['changes']) for t in transitions),
    'prior_commit_mismatches':sum(not c['previous_matches_prior_commit'] for t in transitions for c in t['changes']),
    'input_continuity_violations':sum(len(v[k]) for v in native_views for k in ('committed_head_mismatches','lost_need_ids','lost_conflict_ids')),
    'dedicated_judgment_calls':sum(t['additional_model_call'] for t in transitions),
    'validated_final_reviews':len(receipts),'final_receipt_statuses':[r['status'] for r in receipts],
    'validated_final_coverage':[{field:sorted(x['id'] for x in r['review'][field])==sorted(x['id'] for x in r['prior_'+field]) for field in ('judgments','needs','conflicts')} for r in receipts if r['status']=='REVIEWED'],
    'views':views,'native_views':native_views,'transitions':transitions,'validated_final_receipts':receipts,
    'event_counts':dict(Counter(e['kind'] for e in events)),
    'note':'Canonical MEMORY_MODEL_INPUT and committed states determine continuity. Raw provider J/N aliases may change between calls and are not identity proof. Proposals and validated commits are distinct. No final receipt means final review unverified; no observed conflict means conflict handling unexercised. Continuity does not prove semantic correctness.'}
save(ART/'judgment-review.json',report)
print(json.dumps({k:v for k,v in report.items() if k not in ('views','native_views','transitions','validated_final_receipts','event_counts')},ensure_ascii=False,indent=2))
