"""Exercise repaired native stage with injected deterministic responses, no model."""
import json
from types import SimpleNamespace as S
from contracts import load,B,A,mod
selection=load('semantic_runtime.legal_agent.source_selection',B/'source_selection.py')
native=load('semantic_runtime.legal_agent.memory_rag',B/'memory_rag.py')
checks=[]
def check(name,value):
 assert value,name
 checks.append({'name':name,'pass':True})
source={'source_id':'unit','text':'대표자는 보고한다. 단서의 조건은 확인한다.'}
valid={'claims':[{'text':'대표자의 보고 의무','source_id':'unit','quote':'대표자는 보고한다.'}],'limitations':[]}
invalid={'claims':[{'text':'대표자의 보고 의무','source_id':'unit','quote':'존재하지 않는 인용'}],'limitations':[]}
def execution(always_bad=False):
 calls=[]
 def invoke(system,data,schema,phase):
  calls.append((phase,data))
  if phase.endswith('check'):return {'valid':True,'reason':'contract stub'}
  if phase=='memory-assess' or always_bad:return invalid
  return valid
 host=S(question=lambda s:'모의 질문',verify=lambda r:None,invoke=invoke,binding={'generation':'SYNTHETIC'})
 session=S(work=S(event=lambda *a:None),context=S(query={}),sources=S(scope=['d','d2'],matcher=S(documents={'d':'명시한 규정','d2':'연결된 세칙'},starts=lambda q,scope:{'documents':[{'id':'d'}]})))
 return native.NativeExecution(host,session,{},{}),calls
parts={'READ':{'payload':{'originals':[source]}},'SELECT':{'payload':{'final_ids':['unit']}}}
e,calls=execution();r=e.stage('ASSESS',{'facts':[]},parts,'모의 질문','prose')
check('invalid quote repaired once',r==valid and [x[0] for x in calls]==['memory-assess','memory-assess-repair','memory-assess-check'])
check('rejected quote and error provided to repair',calls[1][1]['repair_feedback']['rejected_assessment']==invalid)
e,calls=execution(True)
try:e.stage('ASSESS',{'facts':[]},parts,'모의 질문','prose')
except mod.MemoryError:check('second invalid quote remains rejected',len(calls)==2)
else:raise AssertionError('invalid assessment published')
e,calls=execution();plan=e.stage('PLAN',{'facts':[],'queries':['검색'],'task':'모의 목적'}, {},'모의 질문','prose')
check('law focus excludes unmentioned allowed documents',plan['law_names']==['명시한 규정'])
choices={'choices':[{'id':'C1','reason':'사유1'},{'id':'C1','reason':'사유2'},{'id':'C2','reason':'사유3'}]}
check('allowed duplicate source IDs coalesce in order',selection.checked_choices(choices,['C1','C2'],3)==['C1','C2'])
check('raw selection reasons remain unchanged',len(choices['choices'])==3)
for label,allowed,limit in [('outside source', ['C2'],3),('physical choice budget',['C1','C2'],2)]:
 try:selection.checked_choices(choices,allowed,limit)
 except ValueError:check('still rejects '+label,True)
 else:raise AssertionError('guard bypassed '+label)
e,calls=execution();e.history_records=[{'event_id':99,'facts':'superseded'}]
def compose(system,data,schema,phase):
 calls.append((phase,data))
 if phase.endswith('check'):return {'valid':True,'reason':'contract stub'}
 return {'text':'현재 판단',**valid}
e.host.invoke=compose
r=e.stage('COMPOSE',{'facts':[{'name':'기관','value':'현재'}]}, {**parts,'ASSESS':{'payload':valid}},'현재 답변','prose')
check('compose and reviewer receive current facts without history',all(x[1]['current_facts']==[{'name':'기관','value':'현재'}] and 'history_records' not in x[1] for x in calls))
result={'passed':len(checks),'total':len(checks),'external_calls':0,'checks':checks};(A/'artifacts/contracts/native-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
