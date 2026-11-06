"""Offline response collection; reference answers never enter product input."""
from common import *
import argparse

def collect():
 grades={r['id']:r for r in read(DES/'grading-only.json')}
 rows=[]
 for case in read(DES/'live-cases.json'):
  folder=ART/'public-live'/(case['id']+'-selected')
  response=folder/'turn-1/response.json.gz'
  if not response.exists():continue
  saved=read(response);body=saved['body'];answer=body.get('answer') or {}
  term=(body.get('assembly') or {}).get('term_agent') or {}
  claims=answer.get('claims',[]) if isinstance(answer,dict) else []
  cited={s for c in claims for s in c.get('source_ids',[])}
  delivered={(e['document_id'],str(b)) for e in term.get('evidence_inventory',[]) if e.get('source_id') in cited for scope in e.get('available_scopes',[]) if scope.get('delivered_complete') for b in scope.get('block_ids',[])}
  grade=grades[case['id']]
  wanted={(a['document_id'],str(b)) for a in grade['anchors'] for b in a['block_ids']}
  calls=read(folder/'calls.json') if (folder/'calls.json').exists() else []
  result=read(folder/'turn-1/result.json') if (folder/'turn-1/result.json').exists() else {}
  row={'case_id':case['id'],'question':case['steps'][0]['question'],'expected':grade['expected'],'answer':answer.get('text','') if isinstance(answer,dict) else str(answer),'http_status':saved['http_status'],'request_seconds':result.get('request_seconds'),'claims':len(claims),'needs_guidance':(term.get('guided_reply') or {}).get('needs_guidance'),'accepted_outcome':term.get('accepted_outcome'),'expected_blocks':len(wanted),'matched_blocks':len(wanted&delivered),'missing_blocks':sorted(wanted-delivered),'physical_calls':len(calls),'unknown':sum(c['status'] in ('unknown','started') for c in calls),'response_path':str(response.relative_to(ROOT)),'response_sha256':sha(response)}
  rows.append(row)
 put(ART/'review-input.json',{'rows':rows,'reference_input_is_offline_only':True,'semantic_grades_automatically_generated':False})
 return rows

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--after',default='');a=p.parse_args()
 for r in collect():
  if r['case_id']>a.after:
   print(json.dumps(r,ensure_ascii=False))
