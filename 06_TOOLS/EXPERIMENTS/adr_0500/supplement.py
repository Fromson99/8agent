"""Additional read-only mechanism receipts and paired text excerpts; not a regrade."""
import json,hashlib
from pathlib import Path
from collections import Counter
from audit import R,A,P,SPECS,read,dump
out={}
for label in ['qwen','gemma']:
 slug,arm=SPECS[label];base=P/slug;d=read(base/'artifacts/workflow-diagnostics.json');ph=sum((Counter(x['phases']) for x in d['by_case']),Counter());dups=Counter();effects=Counter();late=[];late_errors=[]
 for c in d['by_case']:
  if c['attempt_statuses'].get('IGNORED_LATE'):
   late.append(c['case_id'])
   if (c.get('execution_error') or {}).get('type')=='OperationalError':late_errors.append(c['case_id'])
  t=read(base/'artifacts/run-001'/c['case_id']/arm/'trace.json');seen=set()
  for a in t['actions']:
   if a['actor']!='MODEL':continue
   q=json.loads(a['proposed_json']);res=json.loads(a['result_json'] or '{}');key=json.dumps({'tool':q['tool'],'args':q['args']},sort_keys=True,ensure_ascii=False)
   if key in seen:dups[q['tool']]+=1;effects[q['tool']+'|'+str(res.get('status'))+'|new_chars='+str(res.get('budget',{}).get('new_read_chars',0)>0)]+=1
   seen.add(key)
 out[label]={'phases':dict(ph),'exact_repeated_operations':dict(dups),'repeated_operation_effects':dict(effects),'late_response_cases':late,'late_and_sql_interrupted_cases':late_errors}
dump(A/'artifacts/mechanisms.json',out)
fixture=read(P/SPECS['qwen'][0]/'product-cases.json');gold={x['case_id']:x['reference_answer'] for x in read(P/SPECS['qwen'][0]/'gold-cases.json')['cases']};sections=['# 같은 문항의 실제 답변 대조','저장된 답변과 기준답을 그대로 나란히 두었다. 법령 현행성 검증이나 새 채점이 아니다. Qwen 중단5개 재실행은 별도 부록이며 원래 비교를 덮어쓰지 않는다.'];rows=[]
for case in fixture['cases']:
 cid=case['case_id'];section=[f'## {cid}',case['question'],'### 저장 기준답',gold[cid]];r={'case_id':cid}
 for label in ['qwen','gemma']:
  slug,arm=SPECS[label];base=P/slug;product=read(base/'artifacts/run-001'/cid/arm/'result.json');metric=next(x for x in read(base/'artifacts/metrics.json')['by_case'] if x['case_id']==cid);answer=product.get('result',{}).get('answer',{}).get('text');r[label]={'answer':answer,'reviewed_claims':metric['claims'],'auto_pass':metric['correct'],'error_type':(product.get('error') or {}).get('type')};section += [f'### {label}',f"검토 주장 {metric['claims']}개, 기존 자동판정 {metric['correct']}, 오류 {(product.get('error') or {}).get('type') or '없음'}",answer or '[최종 답변 없음]']
 sections.append('\n\n'.join(section));rows.append(r)
(A/'PAIRED_CASES.md').write_text('\n\n'.join(sections)+'\n');dump(A/'artifacts/paired-texts.json',rows)
print(json.dumps(out,ensure_ascii=False))
