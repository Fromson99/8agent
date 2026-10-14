from pathlib import Path
from copy import deepcopy
from itertools import product
import json,sys
code=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]);sys.dont_write_bytecode=True;sys.path.insert(0,str(code/'02_BACKEND'))
from semantic_runtime.legal_agent import completion_contracts as cc
from semantic_runtime.legal_agent.investigation_contracts import GAP_KINDS
kinds=['MISSING_SCOPE','UNREAD_SAVED','MISSING_SOURCE','UNRESOLVED_REFERENCE','WRONG_SUBJECT','MISSING_FACT','VERSION_AMBIGUOUS'];assert GAP_KINDS==kinds
rows=[]
def check(gaps,label):
 value={'gaps':gaps,'claims':[{'source_id':'S1','quote':'모의 원문 그대로'}],'disposition':'LIMITED_ANSWER'};before=deepcopy(value);expected=deepcopy(value);changes=[]
 for i,g in enumerate(expected['gaps']):
  g.setdefault('missing_target','')
  if g['kind']!='MISSING_FACT' and g['suggested_action']=='REQUEST_FACT':
   g['suggested_action']='RESEARCH';changes.append({'gap_index':i,'issue_id':g['issue_id'],'kind':g['kind'],'from':'REQUEST_FACT','to':'RESEARCH'})
 if hasattr(cc,'source_gap_actions'):
  actual,audit=cc.source_gap_actions(value);again,delta=cc.source_gap_actions(actual)
 else:
  actual=cc.with_targets(value);audit=[];again=cc.with_targets(actual);delta=[]
 rows.append({'case':label,'contract_correct':actual==expected and audit==changes,'input_unchanged':value==before,'idempotent':again==actual and not delta,'gap_count_preserved':len(actual['gaps'])==len(gaps),'expected_corrections':len(changes),'actual_corrections':len(audit)})
for i,(kind,action,material,target,ref) in enumerate(product(kinds,['REQUEST_FACT','RESEARCH'],[False,True],['absent','empty','named'],[None,'M1'])):
 g={'issue_id':'Q1','kind':kind,'material':material,'reason':'모의 부족을 보존','suggested_action':action,'material_id':ref}
 if target!='absent':g['missing_target']='' if target=='empty' else '모의 규정 제3조'
 check([g],f'single-{i:03}')
for i,vals in enumerate(product(kinds,kinds,['REQUEST_FACT','RESEARCH'],['REQUEST_FACT','RESEARCH'],[False,True],[False,True])):
 k1,k2,a1,a2,m1,m2=vals
 check([{'issue_id':f'Q{j}','kind':k,'material':m,'reason':f'보존 {j}','suggested_action':a,'material_id':None,'missing_target':f'대상 {j}'} for j,(k,a,m) in enumerate([(k1,a1,m1),(k2,a2,m2)],1)],f'pair-{i:03}')
assert len(rows)==952
out.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n');print(out.name,len(rows),sum(r['contract_correct'] for r in rows))
