from pathlib import Path
from copy import deepcopy
from itertools import product
import json,sys
code=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]);sys.dont_write_bytecode=True;sys.path.insert(0,str(code/'02_BACKEND'))
from semantic_runtime.chat_adapter import views
v=views();rows=[]
for status,kind,depth in product(range(400,600),['technical','timeout','review_incomplete','budget'],[0,1,2]):
 body={'request_id':'matrix-1','_gateway_status':status,'detail':'PRIVATE_SECRET_INPUT','traceback':'PRIVATE_SECRET_INPUT'}
 if kind=='timeout':body['error_type']='builtins.TimeoutError'
 if kind=='review_incomplete':body['code']='SOURCE_INVESTIGATION_INCOMPLETE'
 if kind=='budget':body['code']='BUDGET_EXHAUSTED'
 before=deepcopy(body);value=body
 for _ in range(depth):value=v.public_response(value,status=status)
 text=v.render(value);expected={'technical':str(status),'timeout':'timeout','budget':'limit','review_incomplete':None}[kind]
 correct=text.startswith('현재 충분한 법률 검토를 하지 못했습니다.') and (f'({expected})' in text if expected else '법률 쟁점이나 상황을 조금 더 구체적으로 질문해 주세요.' in text)
 if kind=='technical' and status in (401,403):correct=correct and '권한' in text
 if kind=='technical' and status==409:correct=correct and '처리 중' in text
 if kind=='budget':correct=correct and '나누어' in text
 final=v.public_response(value,status=status)
 rows.append({'case':f'{status}-{kind}-{depth}','contract_correct':bool(correct),'input_unchanged':body==before,'privacy':not any(s in text or s in json.dumps(final) for s in ['PRIVATE_SECRET_INPUT','Traceback']),'failed_state':final['answer_status']=='failed','status_preserved':final['_gateway_status']==status,'no_answer':not final.get('answer')})
assert len(rows)==2400
out.write_text(json.dumps(rows,ensure_ascii=False,separators=(',',':'))+'\n');print(out.name,len(rows),sum(r['contract_correct'] for r in rows))
