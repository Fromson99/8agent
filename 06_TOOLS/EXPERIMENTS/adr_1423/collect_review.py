"""Offline response collection; reference answers never enter product input.

Adds MAIN161 observations: same-section automatic reads (evidence reason written by
connection_scope) and unread-connection notes (guided_reply.unread_connections).
"""
from common import *
import argparse
SECTION_MARK='에서 절 제목의 핵심 표현을 함께 쓰는 조문 자동 확보'

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
  inventory=term.get('evidence_inventory',[])
  delivered={(e['document_id'],str(b)) for e in inventory if e.get('source_id') in cited for scope in e.get('available_scopes',[]) if scope.get('delivered_complete') for b in scope.get('block_ids',[])}
  grade=grades[case['id']]
  wanted={(a['document_id'],str(b)) for a in grade['anchors'] for b in a['block_ids']}
  calls=read(folder/'calls.json') if (folder/'calls.json').exists() else []
  result=read(folder/'turn-1/result.json') if (folder/'turn-1/result.json').exists() else {}
  reply=term.get('guided_reply') or {}
  unread=reply.get('unread_connections') or []
  text=answer.get('text','') if isinstance(answer,dict) else str(answer)
  section_reads=[{'source_id':e.get('source_id'),'label':e.get('label') or e.get('title'),'reason':e.get('reason')} for e in inventory if SECTION_MARK in str(e.get('reason',''))]
  unread_sources={u.get('source_id') for u in unread if u.get('source_id')}
  row={'case_id':case['id'],'question':case['steps'][0]['question'],'expected':grade['expected'],'answer':text,'http_status':saved['http_status'],'request_seconds':result.get('request_seconds'),'claims':len(claims),'needs_guidance':reply.get('needs_guidance'),'accepted_outcome':term.get('accepted_outcome'),'expected_blocks':len(wanted),'matched_blocks':len(wanted&delivered),'missing_blocks':sorted(wanted-delivered),'physical_calls':len(calls),'unknown':sum(c['status'] in ('unknown','started') for c in calls),'response_path':str(response.relative_to(ROOT)),'response_sha256':sha(response),
       'same_section_reads':section_reads,
       'unread':{'total':reply.get('unread_connection_total'),'shown':len(unread),'list_only':sum(bool(u.get('list_only')) for u in unread),
                 'model_reason':sum(u.get('reason_origin')=='MODEL_NOTE' for u in unread),
                 'missing_origin_or_target':sum(not (u.get('from_label') and u.get('target_label')) for u in unread),
                 'claims_citing_unread':sorted(cited&unread_sources),
                 'answer_has_unread_section':'확인하지 않은 연결 조문' in text,
                 'items':[{k:u.get(k) for k in ('from_label','target_label','relation','relation_text','reason_code','reason_origin','reason','list_only','judged_unneeded')} for u in unread]}}
  rows.append(row)
 put(ART/'review-input.json',{'rows':rows,'reference_input_is_offline_only':True,'semantic_grades_automatically_generated':False})
 return rows

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--after',default='');p.add_argument('--brief',action='store_true');a=p.parse_args()
 for r in collect():
  if r['case_id']>a.after:
   if a.brief:r={k:r[k] for k in ('case_id','http_status','request_seconds','claims','matched_blocks','expected_blocks','physical_calls','unknown')}|{'section_reads':len(r['same_section_reads']),'unread_shown':r['unread']['shown']}
   print(json.dumps(r,ensure_ascii=False))
