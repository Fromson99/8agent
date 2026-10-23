"""Offline, immutable-input replay. This runner has no model client or network."""
from pathlib import Path
from types import SimpleNamespace as S
from copy import deepcopy
import sys,json,hashlib
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1004-saved-termination-response-replay';ART=ADR/'artifacts';SOURCE=ROOT/'04_EXPERIMENTS/ADR/ADR-1002-answer-progress-termination/artifacts'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
mode=sys.argv[1]
if mode=='prepare':
 m=read(ADR/'실험/manifest.json');reason='Offline decision/schema replay only; no retrieval, product change or new model call.'
 m['design'].update(hypothesis='Six preserved raw responses can be checked against exact original schemas, projection and pre-existing expected actions despite the original envelope-reading failure.',primary_metric='Exact input/schema identity and six canonical decisions versus pre-existing labels.',success_criteria='All six original hashes unchanged; payload and schema match original stage request exactly; raw response validates and canonical projection matches pre-existing expected action and target; no model/network call.',failure_criteria='Any input/schema/hash mismatch, invalid response, changed target or action mismatch fails; preserve failures without changing originals.',criteria_frozen_before_run=True,sampling='All six previously exposed saved replies, no exclusions; compatibility audit only, no new behavioral/model-quality trial.')
 m['design']['code_isolation']['reason']=reason
 for a in m['design']['arms']:a.update(changes='Read-only replay of ADR1002 '+a['id']+' outputs and exact code',controls='Original inputs, raw replies and frozen action labels; no external client')
 m['lineage']['hypothesis_delta']=m['design']['hypothesis']
 m['runs'][0].update(purpose='regrade',selection_rule=m['design']['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
 m['dataset'].update(name='ADR1002 six saved synthetic navigation responses',version='saved-20261022-v1',frozen_source=str((SOURCE/'stage-inputs.json').relative_to(ROOT)),sha256=sha(SOURCE/'stage-inputs.json'),legal_version_checked=False,reference_version_checked=False,version_scope='Synthetic source rules; no legal-answer claim')
 m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
 m['llm_policy']['llm_calls']=[]
 save(ADR/'실험/manifest.json',m)
 files=[SOURCE/'stage-inputs.json',SOURCE/'stage-gold.json',SOURCE/'design-freeze.json',SOURCE/'stage.json',Path(__file__)]
 files+=list((SOURCE/'paired').rglob('stage-request.json'))+list((SOURCE/'paired').rglob('response.json'))
 save(ART/'freeze.json',{'design':m['design'],'files':{str(p.relative_to(ROOT)):sha(p) for p in files}})
 print('Frozen offline replay; model budget0')
 raise SystemExit
arm=mode;assert arm in ('baseline','candidate');f=read(ART/'freeze.json');assert all(sha(ROOT/n)==h for n,h in f['files'].items())
s=read(SOURCE/'stage.json');C=ROOT/(s['base_release']['code_root'] if arm=='baseline' else s['roots']['candidate'])
files=s['base_release']['files'] if arm=='baseline' else read(SOURCE/'design-freeze.json')['files']['candidate'];assert all(sha(C/n)==h for n,h in files.items())
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'02_BACKEND')]
from semantic_runtime.legal_agent import decision_projection as dp,law_navigation as nav,output_contract as oc,investigation_scope as scope
from jsonschema import validate
results=[]
for row in read(SOURCE/'stage-inputs.json'):
 case_id=row['id'];saved_dir=SOURCE/'paired'/case_id/arm;original=read(saved_dir/'stage-request.json');raw_path=next((saved_dir/'model').glob('call-*/response.json'));provider_body=read(raw_path);value=json.loads(provider_body['choices'][0]['message']['content'])
 data=deepcopy(row['data']);actions=deepcopy(row['actions']);events=[]
 def check(v,d,a):validate(v,nav.decision_schema(d,a,set()));scope.validate(v,d)
 inv=S(modern=True,control=False,policy={'answer_progress_control':arm=='candidate'},p={'binding':{'synthetic':'stage-v1'}},s=S(repo=S(budget=lambda:dict(model_limit=40,model_reserved=0,finalization_reserve=3),event=lambda *x:events.append(x))),question=row['question'],save=lambda:None,validate=check,left=lambda:180)
 if row['prior_opinion']:
  prior_value={'choice':'READ','selections':[{'target':'previous','issue_id':'Q1','missing_need':'제2조 지급 항목 확인','relation':'DEPENDENCY','source_ref':'E1'}]}
  inv.p['executed_compact_choices']=[deepcopy(prior_value)]
  if arm=='candidate':
   from semantic_runtime.legal_agent import answer_progress as ap
   prior_value['answer_progress']={'status':'NEEDS_SOURCE','answer_so_far':'경비 항목은 제2조에 위임되어 있다.','basis_refs':['E1'],'material_need':'국내 출장 경비 항목','next_answer_change':'위임된 지급 항목을 알 수 있다.','previous_effect':'INITIAL'}
   ap.record(inv,data,prior_value,'synthetic-prior-opinion')
 def offline(repo,owner,payload,schema,invoke,validator,**kw):
  assert payload==original['view'],'original model input changed'
  assert schema==original['schema'],'original schema changed'
  validate(value,schema);validator(value);return deepcopy(value)
 oc.bounded_decision=offline
 result={'case_id':case_id,'arm':arm,'raw_response':str(raw_path.relative_to(ROOT)),'new_model_calls':0}
 try:
  decision=dp.choose_read(inv,data,actions,'source-law-navigation');gold=read(SOURCE/'stage-gold.json')['cases'][case_id]
  expected='FINISH' if gold['choice']=='FINISH' else 'READ_ARTICLES'
  correct=decision['next_action']==expected and ('target' not in gold or decision['targets']==[gold['target']])
  result.update(passed=correct,decision=decision,input_exact=True,schema_exact=True)
 except Exception as exc:result.update(passed=False,error={'type':type(exc).__name__,'message':str(exc)})
 results.append(result)
save(ART/(arm+'.json'),results);print(json.dumps({'arm':arm,'passed':sum(r['passed'] for r in results),'total':len(results),'model_calls':0},ensure_ascii=False))
