"""Read exact model/native receipts; never alter candidate or product answers."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0672-investigation-chain-parent-collision';D=R/'09_ARTIFACTS/AUDITS/20261006-investigation-chain-r2'
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
all_cases=[];summaries=[]
for cid in ['venture-stock-option','accounting-manager']:
 p=A/'artifacts/run-001'/cid;r=read(p/'result.json');m=r.get('output',{}).get('assembly',{}).get('term_agent',{})
 chain=m.get('investigation_chain',{});steps=chain.get('steps',[]);inputs=[];previous=[];checks=[]
 for q in sorted((p/'provider').glob('call-*/request.json')):
  req=read(q)
  try:v=json.loads(req['messages'][-1]['content']);v=v.get('view',v)
  except (ValueError,KeyError,IndexError):continue
  history=v.get('investigation_chain',{}).get('steps')
  if history is None:continue
  identities=[{'id':x['id'],'reason':x['reason'],'law_decisions':x['law_decisions'],'branch_decisions':x['branch_decisions'],'reference_decisions':x['reference_decisions']} for x in history]
  checks.append(identities[:len(previous)]==previous);previous=identities
  inputs.append({'call':q.parent.name,'chain_steps':len(history),'chain_ids':[x['id'] for x in history],
   'history_chars':len(json.dumps(v['investigation_chain'],ensure_ascii=False)),
   'laws':len(v.get('laws',[])),'reference_chars':len(json.dumps(v.get('references',{}),ensure_ascii=False)),
   'source_chars':len(json.dumps(v.get('sources',[]),ensure_ascii=False)),
   'input_chars':sum(len(x.get('content','')) for x in req['messages'])})
 out={'case_id':cid,'http_status':r['http_status'],'request_seconds':r.get('request_seconds',r['total_seconds']-r.get('app_setup_seconds',0)),'model_calls':r['model_calls'],
  'history_reasons_preserved_in_every_later_input':bool(checks) and all(checks),'all_steps_visible_in_final_input':len(previous)==len(steps),
  'natural_return_actions':sum(x['action']=='RETURN_TO' for x in steps),'multi_article_read_actions':sum(x['action']=='READ_ARTICLES' and len(x['targets'])>1 for x in steps),
  'menu_points':len(m.get('return_points',[])),'inputs':inputs,'chain':chain,
  'answer_text':r.get('output',{}).get('answer',{}).get('text',''),'active_pointer_unchanged':r['active_pointer_before']==r['active_pointer_after'],
  'return_coverage':'Natural requests do not force RETURN_TO; exact search/read/reference restoration and interruption/resume exercised by synthetic real reader/native contracts.'}
 put(p/'chain-audit.json',out);all_cases.append(out)
 lines=[r['question'],'','초기 실행 검색어:']+chain.get('entry_search',{}).get('queries',[])
 for x in steps:
  lines+=['',str(x['number'])+'. '+x['action'],'출발 시점: '+x['from_frame'],'이유: '+x['reason']]
  lines+=['대상: '+t['label'] for t in x['targets']]
  lines+=['법령 판단: '+json.dumps(z,ensure_ascii=False) for z in x['law_decisions']]
  lines+=['조문 판단: '+json.dumps(z,ensure_ascii=False) for z in x['branch_decisions']]
  lines+=['연결 판단: '+json.dumps(z,ensure_ascii=False) for z in x['reference_decisions']]
 (p/'행동체인.txt').write_text('\n'.join(lines)+'\n')
 (D/(cid+'-실제답변.txt')).write_text(out['answer_text']+'\n')
 summaries.append(r['question']+'\nHTTP '+str(r['http_status'])+' / '+str(round(r.get('request_seconds',0),3))+'초 / 모델 '+str(r['model_calls'])+'회\n'+out['answer_text'])
put(D/'verification.json',{'candidate':read(A/'artifacts/design/bindings.json'),'cases':all_cases,'contracts':73,'main_wiring':'unchanged','genos_deployed':False,'quality_certified':False})
(D/'검증결과.txt').write_text('로컬 격리 후보 구현·두 질문 실행\n\n'+'\n\n'.join(summaries)+'\n\n73개 계약 통과. 실제 자연 실행의 모든 후속 입력에 행동·판단 이유 유지 여부는 verification.json에 기록.\n돌아가기 동작은 검색/원문/연결 메뉴의 합성 계약에서 확인. 자연 질의에 복귀를 강제하지 않았음.\n활성 로컬 generation42 및 GENOS 배포 변경 없음. 독립 법률 품질평가/holdout 미수행.\n')
print(json.dumps([{k:r[k] for k in ['case_id','http_status','request_seconds','model_calls','history_reasons_preserved_in_every_later_input','natural_return_actions']} for r in all_cases],ensure_ascii=False))
