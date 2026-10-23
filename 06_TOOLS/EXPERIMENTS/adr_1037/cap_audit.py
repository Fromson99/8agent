"""Compare real saved wire bodies with preregistered output-cap policy, offline."""
from common import *
P=ART/'known-query/candidate';rows=[]
for p in sorted((P/'model').glob('call-*/request.json')):
 v=read(p);rows.append({'call':p.parent.name,'output_cap_fields':{k:v[k] for k in ('max_tokens','max_completion_tokens','max_output_tokens') if k in v},'request_sha256':sha(p)})
save(ART/'output-policy-review.json',{'all_requests_uncapped':bool(rows) and all(not r['output_cap_fields'] for r in rows),'calls':rows,'profile_output_cap':read(P/'effective-profile.json')['max_output_tokens'],'policy_sha256':sha(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),'server_limits_known':False})
print('Uncapped wire requests:',sum(not r['output_cap_fields'] for r in rows),'/',len(rows))
