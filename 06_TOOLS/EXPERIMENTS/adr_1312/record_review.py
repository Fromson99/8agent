from common import *
import base64
rows=[]
for cell in read(DES/'criteria.json')['order']:
 case,arm=cell.split('/');p=ART/'live'/(case+'-'+arm)
 if not p.exists():
  rows.append({'cell':case+'-'+arm,'case_id':case,'arm':arm,'verdict':'NOT_RUN','basis':'선행NearAI요청UNKNOWN후전역중단. 실제호출/답변0이며오답으로채점하지않음.','final_core_rules_matched':None,'final_core_rules_total':3});continue
 r=read(p/'result.json');response=read(p/'response.json.gz')['body'];answer=response.get('answer') or {};term=response.get('assembly',{}).get('term_agent',{});outcome=term.get('accepted_outcome') or {}
 row={'cell':p.name,'case_id':case,'arm':arm,'http_status':r['http_status'],'response_sha256':sha(p/'response.json.gz'),'answer_text_sha256':sha(p/'answer.txt'),'final_claim_count':r['claims'],'product_outcome':outcome,'final_core_rules_total':3,'manual_judge':'Codex inspected final claims and same-artifact source blocks; external judge calls0'}
 if r['http_status']==200:
  assert case=='ontology-369' and arm=='before' and len(answer['claims'])==3
  checks=[{'claim_id':'claim:1','source_block':'1421','rule':'1주마다의결권1개','matched':True},{'claim_id':'claim:2','source_block':'1422','rule':'회사가가진자기주식의결권없음','matched':True},{'claim_id':'claim:3','source_block':'1423','rule':'회사/모회사및자회사/자회사의타회사발행주식총수10분의1초과보유→그다른회사가가진회사또는모회사주식의의결권없음','matched':True,'strict_threshold_and_subject_direction_preserved':True}]
  row.update(verdict='PASS',final_core_rules_matched=3,checks=checks,basis='최종3주장의수치·조건·주체·제한대상방향이실제확보한369조1~3항과일치. 별도371조추가주장없음. 내용전달성공이며제품내부LIMITED_ANSWER/PARTIAL/NO_PROGRESS와구분한다.',unsupported_material_rule_found=False)
 else:
  assert arm=='after' and case=='ontology-369' and r['http_status']==504
  calls=read(p/'calls.json');last=calls[-1];d=last['transport_diagnostics'];assert last['status']=='unknown' and d['received_http_status']==200 and d['whitespace_only'] and not d['complete'] and d['worker_reaped']
  partial=read(p/'raw/call-002/partial.json.gz');body=base64.b64decode(partial['body_base64']);assert len(body)==660 and not body.strip() and hashlib.sha256(body).hexdigest()==d['received_sha256']
  row.update(verdict='ERROR',final_core_rules_matched=None,checks=[],basis='NearAI단독물리2번째요청에서HTTP200헤더뒤공백60조각660bytes만수신,완성JSON없이179.933초절대기한종료→UNKNOWN/API504/주장0. 원문선택모델단계라새FINISH직행수정미도달;종료조건수정의실제답품질/호출감소미검증.',error_taxonomy='provider_stream_incomplete_unknown',not_a_content_wrong_answer=True,transport={'seconds':last['seconds'],**d})
 rows.append(row)
put(ART/'semantic-review.json',{'rows':rows,'source_scored_correct':1,'actual_technical_failures':1,'not_run':1,'new_model_calls':0,'frozen_reference_sha256':sha(DES/'scoring-only-originals.json'),'scope':'Known369 final3claims only; after is technical failure before assessment and365notrun, not legal wrong-answer rate.'})
print('Content1pass/technical1/notrun1 recorded; partial stream hash independently verified.')
