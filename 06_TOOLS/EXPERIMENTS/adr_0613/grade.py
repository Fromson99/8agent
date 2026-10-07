"""Frozen offline functional checks and independent answer/history judging."""
import hashlib,json,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[3];sys.path.insert(0,str(R/'02_BACKEND'));sys.dont_write_bytecode=True
from lawrag.research.experiment_client import ExperimentClient
from binding import verify,sha
A=R/'04_EXPERIMENTS/ADR/ADR-0613-cm-memory-current-state-authority';D=A/'artifacts/design';run=A/'artifacts/run-001'
def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def obj(props):return {'type':'object','additionalProperties':False,'required':list(props),'properties':props}
SCHEMA=obj({'correct':{'type':'boolean'},'reason':{'type':'string'}})
SYSTEM='제품과 분리된 사후 평가자다. 답변을 수정하지 않는다. 제공된 저장 기준답의 결론과 핵심 단서가 답변에 포함되고, 원문에 없는 확정적 주장이 없어야 correct=true다. 확인 불가/빈 답변/틀린 적용대상/필수 단서 누락은 false다. 원래 CM 기준답의 현행 법률 타당성을 인증하는 평가가 아니다. 한국어 이유와 JSON만 출력한다.'
def main():
 for p,h in json.loads((D/'freeze.json').read_text()).items():assert sha(R/p)==h
 gold=json.loads((D/'gold.json').read_text());arms={a:json.loads((run/a/'product-result.json').read_text()) for a in ('BASELINE','REPAIRED')};out=run/'offline-judge';assert not out.exists();client=ExperimentClient(R,out,max_calls=40,max_output_tokens=1800,max_repairs=0)
 grades={};semantic=[]
 for arm,product in arms.items():
  rows=[]
  for case in product['products']:
   cid=case['case_id'];spec=gold[cid];ts=case['turns']
   def chk(t,k,ok,expected,actual):rows.append({'case_id':cid,'turn':t,'kind':k,'pass':bool(ok),'expected':expected,'actual':actual})
   for t in ts:
    i=t['turn'];o=t['output'];expected='STORED' if i in spec['confirm_turns'] else 'REUSED' if i in spec['reuse_turns'] else 'READY'
    chk(i,'completion',o.get('status')==expected,expected,o.get('status'))
    if i in spec['history_turns'] or i in spec['presentation_turns']:
     prev=ts[i-2]['db'];current=t['db'];target=o.get('goal_id') or (ts[i-2]['output'].get('goal_id'));old={k['id']:k for k in prev['knowledge'] if k['status']=='ACTIVE' and k['bundle']==target};now={k['id']:k for k in current['knowledge'] if k['status']=='ACTIVE'}
     chk(i,'confirmed_experience_preserved',bool(old) and old.keys()<=now.keys(),list(old),list(now))
     if i in spec['history_turns']:
      chk(i,'history_does_not_mutate_goal',prev['goal']==current['goal'] and prev['route']==current['route'] and prev['event']==current['event'],'same goal/route/events',o.get('executed'))
      events=[e for e in prev['event'] if e['goal']==o.get('goal_id')];ids=[e['id'] for e in events];refs=[e['event_id'] for e in o.get('history',[])]
      chk(i,'exact_history_event_references',bool(ids) and ids==refs,ids,refs)
      try:
       verdict=client.generate('실제 기록과 설명의 정정 이력을 대조한다. 원래 상태, 각 조건 변경, 복원 대상을 올바르게 설명해야 true다. 현재 결론만 설명하고 요청한 정정 과정을 생략하거나 기록과 다른 이력을 말하면 false다. 사건의 법률 결론은 이 호출의 채점 대상이 아니다. JSON만 출력한다.',{'events':events,'answer':(o.get('answer') or {}).get('text','')},SCHEMA,phase=arm+'-'+cid+'-history')
      except Exception as e:verdict={'correct':False,'reason':str(e),'judge_error':True}
      semantic.append({'arm':arm,'case_id':cid,'turn':i,'kind':'history','verdict':verdict})
     else:chk(i,'presentation_only_compose',o.get('executed')==['COMPOSE'],['COMPOSE'],o.get('executed'))
    for target,origin in spec['restore_pairs']:
     if i==target:
      expectedfacts=(ts[origin-1]['output'].get('state') or {}).get('facts');actual=(o.get('state') or {}).get('facts');chk(i,'restore_exact_facts',expectedfacts is not None and expectedfacts==actual,expectedfacts,actual)
    if str(i) in spec['legal_turns']:
     reference=spec['references'][spec['legal_turns'][str(i)]];answer=(o.get('answer') or {}).get('text','')
     if not answer:verdict={'correct':False,'reason':'제품 답변 없음','judge_called':False}
     else:
      try:verdict=client.generate(SYSTEM,{'base_case':cid,'user_question':t['input']['question'],'current_state':o.get('state'),'reference_answer':reference,'answer':answer,'claims':(o.get('answer') or {}).get('claims',[])},SCHEMA,phase=arm+'-'+cid+'-'+str(i)+'-legal')
      except Exception as e:verdict={'correct':False,'reason':str(e),'judge_error':True}
     semantic.append({'arm':arm,'case_id':cid,'turn':i,'kind':'legal','verdict':verdict})
   put(run/'grading-progress.json',{'grades':grades,'current':rows,'semantic':semantic})
  grades[arm]={'checks':rows,'passed':sum(x['pass'] for x in rows),'total':len(rows)}
 pairs=[]
 for b in [x for x in semantic if x['arm']=='BASELINE']:
  g=next(x for x in semantic if x['arm']=='REPAIRED' and all(x[k]==b[k] for k in ('case_id','turn','kind')))
  pairs.append({'case_id':b['case_id'],'turn':b['turn'],'kind':b['kind'],'baseline':b['verdict']['correct'],'guarded':g['verdict']['correct']})
 result={'status':'complete','arms':arms,'functional':grades,'semantic':semantic,'pairs':pairs,'judge_usage':client.usage,'judge_attempts':client.calls}
 put(run/'result.json',result);print(json.dumps({'functional':{a:{k:v for k,v in g.items() if k!='checks'} for a,g in grades.items()},'semantic':{a:{kind:{'correct':sum(x['verdict']['correct'] for x in semantic if x['arm']==a and x['kind']==kind),'total':sum(x['arm']==a and x['kind']==kind for x in semantic)} for kind in ('legal','history')} for a in arms}},ensure_ascii=False))
if __name__=='__main__':main()
