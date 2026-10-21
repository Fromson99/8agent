from pathlib import Path
from types import SimpleNamespace as S
from copy import deepcopy
import json,hashlib,sys,time,resource
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0842-comparison-execution-qualification';D=A/'artifacts/design';read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
f=read(D/'freeze.json');assert all(sha(R/n)==h for n,h in f['files'].items());C=R/f['code_root'];sys.dont_write_bytecode=True;sys.path.insert(0,str(C/'02_BACKEND'))
from workflow.risk_team_compare_workflow import basis
from workflow import presentation
sources=[{'evidence_id':s,'side':s,'spans':[{'text':s}]} for s in ('internal','external')];presentation.evidence=lambda ctx,state,ids=None:sources
ctx=S(request={'as_of':None},repo=S(save=lambda s:None));rows=[];start=time.monotonic()
for case in read(D/'direct-cases.json'):
 item={s:{'status':case['status'],'text':'검토 의견','citations':[{'evidence':s,'quote':s}] if case['citations'] not in ('none','external' if s=='internal' else 'internal') else [],'dependencies':[],'scope_sufficient':False,'missing':'확인 범위에 한계 있음'} for s in ('internal','external')}
 if case['citations']=='foreign':item['internal']['citations']=[{'evidence':'external','quote':'external'}]
 elif case['citations']=='unknown':item['internal']['citations'][0]['evidence']='fabricated'
 elif case['citations']=='altered':item['internal']['citations'][0]['quote']='invented'
 if case['retained']:
  for s in item:item[s]['alternatives']=[{'text':'앞서 확인','citations':item[s]['citations'],'dependencies':[]}];item[s]['citations']=[]
 state={'scope':{'issues':[{'id':'i'}]},'task_board':{'rows':{'i:f':{'issue_id':'i','field':'condition','current':item}}}}
 if case['gap']!='none':state['rag_results']={'internal':{'side':'internal','bundle':{'gaps':[{'kind':'MISSING_SOURCE','material':True,'parent_issue_refs':['i'] if case['gap']=='mapped' else [],'missing_target':'예외 조항','reason':'후속 확인 필요'}]}}}
 before=deepcopy(item);error=None;out=None
 try:out=basis.from_items(ctx,state)
 except ValueError as exc:accepted=False;error=str(exc)
 else:accepted=True
 pairs=len(out['pairs']) if out else 0
 passed=accepted==case['valid'] and (not accepted or pairs==int(case['pair'])) and item==before
 rows.append({**case,'accepted':accepted,'pair_count':pairs,'passed':passed,'error':error})
v={'total':len(rows),'passed':sum(r['passed'] for r in rows),'invalid_accepted':sum(r['accepted'] and not r['valid'] for r in rows),'model_calls':0,'cases':rows,'seconds':time.monotonic()-start,'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'legal_correctness_evaluated':False};(A/'artifacts/direct-matrix.json').write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in v.items() if k!='cases'}));assert v['passed']==168
