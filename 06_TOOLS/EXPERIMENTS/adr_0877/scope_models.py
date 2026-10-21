from pathlib import Path
import json,hashlib,sys,ast,time
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0877-original-context-qualification';D=A/'artifacts/design';read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
f=read(D/'freeze.json');assert all(sha(R/n)==h for n,h in f['files'].items())
C=R/f['code_root'];B=R/read(D/'baseline.json')['release']['code_root'];sys.dont_write_bytecode=True;sys.path[:0]=[str(C/'02_BACKEND'),str(R/'02_BACKEND')]
import lawrag;lawrag.__path__.append(str(R/'02_BACKEND/lawrag'))
from lawrag.research.experiment_client import ExperimentClient
from workflow.adapters.projection import prepare
from workflow.adapters.model import SYSTEM
from workflow.risk_team_compare_workflow.contracts import COMPARE
from workflow.risk_team_compare_workflow.compare import validate
from semantic_runtime.legal_agent.local_gemma import provider_request
from jsonschema import validate as validate_schema
O=A/'artifacts/scope-models';O.mkdir(exist_ok=False);client=ExperimentClient(R,O/'raw',max_calls=5,max_output_tokens=2400,max_repairs=0)
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def instructions(root):
 tree=ast.parse((root/'02_BACKEND/workflow/risk_team_compare_workflow/compare.py').read_text())
 call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='decide' and n.args and isinstance(n.args[0],ast.Constant) and n.args[0].value=='COMPARE')
 return ast.literal_eval(call.args[3])
results=[]
for case in read(D/'scope-cases.json'):
 for arm,root in [('baseline',B),('candidate',C)] if case['kind'].startswith('synthetic') else [('candidate',C)]:
  issue={'id':'q','label':case['question'],'numeric':False};sources=[]
  for side in ('internal','external'):
   sources.append({'evidence_id':side,'side':side,'document_id':side,'source_id':side,'metadata':{'source_kind':'synthetic' if side=='internal' or case['kind'].startswith('synthetic') else 'pinned_public_original'},'text':case[side], 'source_complete':True,'version_verified':False,'citation_names':[], 'parent_issue_refs':['q'], 'spans':[{'block_id':str(i),'start_cp':0,'end_cp':len(t),'text':t,'span_hash':hashlib.sha256(t.encode()).hexdigest()} for i,t in enumerate(case[side].splitlines())]})
  pair={'pair_id':'p','issue_id':'q','internal':['internal'],'external':['external'],'basis_path':[],'comparison_eligibility':True,'basis_relation':'CONTENT_ONLY','applicability':{'status':'UNKNOWN','reason':'Model evaluates scope','citations':[],'as_of':None},'reason':'Compare supplied originals','content_difference':'','content_citations':[]}
  data={'question':case['question'],'user_facts':case['facts'],'as_of':None,'scope':{'issues':[issue]},'basis':{'pairs':[pair],'gaps':[],'summary':'Explicit packet'},'sources':sources,'gaps':[], 'comparison_focus':{'issue':issue,'field_reviews':[]},'packet':{'dependency_closure_complete':True,'evidence_ids':['internal','external']}}
  view,schema,expand,receipt=prepare('COMPARE',data,COMPARE)
  prompt=SYSTEM+'\n'+instructions(root)+'\n인용은 citation_options의 citation_id만 선택한다. 인용 원문과 서버 소유 필드는 시스템이 조립한다.'
  body=provider_request({'model':'qwen/qwen3.8-27b','messages':[{'role':'system','content':prompt},{'role':'user','content':json.dumps({'view':view},ensure_ascii=False)}],'response_format':{'type':'json_schema','json_schema':{'name':'scope_check','strict':True,'schema':schema}},'temperature':0,'max_tokens':2400,'stream':False})
  start=time.monotonic();raw=client.chat_completions(body,phase=case['id']+'-'+arm,timeout_seconds=120);value=json.loads(raw['body_json']['choices'][0]['message']['content']);value=expand(value);validate_schema(value,COMPARE);validate(value,sources,data['basis'],[issue])
  results.append({'case':case['id'],'kind':case['kind'],'arm':arm,'result':value,'projection':receipt,'canonical_valid':True,'exact_citations':True,'seconds':time.monotonic()-start,'model':raw['body_json']['model'],'provider':raw['body_json']['provider']});put(O/'result.json',{'results':results,'usage':client.usage,'model_calls':client.calls,'complete':client.calls==5});print(case['id'],arm,'valid',flush=True)
