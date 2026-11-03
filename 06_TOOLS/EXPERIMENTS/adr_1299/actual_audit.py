"""Read-only actual records; distinguish observed failure from structural inference."""
from common import *
from collections import Counter
F=read(DES/'freeze.json');P=ROOT/read(DES/'inputs.json')['prior_artifacts']/'live/review-whatif'
def size(x):return len(json.dumps(x,ensure_ascii=False,separators=(',',':')).encode())
def walk(x):
 yield x
 if isinstance(x,dict):
  for v in x.values():yield from walk(v)
 elif isinstance(x,list):
  for v in x:yield from walk(v)
rows=[];outputs={}
base=read(P/'canonical/003.json.gz')['view'];question=base['current_request'];source_texts=[o['text'] for o in base['evidence_options']]
for number in (4,5,6):
 folder=P/'raw'/f'call-{number:03d}';r=read(folder/'request.json.gz');finished=read(folder/'finished.json')
 system=r['messages'][0]['content'];user=r['messages'][1]['content'];v=json.loads(user);v=v.get('view',v)
 strings=[x for x in walk(v) if isinstance(x,str)];s=r['response_format']['json_schema']['schema']
 row={'number':number,'stage':finished['stage'],'status':finished['status'],'seconds':finished['seconds'],
  'schema_bytes':size(s),'system_bytes':len(system.encode()),'user_bytes':len(user.encode()),'request_bytes':size(r),
  'question_occurrences':sum(x.count(question) for x in strings),
  'original_text_occurrences':[sum(x.count(t) for x in strings) for t in source_texts],
  'user_sections':{k:size(x) for k,x in v.items()},'top_level_schema_required':s.get('required',[]),
  'top_level_schema_fields':list(s.get('properties',{})),
  'exact_source_bytes':sum(len(t.encode()) for t in source_texts)}
 if (folder/'response.json.gz').exists():
  body=read(folder/'response.json.gz');out=json.loads(body['choices'][0]['message']['content']);outputs[number]=out
  sizes={k:size(x) for k,x in out.items()};reviews=out.get('read_judgment_review',{})
  row.update(output_bytes=size(out),output_sections=sizes,
   review_sections_bytes=sizes.get('read_judgment_review',0)+sizes.get('requirement_review',0),
   review_output_share=(sizes.get('read_judgment_review',0)+sizes.get('requirement_review',0))/size(out),
   review_rows={k:len(x) for k,x in reviews.items() if isinstance(x,list)},
   scope_group_rows=sum(len(x['groups']) for x in reviews.get('scope_reviews',[])),
   requirement_rows=len(out.get('requirement_review',[])),usage=body.get('usage'))
 rows.append(row)
before,after=outputs[4],outputs[5]
diff=[]
for i,(a,b) in enumerate(zip(before['read_judgment_review']['needs'],after['read_judgment_review']['needs'])):
 if a!=b:diff.append({'path':f'/read_judgment_review/needs/{i}','before':a,'after':b})
repair=read(P/'canonical/004.json.gz')['view']['repair_feedback']['validation']
result={'actual_rows':rows,'baseline_before_after':{'claims_exactly_equal':before['claims']==after['claims'],
 'issue_assessments_exactly_equal':before['issue_assessments']==after['issue_assessments'],
 'gaps_exactly_equal':before['gaps']==after['gaps'],
 'review_errors':repair['issues'],'changed_needs':diff,
 'optional_ontology_field_before':before.get('ontology_usage'),'optional_ontology_field_after_present':'ontology_usage' in after},
 'latest_timeout':read(P/'raw/call-006/finished.json'),
 'scope_claim':'Actual MAIN134 two-source behavior; transport cause inside provider unknown. Structural burden is independently observed, not proven cause of blank response.',
 'model_calls':0}
put(ART/'actual-audit.json',result)
print(json.dumps({'claims_equal':result['baseline_before_after']['claims_exactly_equal'],'rows':[{k:r[k] for k in ('number','schema_bytes','system_bytes','user_bytes','question_occurrences','original_text_occurrences')} for r in rows]},ensure_ascii=False))
