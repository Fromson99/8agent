"""Known original packet through exact candidate pairing, projection and COMPARE."""
from pathlib import Path
from types import SimpleNamespace as S
import ast,hashlib,json,sys,time
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0841-comparison-direct-review';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
f=read(D/'freeze.json');assert all(sha(R/n)==h for n,h in f['files'].items());C=R/f['code_root'];sys.dont_write_bytecode=True;sys.path[:0]=[str(C/'02_BACKEND'),str(R/'02_BACKEND')]
import lawrag;lawrag.__path__.append(str(R/'02_BACKEND/lawrag'))
from lawrag.research.experiment_client import ExperimentClient
from workflow.adapters.projection import prepare
from workflow.adapters.model import SYSTEM
from workflow.risk_team_compare_workflow import basis,compare
from workflow import presentation
record=read(D/'known-packet.json');state=record['state'];sources=record['sources']
presentation.evidence=lambda ctx,state,ids=None:[s for s in sources if ids is None or s['evidence_id'] in ids]
ctx=S(request={'as_of':record['view']['as_of']},repo=S(save=lambda state:None))
selected=basis.from_items(ctx,state);assert len(selected['pairs'])==2
syntax=ast.parse((C/'02_BACKEND/workflow/risk_team_compare_workflow/compare.py').read_text())
instructions=next(ast.literal_eval(n.args[3]) for n in ast.walk(syntax) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='decide' and n.args and isinstance(n.args[0],ast.Constant) and n.args[0].value=='COMPARE')
system=SYSTEM+'\n'+instructions+'\n인용은 citation_options의 citation_id만 선택한다. 인용 원문과 서버 소유 필드는 시스템이 조립한다.'
O=A/'artifacts/model';O.mkdir(exist_ok=False);client=ExperimentClient(R,O/'raw',max_calls=2,max_output_tokens=6400,max_repairs=0);results=[];start=time.monotonic()
for pair in selected['pairs']:
 ids=set(pair['internal']+pair['external']);visible=[s for s in sources if s['evidence_id'] in ids]
 one={'pairs':[pair],'gaps':[g for g in selected['gaps'] if g['issue_id']==pair['issue_id']],'summary':pair['reason']}
 data={k:v for k,v in record['view'].items() if k!='child_gap_constraints'};data.update(basis=one,sources=visible,phase='compose',source_stage='workflow-compare')
 data['packet']={**data['packet'],'evidence_ids':sorted(ids)}
 projected,schema,expand,receipt=prepare('COMPARE',data,compare.COMPARE)
 row={'issue_id':pair['issue_id'],'sources':len(visible),'source_pair':pair,'known_in_sample':True,'projection':receipt}
 try:
  raw=client.generate(system,{'output_schema':schema,'view':projected},schema,phase='workflow-compare')
  value=expand(raw);row['proposal']=value;compare.validate(value,visible,one,state['scope']['issues']);assert {r['pair_id'] for r in value['rows']}=={pair['pair_id']};row['accepted']=True
 except Exception as exc:row.update(accepted=False,error_type=type(exc).__name__,error=str(exc)[:1000])
 results.append(row);(O/'partial.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'issue':row['issue_id'],'accepted':row['accepted'],'rows':len(row.get('proposal',{}).get('rows',[]))}),flush=True)
result={'results':results,'model_calls':client.calls,'usage':client.usage,'seconds':time.monotonic()-start,'actual_end_to_end':False,'retrieval_rerun':False,'quality_certified':False,'code_root':f['code_root']}
(O/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
