"""Offline inspection of actual correction scopes and retention receipts."""
from common import *
events=read(ART/'known-query/candidate/events-audit.json')
scopes={}; rejections=[]; receipts=[]
for e in events:
    v=e['payload']
    if e['kind'] in ('OUTPUT_DECISION_STATE','OUTPUT_CORRECTION_SCOPE'):
        owner=v.get('binding',{}).get('owner','')
        if owner.endswith('-correction-scope'):
            scopes.setdefault(v['decision_key'],[]).append({'seq':e['seq'],'status':v['status'],'attempt':v['attempt'],
                'decision':v.get('decision'),'failure_count':len(v.get('failures',[])),'failures':v.get('failures',[])})
        elif v.get('status')=='REJECTED':
            rejections.append({'seq':e['seq'],'owner':owner,'attempt':v['attempt'],'error':v.get('error'),'failure':v.get('failure')})
    if e['kind']=='READ_JUDGMENT_RECORDED':
        receipts.append({'seq':e['seq'],'wire_version':v.get('wire_version'),'wire_proposal_hash':v.get('wire_proposal_hash'),
            'normalizations':v.get('normalizations',[]),'changes':len(v['changes'])})
report={'scope_count':len(scopes),'maximum_scope_failures':max([r['failure_count'] for rows in scopes.values() for r in rows] or [0]),
    'scope_failures_within_two':all(r['failure_count']<=2 for rows in scopes.values() for r in rows),
    'rejected_decisions':rejections,'normalization_receipts':receipts,'scopes':scopes,
    'note':'A zero-failure live path does not exercise exhausted-budget recovery. Cross-presentation/restart/unknown-reservation behavior is established by deterministic contracts, not inferred from a clean live run.'}
save(ART/'recovery-review.json',report)
print(json.dumps({k:v for k,v in report.items() if k not in ('scopes','normalization_receipts')},ensure_ascii=False,indent=2))
