"""Offline completion/cause review of the single real run; no model invocation."""
from common import *
P=ART/'live/gold-369';a=read(P/'audit.json');calls=read(P/'calls.json');second=read(P/'raw/call-002/finished.json');diag=second['transport_diagnostics']
events=[]
for line in (ART/'live-process.log').read_text().splitlines():
 try:v=json.loads(line)
 except ValueError:continue
 if v.get('event')=='model.attempt.failed':events.append(v)
assert a['http_status']==504 and a['unknown']==1 and a['post_unknown_calls']==0
assert second['error_type']=='AbsoluteDeadlineExceeded' and diag['whitespace_only'] and not diag['complete']
assert events[-1]['error_code']=='MODEL_DEADLINE_EXCEEDED' and events[-1]['unknown'] is True and events[-1]['retry_scheduled'] is False
assert not a['assessments'] and a['answer_chars']==0
v={'passed':False,'status':'NOT_REACHED_FINAL_ASSESSMENT','answer_chars':0,'legal_content_review':'No answer to review; no legal quality conclusion',
 'scope_review_live_exercised':False,'final_scope_contract_sent':False,'failure_stage':second['stage'],
 'cause_observed':{'error_type':second['error_type'],'error_code':events[-1]['error_code'],'http_status':a['http_status'],'transport':diag},
 'unknown_propagated':True,'original_error_not_masked':True,'post_unknown_model_calls':0,'provider_switches':0,
 'hypothesis_limit':'Final generalized contract was not reached. Whitespace response/internal provider cause unknown; do not attribute to SQLite or new scope validator.',
 'synthetic_validation':'Scope contract separately verified by pure contracts and actual native API with synthetic model.',
 'observed_run_statuses':[x['status'] for j in a['journals'] for x in j.get('runs',[])],
 'same_question_redispatch':0,'new_model_calls_for_review':0}
put(P/'content-review.json',v);print(v['status'], 'original timeout and UNKNOWN preserved')
