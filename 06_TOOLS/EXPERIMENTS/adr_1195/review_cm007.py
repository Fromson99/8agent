"""Offline source/assessment/composition diagnosis, never a product correction."""
from common import *
def bind(p):return {"path":str(p.relative_to(ROOT)),"sha256":sha(p)}
P=ART/'live/cm-007';a=read(P/'audit.json');ass=a['assessments'][-1]['payload'];answer=(P/'answer.txt').read_text();calls=read(P/'calls.json')
req=read(P/'raw/call-008/request.json.gz');wire=req['messages'][1]['content'];raw=read(P/'raw/call-008/response.json.gz');narrative=json.loads(raw['choices'][0]['message']['content']);paragraph=narrative['paragraphs'][0]['text'];c1=next(c for c in ass['claims'] if c['claim_id']=='C1');c2=next(c for c in ass['claims'] if c['claim_id']=='C2')
assert ass['answer_coverage']=='COVERED' and ass['gaps']==[] and ass['limitations']==[]
assert '국내소재외국지주회사 제외' in c1['text'] and '국내소재외국지주회사 포함' in c1['text']
assert '국내소재외국지주회사' in wire and '국내소재외국지주회사' not in answer
assert all(x in c2['text'] for x in ('상장예비심사신청 후에 국내에서 모집·매출한','50억원','6개월'))
assert '상장예비심사신청 후 국내에서 모집·매출한' in answer
assert '확인한 원문 범위에서 답변하며, 나머지 범위는 확인하지 못했습니다.' not in answer
assert all(x['status']=='responded' for x in calls)
assert calls[6]['http_status']==429 and calls[7]['actual_provider']=='Near AI'
input7=read(P/'raw/call-007/request.json.gz');assert input7['messages']==req['messages'] and input7['response_format']==req['response_format']
observations={'case_id':'cm-007','new_model_calls':0,'inspection':'Offline comparison of actual stored original, accepted C1, serialized COMPOSE input and visible final text; not keyword-only quality grading',
 'failure_stage':'memory-compose, physical call008 after confirmed429 on007',
 'source_and_assess_condition':'국내기업은 국내소재외국지주회사 제외, 외국기업은 국내소재외국지주회사 포함',
 'compose_received_condition':True,'visible_answer_preserved_condition':False,
 'materiality':'This condition determines which quantity/cap/holding-period regime applies to a domestic-located foreign holding company. The final domestic/foreign grouping drops that exception.',
 'secondary_ambiguity':'Foreign-company monthly-sale clause omits the explicit initially-acquired-share denominator present in accepted C1; final wording only says monthly5%.',
 'same_compose_messages_and_schema_across429_switch':True,
 'composer_prompt_already_requests_condition_preservation':True,
 'server_check_scope':'narrative_answer.checked requires every claim ID covered, but does not establish that each condition/exception or denominator is retained in paragraph text.',
 'provider_causality':'Observed NearAI response omits condition; switching policy did not change messages/schema. No controlled provider comparison or provider-causal conclusion.',
 'evidence':{'accepted_assessment':bind(P/'audit.json.gz'),'compose_request':bind(P/'raw/call-008/request.json.gz'),'compose_response':bind(P/'raw/call-008/response.json.gz'),'visible_answer':bind(P/'answer.txt')}}
put(P/'composition-audit.json',observations)
review={'case_id':'cm-007','passed':False,'failure_type':'other: final_composition_scope_omission','content_evaluated':True,
 'model_claim_content_passed':True,'visible_answer_consistency_passed':False,'transport_completion_passed':True,
 'previous_domestic_post_application_omission_reproduced':False,'generic_limitation_removed':True,
 'originals_and_final_input_complete':True,'reference_answer_used_in_product':False,'new_model_calls':0,
 'checked':['Both markets article13 required originals acquired and cited; quantity/cap/period core values present',
 'KOSPI foreign-only and post-application domestic denominator, issueprice,50억원cap,6monthsale restriction preserved',
 'KOSDAQ3%10억원3months; fasttransfer5%25억원6months and specified1year exception preserved',
 'KOSDAQ foreign5%, innovation50억원 otherwise25억원,1year and6monthmonthly5%sale path present',
 'Private placement/acquisition window/unsubscribed balance inclusion and innovation-underwriter3year/2year trigger preserved',
 'Material domestic-located foreign holding company classification exists in source, accepted C1 and composeinput but absent in visible answer'],
 'reason':'The final writing step dropped a material actor classification despite complete acquired/delivered originals and accepted claim conditions. Structural claim-ID coverage accepted it. This is final composition loss, not failed retrieval.',
 'diagnostic':bind(P/'composition-audit.json')}
put(P/'content-review.json',review)
print('CM007 content gate failed at final COMPOSE; acquisition/assessment/prompt/footer/transport/storage checked separately')
