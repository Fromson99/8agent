from pathlib import Path
from copy import deepcopy
import hashlib,json,sys,time,resource
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0838-comparison-judgment-qualification';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
arm=sys.argv[1];assert arm in ('baseline','connected');f=read(D/'freeze.json');assert all(sha(R/n)==h for n,h in f['files'].items())
b=read(D/'baseline.json')['manifest'];C=R/(b['code_root'] if arm=='baseline' else f['code_root']);files=b['files'] if arm=='baseline' else f['serving_files'];assert all(sha(C/n)==h for n,h in files.items())
sys.dont_write_bytecode=True;sys.path.insert(0,str(C/'02_BACKEND'))
from workflow.risk_team_compare_workflow import task_board as tb
sources=[{'evidence_id':s,'side':s,'text':t,'spans':[{'text':t,'block_id':'1','start_cp':0,'end_cp':len(t)}]} for s,t in [('internal','검토 후 보고한다.'),('external','보고한다.')]]
citations={s['side']:{'evidence':s['evidence_id'],'quote':s['text']} for s in sources};rows=[];start=time.monotonic()
for case in read(D/'cases.json'):
 item={'field':'procedure','content_status':case['comparison'],'difference':'현재 확보 범위에서 검토한 의견입니다.','next_tasks':[]}
 for side in ('internal','external'):
  cs=[dict(citations[side])] if case['citation_mode'] not in ('none',('external_only' if side=='internal' else 'internal_only')) else []
  item[side]={'status':case['status'],'text':'검토 의견과 미확보 설명입니다.','citations':cs,'dependencies':[],'scope_sufficient':False,'missing':'확인할 조건'}
 if case['citation_mode']=='foreign_side':item['internal']['citations']=[dict(citations['external'])]
 elif case['citation_mode']=='unknown':item['internal']['citations'][0]['evidence']='fabricated'
 elif case['citation_mode']=='altered':item['internal']['citations'][0]['quote']='보고를 생략한다.'
 before=deepcopy(item);error=None
 try:tb.checked({'items':[item]},sources,['procedure'],{})
 except ValueError as exc:accepted=False;error=str(exc)
 else:accepted=True
 rows.append({**case,'accepted':accepted,'pass':accepted==case['expected_accepted'] and item==before,'mutated':item!=before,'error':error})
value={'arm':arm,'cases':rows,'passed':sum(r['pass'] for r in rows),'total':len(rows),'false_positives':sum(r['accepted'] and not r['expected_accepted'] for r in rows),'elapsed_seconds':time.monotonic()-start,'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'model_calls':0,'legal_correctness_evaluated':False}
(A/f'artifacts/matrix-{arm}.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in value.items() if k!='cases'}))
