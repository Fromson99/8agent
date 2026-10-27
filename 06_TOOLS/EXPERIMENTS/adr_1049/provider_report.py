"""Read only saved physical requests/responses; never infer missing provider/usage."""
from collections import Counter,defaultdict
from common import ART,read,save

def report():
 rows=[]
 for root,role in ((ART/'matrix','product'),(ART/'evaluation','judge')):
  if not root.exists():continue
  for request_path in sorted(root.rglob('request.json')):
   if not request_path.parent.name.startswith('call-'):continue
   request=read(request_path);folder=request_path.parent
   response=(read(folder/'response.json') or {}) if (folder/'response.json').exists() else {}
   receipt=read(folder/'response-receipt.json') if (folder/'response-receipt.json').exists() else {}
   error=response.get('error') or {};meta=error.get('metadata') or {}
   relative=folder.relative_to(root).parts
   arm=relative[0].rsplit('-',1)[-1] if role=='product' else 'OFFLINE'
   usage=response.get('usage') or {}
   rows.append({'role':role,'arm':arm,'path':str(folder.relative_to(ART)),
     'requested':request.get('provider',{}).get('only',[]),'observed':response.get('provider') or meta.get('provider_name'),
     'http_status':receipt.get('status_code'),'error_code':error.get('code'),
     'input_tokens':usage.get('prompt_tokens'),'output_tokens':usage.get('completion_tokens'),'cost_usd':usage.get('cost')})
 groups=defaultdict(list)
 for row in rows:groups[(row['role'],row['arm'],tuple(row['requested']),row['observed'])].append(row)
 aggregates=[]
 for (role,arm,requested,observed),items in groups.items():
  aggregates.append({'role':role,'arm':arm,'requested':list(requested),'observed':observed,'physical_calls':len(items),
   'http_status_counts':dict(Counter(str(r['http_status']) for r in items)),
   'usage':{k:{'known_sum':sum(r[k] for r in items if isinstance(r[k],(int,float))),
    'unknown_calls':sum(r[k] is None for r in items)} for k in ['input_tokens','output_tokens','cost_usd']}})
 return {'physical_calls':len(rows),'groups':aggregates,'calls':rows,
  'limitation':'Provider mix is an execution confound. Do not claim a clean same-provider effect when arm mixes differ. Missing usage and unobserved provider remain unknown.'}
if __name__=='__main__':
 result=report();save(ART/'provider-summary.json',result);print('provider report:',result['physical_calls'],'physical calls')
