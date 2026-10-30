"""Predeclared small saved-input experiment; no corpus load or next tool execution."""
from common import *
import sys,os,gzip,resource,time
from copy import deepcopy
from types import SimpleNamespace as NS
sys.dont_write_bytecode=True
f=read(DES/'freeze.json');C=ROOT/f['code_root'];mode='--prepare' in sys.argv
for n,h in f['files'].items():assert sha(C/n)==h,n
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'02_BACKEND')]
from semantic_runtime.legal_agent import investigation_supervisor as su
from semantic_runtime.legal_agent.navigation_input import NavigationReferences
from semantic_runtime.legal_agent import compact_model_input as minimal
from semantic_runtime.legal_agent.local_gemma import provider_request
from semantic_runtime.legal_agent.model_contract import structured_value
from semantic_runtime.contracts import digest
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
from lawrag.research.experiment_client import ExperimentClient
from jsonschema import validate
out=ART/'saved-input-probe';out.mkdir(exist_ok=True)
base=ROOT/'04_EXPERIMENTS/ADR/ADR-1161-cm3-focused-qwen/artifacts/run-001';allowed=set(read(DES/'corpus.json')['document_ids']);cases={c['id']:c for c in read(DES/'cases.json')}
summary=[]
for cid in ('cm-007','cm-009'):
 p=out/cid;p.mkdir(exist_ok=True)
 if mode:
  original=base/cid/'canonical/008.json.gz';prior=base/cid/'canonical/008-output.json.gz'
  src=json.load(gzip.open(original,'rt'));v=src['view'];proposal=json.load(gzip.open(prior,'rt'))
  assert v['current_request']==cases[cid]['request']['json']['question']
  assert all(s['document_id'] in allowed for s in v.get('sources',[]))
  sch=deepcopy(src['schema'])
  sch['anyOf']=[b for b in sch['anyOf'] if b['properties']['choice'].get('const') not in ('NEXT_READ_CANDIDATES','PREV_READ_CANDIDATES','NEXT_TOOL_CANDIDATES','PREV_TOOL_CANDIDATES')]
  for b in sch['anyOf']:
   for k in ('read_review','answer_progress'):b['properties'].pop(k,None)
   b['required']=[k for k in b['required'] if k not in ('read_review','answer_progress')]
  fake=NS(question=v['current_request'],p={'binding':digest([str(original),sha(original)])},policy={'supervisor_mode':'enforce'},s=NS(repo=NS(budget=lambda:dict(model_limit=40,model_reserved=8,finalization_reserve=3))),save=lambda:None)
  data={**v,'laws':[{'document_id':d['document_id'],'name':d['name']} for d in v.get('document_structures',[])]}
  state=su.state_for(fake,data);state['goals']=deepcopy(v.get('answer_progress_context',{}).get('current_goals',[]));state['unchanged']=deepcopy(v.get('answer_progress_context',{}).get('unchanged_steps_by_issue',{}));state['state_hash']=su.seal(state)
  payload=su.review_payload(fake,data,v,proposal,state,'SAVED_NO_ANSWER_PROGRESS');payload['reference_registry']=v['reference_registry'];payload['source_stage']='source-law-navigation-supervisor-read-choice'
  # Preserve exact prior catalog/aliases; quantities unavailable in captured view stay unknown.
  schema=su.schema_for(sch);refs=NavigationReferences({**v,**payload});wire_schema=refs.schema(schema);wire_view=minimal.project(refs.view(payload),wire_schema)
  body={'model':'qwen/qwen3.8-27b','messages':[{'role':'system','content':su.PROMPT+'\n'+minimal.INSTRUCTIONS},{'role':'user','content':json.dumps({'view':wire_view},ensure_ascii=False)}],'stream':False,'temperature':0,'response_format':{'type':'json_schema','json_schema':{'name':'InvestigationSupervisor','strict':True,'schema':wire_schema}}}
  put(p/'request.json',body);put(p/'canonical.json',{'view':payload,'schema':schema,'mapping':refs.forward,'wire_schema':wire_schema});put(p/'source-binding.json',{'input_path':str(original.relative_to(ROOT)),'input_sha256':sha(original),'proposal_path':str(prior.relative_to(ROOT)),'proposal_sha256':sha(prior),'gold_visible':False,'counterfactual_only':True,'frontier_counts':'not available in captured compact view; not invented','full_pipeline_executed':False})
  print(cid,'prepared',len(json.dumps(body,ensure_ascii=False)),'chars',flush=True);continue
 assert sha(p/'request.json')==read(out/'freeze.json')['requests'][cid]
 if (p/'result.json').exists() or (p/'raw').exists():raise RuntimeError('No same-fixture retry')
 client=ExperimentClient(ROOT,p/'raw',max_calls=1,max_output_tokens=None,max_repairs=0)
 started=time.monotonic();row={'case':cid,'full_pipeline_executed':False,'tool_execution':False,'legal_quality_certified':False}
 try:
  body=read(p/'request.json');res=client.chat_completions(provider_request(body),phase='saved-supervisor-probe',timeout_seconds=180)
  parsed=structured_value(res['body_json']);canon=read(p/'canonical.json');validate(parsed,canon['wire_schema'])
  refs=object.__new__(NavigationReferences);refs.stable=True;refs.forward=canon['mapping'];refs.reverse={v:k for k,v in refs.forward.items()};restored=refs.restore(parsed);validate(restored,canon['schema'])
  put(p/'decision.json',restored);row.update(status='completed',directive=restored['directive'],reason=restored['reason'],remaining_scope=restored['remaining_scope'])
  if 'action' in restored:row['action']=restored['action']
 except Exception as e:row.update(status='failed',error_type=type(e).__name__,error=str(e))
 row.update(physical_calls=client.calls,usage=client.usage,seconds=time.monotonic()-started,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss);put(p/'result.json',row);summary.append(row);print(cid,row['status'],row.get('directive'),client.calls,flush=True)
 if row['status']=='failed':break
if mode:
 put(out/'freeze.json',{'requests':{c:sha(out/c/'request.json') for c in ('cm-007','cm-009')},'code_revision':f['candidate_revision'],'runner_sha256':sha(Path(__file__)),'physical_call_limit':2,'each_fixture_once':True,'evaluation_only_references_in_payload':False})
else:put(out/'result.json',{'cases':summary,'full_case_runs':0,'physical_calls':sum(r['physical_calls'] for r in summary),'main_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']})
