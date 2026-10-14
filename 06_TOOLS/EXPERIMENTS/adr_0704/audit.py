"""Frozen, model-free exhaustive presentation/observability qualification."""
from pathlib import Path
from copy import deepcopy
import ast,asyncio,hashlib,importlib.util,json,os,time,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0704-compact-progress-call-metrics';D=A/'artifacts/design';O=A/'artifacts/run-001';O.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
frozen=read(D/'freeze.json');codes=read(D/'bindings.json')['codes'];base=R/codes['baseline'];code=R/codes['compact-display']
assert not (O/'result.json').exists(), 'Formal outcomes are append-only'
assert all(sha(R/p)==h for p,h in frozen['files'].items())
def module(root,name):
 s=importlib.util.spec_from_file_location(name,root/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
os.environ['GENOS_RAG_PROGRESS_UI']='socketio'
modules={a:module(R/p,a) for a,p in codes.items()}
async def evaluate(w,scenario):
 d=w._ChatProgress({'socketIOClientId':'synthetic'});sent=[]
 async def emit(name,value,room):sent.append((name,deepcopy(value)))
 d.emit=emit
 raw=[]
 def ev(stage,kind='phase',**extra):
  return {'schema_version':'rag-progress-v1','kind':kind,'label':'원시 '+stage,'details':['PRIVATE_ACTIVITY'], 'basis':{'stage':stage,'kind':'CASE_STAGE_STARTED','detail_mode':'activity'},**extra}
 raw+=[ev('INTENT'),ev('PLAN'),ev('RECALL','candidate')]
 for cycle in range(scenario['cycles']):
  for n in range(scenario['repeats']):
   raw += [ev('READ','reading'),ev('READ','read_complete'),ev('SELECT','selected')]
  raw += [ev('ASSESS','decision')]
  if scenario['late']:raw += [ev('RECALL','candidate'),ev('READ','reading')]
  raw += [ev('COMPOSE'),ev('READ','heartbeat'),ev('READ','model_wait'),ev('READ','decision',basis={'kind':'MODEL_OUTPUT_INVALID','detail_mode':'full_error'},details=['PRIVATE_ERROR'])]
 raw += [ev('COMPOSE',basis={'kind':'OBS_EVENT','name':'request.finished'})]
 start=time.perf_counter()
 for row in raw:await d.progress(row)
 answer='검증용 답변 본문과 출처 [1]는 그대로입니다.'
 await d.finish(answer)
 cards=[v for k,v in sent if k=='agentFlowExecutedData'];tokens=''.join(v for k,v in sent if k=='token')
 return {'events':len(raw),'card_updates':len(cards),'cards':len(d.blocks),'serialized_card_bytes':len(json.dumps(cards,ensure_ascii=False).encode()),'elapsed_ms':(time.perf_counter()-start)*1000,'answer_exact':tokens==answer,'no_private_error':'PRIVATE_ERROR' not in json.dumps(cards),'no_raw_activity':'PRIVATE_ACTIVITY' not in json.dumps(cards),'stable_ids':len({x['nodeId'] for x in d.blocks})==len(d.blocks)}
rows=[]
for scenario in read(D/'matrix.json')['scenarios']:
 rows.append({'case':scenario,'by_arm':{a:asyncio.run(evaluate(w,scenario)) for a,w in modules.items()}})
# Normalize only reviewed observational additions; all product branching remains
# syntactically identical to the already qualified MAIN47 pipeline.
class RemoveObservation(ast.NodeTransformer):
 def visit_ImportFrom(self,n):
  return None if n.module=='execution_metrics' else n
 def visit_With(self,n):
  n=self.generic_visit(n);n.items=[x for x in n.items if not (isinstance(x.context_expr,ast.Call) and isinstance(x.context_expr.func,ast.Name) and x.context_expr.func.id=='transport_attempt')];return n
 def visit_FunctionDef(self,n):
  if n.name=='ask' and any(isinstance(x,ast.ImportFrom) and x.module=='execution_metrics' for x in n.body):return None
  if n.name=='execute_ask':
   n.name='ask';n.decorator_list=ast.parse("@app.post('/v1/rag/ask')\ndef ask(): pass").body[0].decorator_list
  return self.generic_visit(n)
 def visit_Call(self,n):
  n=self.generic_visit(n)
  if isinstance(n.func,ast.Name) and n.func.id=='ProgressCapture':n.keywords=[k for k in n.keywords if k.arg!='compact_public']
  return n
semantic={}
for name in ['app.py','legal_agent/gateway.py','request_report.py']:
 p='02_BACKEND/semantic_runtime/'+name
 semantic[p]=ast.dump(ast.parse((base/p).read_text()))==ast.dump(RemoveObservation().visit(ast.parse((code/p).read_text())))
allowed={'00_SYSTEM/PIPELINE.json','02_BACKEND/semantic_runtime/app.py','02_BACKEND/semantic_runtime/legal_agent/gateway.py','02_BACKEND/semantic_runtime/request_report.py','02_BACKEND/semantic_runtime/progress.py','08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'}
basefiles=read(D/'baseline.json')['manifest']['files'];changes=[p for p,h in basefiles.items() if sha(code/p)!=h]
no_other_changes=all(p in allowed or p.startswith('02_BACKEND/ENGINES/') for p in changes)
# Engine entrypoints, contract IDs and configuration remain unchanged; only
# hashes plus the newly explicit timing dependency may differ.
pins=True
for p in changes:
 if not p.startswith('02_BACKEND/ENGINES/'):continue
 b,c=read(base/p),read(code/p);bf=b.pop('files');cf=c.pop('files');pins &= b==c and set(cf)==set(bf)|{'02_BACKEND/semantic_runtime/execution_metrics.py'} and all(sha(code/x)==h for x,h in cf.items())
bp,cp=read(base/'00_SYSTEM/PIPELINE.json'),read(code/'00_SYSTEM/PIPELINE.json')
for p in [bp,cp]:
 for e in p['engines'].values():e.pop('sha256')
pins &= bp==cp
contracts=list(ET.parse(A/'artifacts/contracts/required.xml').iter('testcase'));failures=[t.get('name') for t in contracts if t.find('failure') is not None or t.find('error') is not None]
legacy=lambda p:{t.get('name') for t in ET.parse(p).iter('testcase') if t.find('failure') is not None}
baseline_legacy=legacy(A/'artifacts/contracts/baseline-legacy-repair.xml');development_legacy={x for x in legacy(A/'artifacts/contracts/development-rev001.xml') if x.startswith(('test_selection_errors_','test_progress_describes_','test_full_bounded_pipeline_'))}
checks={'bounded_summary_cards':all(x['by_arm']['compact-display']['cards']<=5 and x['by_arm']['compact-display']['card_updates']<=5 for x in rows),'stable_card_ids':all(x['by_arm']['compact-display']['stable_ids'] for x in rows),'private_error_and_activity_absent':all(x['by_arm']['compact-display']['no_private_error'] and x['by_arm']['compact-display']['no_raw_activity'] for x in rows),'answer_bytes_unchanged':all(v['answer_exact'] for x in rows for v in x['by_arm'].values()),'product_semantics_unchanged':all(semantic.values()),'retrieval_profiles_data_unchanged':no_other_changes,'explicit_engine_dependency_pins':bool(pins),'all_233_required_contracts':len(contracts)==233 and not failures,'legacy_failures_unchanged':len(baseline_legacy)==9 and baseline_legacy==development_legacy,'frozen_files_unchanged':all(sha(R/p)==h for p,h in frozen['files'].items()),'main_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(D/'baseline.json')['pointer_sha256']}
result={'strict_success':all(checks.values()),'checks':checks,'matrix':rows,'semantics':semantic,'by_arm':{a:{'status':'complete','cases':len(rows),'external_model_calls':0,'max_cards':max(x['by_arm'][a]['cards'] for x in rows),'total_card_bytes':sum(x['by_arm'][a]['serialized_card_bytes'] for x in rows)} for a in codes},'required_contracts':len(contracts),'known_legacy_failures':sorted(baseline_legacy),'model_calls':0,'semantic_quality_inherited_from':'ADR-0703-experiment-v1/structured-reading','quality_certified':False,'genos_deployed':False,'main_wiring':'unchanged'}
put(O/'result.json',result)
m=read(A/'실험/manifest.json');m['results'].update(status='complete',by_arm=result['by_arm'],comparisons=[],usage={'external_model_calls':0},latency={'scope':'synthetic presentation only'},error_taxonomy=[] if result['strict_success'] else [k for k,v in checks.items() if not v]);m['runs'][0].update(status='complete',sha256=sha(O/'result.json'));put(A/'실험/manifest.json',m)
print(json.dumps({'checks':checks,'by_arm':result['by_arm']},ensure_ascii=False,indent=2))
raise SystemExit(0 if result['strict_success'] else 1)
