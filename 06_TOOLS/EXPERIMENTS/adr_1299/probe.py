"""Current-code input/schema diagnosis; no network, model, product or corpus writes."""
from common import *
from copy import deepcopy
from types import SimpleNamespace
import os,sqlite3,time,collections
os.environ.update(OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2')
preflight='--preflight' in sys.argv
F=read(DES/'freeze.json') if not preflight else None
C=ROOT/F['code_root'] if F else ROOT/read(DES/'candidate.json')['path']/'snapshot'
sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import completion_v8 as v8,completion_execution as ce
from semantic_runtime.legal_agent import read_judgment_final as final,requirement_coverage as requirements,ontology_assessment as ontology
from semantic_runtime.legal_agent import compact_model_input as compact,stable_references as stable
from semantic_runtime.legal_agent.gateway import ModelGateway
from semantic_runtime.legal_agent.minimal_output import prepare_request
from semantic_runtime.legal_agent.local_gemma import provider_request
from semantic_runtime.legal_agent.navigation_input import expand_cards
from resource_guard import Guard
PRIOR=ROOT/read(DES/'inputs.json')['prior_artifacts'];P=PRIOR/'live/review-whatif'
base=read(P/'canonical/003.json.gz');actual=read(P/'raw/call-004/request.json.gz');profile=read(P/'binding.json')['profile']
def size(v):return len(json.dumps(v,ensure_ascii=False,separators=(',',':')).encode())
def walk(v,path=''):
 yield path,v
 if isinstance(v,dict):
  for k,x in v.items():yield from walk(x,path+'/'+k)
 elif isinstance(v,list):
  for i,x in enumerate(v):yield from walk(x,path+'/'+str(i))
def schema(v):
 s=v8.assessment_schema(v['issues'],[r['material_id'] for r in v['saved_inventory']],v['evidence_options'],v['user_fact_sources'],[])
 s=ce.bounded_judgment_notes(s)
 s=final.attach(s,v['read_judgments'],v['evidence_options'])
 s=requirements.attach(s,v['requirement_context'],v['evidence_options'])
 s=ontology.usage_schema(s,{'ontology_bundles':v['ontology_bundles']})
 return ce.assessment_projection(s,allowed_targets=['',*(r['target'] for r in v['locator_options'])])[0]
def wire(v,s):
 g=object.__new__(ModelGateway);g.profile=profile;g.compact=True;g.domain={};g.system='';g.prompts={'compose':''}
 g.transport=SimpleNamespace(binding=profile['model_binding']);g.protocol=SimpleNamespace(schema=lambda name:deepcopy(s))
 request=g.request('compose',v,'BoundedSourceDecision')
 request,_=prepare_request(request,g._generation_schema)
 request=provider_request(request)
 out=deepcopy(actual)
 out['response_format']['json_schema']['schema']=request['response_format']['json_schema']['schema']
 out['messages'][1]['content']=request['messages'][1]['content']
 return out
def calibration():
 s=schema(base['view']);r=wire(base['view'],s)
 checks={'generation_schema_exact':s==base['schema'],
  'provider_schema_exact':r['response_format']==actual['response_format'],
  'provider_user_exact':r['messages'][1]['content']==actual['messages'][1]['content']}
 return checks,s,r
if preflight:
 checks,s,r=calibration();out=ART/'preflight';out.mkdir(exist_ok=False)
 put(out/'result.json',checks)
 if not all(checks.values()):
  write_raw_json(out/'reconstructed.json.gz',{'schema':s,'request':r})
 print(json.dumps(checks));raise SystemExit(0 if all(checks.values()) else 1)
assert F and all(sha(C/n)==h for n,h in F['files'].items())
assert all(sha(ROOT/n)==h for n,h in F['inputs'].items())
assert all(sha(ROOT/n)==h for n,h in F['scripts'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==F['pointer_sha256']
RUN.mkdir(parents=True,exist_ok=False);guard=Guard(RUN);guard.start()
assert all(calibration()[0].values())

def bind(v,s):
 v=deepcopy(v);v.pop('reference_registry',None);v.pop('minimal_input_binding',None)
 v=compact.bind(v,s,stable=True,document_names={'synthetic-whatif-v1':'가정검증규정'})
 db=sqlite3.connect(':memory:');db.execute('CREATE TABLE navigation_handle(handle TEXT,kind TEXT,identity_json TEXT,binding_hash TEXT)')
 old=base['view']['reference_registry']
 for ident,alias in old['mapping'].items():db.execute('INSERT INTO navigation_handle VALUES(?,?,?,?)',('@model:'+alias,'model-reference-v2',json.dumps(ident),old['binding']))
 for row in old['documents']:db.execute('INSERT INTO navigation_handle VALUES(?,?,?,?)',('@model:'+row['id'],'model-document-v2',json.dumps({k:x for k,x in row.items() if k!='id'}),old['binding']))
 repo=SimpleNamespace(db=db,run=lambda:{'binding_hash':old['binding']},event=lambda *a:None)
 result=stable.bind(repo,v);db.close();return result

def fixture(n,mode,chars):
 v=deepcopy(base['view']);ctx=v['read_judgments'];continuity=ctx['need_continuity']
 per_targets=[t for t in continuity['targets'] if t['kind']=='SOURCE_GOAL']
 combined=next(t for t in continuity['targets'] if t['kind']=='STRUCTURE_SELECTION')
 for i in range(3,n+1):
  sid='S'+digest(['source',i])[:27];eid='E'+digest(['evidence',i])[:27];jid='J'+digest(['judgment',i])[:24];target='G'+digest(['target',i])[:25]
  source='article:'+digest(['article',i])[:24];text=(f'제{i}조 추가자료 {i}: '+('별도 작업의 대상과 조건 및 기록 범위를 확인한다. '*100))[:chars]
  op=deepcopy(v['evidence_options'][0]);op.update(id=sid,source_id=source,evidence_id=eid,block_id=str(i-1),start_cp=0,end_cp=len(text),text=text,text_hash=hashlib.sha256(text.encode()).hexdigest());v['evidence_options'].append(op)
  src=deepcopy(v['sources'][0]);src.update(source_id=source,unit_id=str(i-1),heading=f'제{i}조 추가자료',evidence_ids=[eid],evidence_refs=[sid]);v['sources'].append(src)
  head=deepcopy(ctx['judgments'][0]);head.update(id=jid,source_id=source,available_evidence_refs=[sid]);ctx['judgments'].append(head)
  expected={'block_id':str(i-1),'start_cp':0,'end_cp':len(text),'block_hash':digest(text)}
  t=deepcopy(per_targets[0]);t.update(id=target,origin_id='synthetic-goal-'+str(i),coordinate=f'제{i}조',expected=[expected],arrivals=[],available_evidence_refs=[sid]);per_targets.append(t)
  need={'id':target,'origin':'SOURCE_GOAL','text':f'제{i}조 대상과 조건을 확인한다.','issue_refs':['Q1'],'status':'OPEN','target_refs':[target]};ctx['needs'].append(need)
  combined['unit_ids'].append(str(i-1));combined['expected'].append(expected);combined['available_evidence_refs'].append(sid)
  v['locator_options'].append({'target':f'가정검증규정 제{i}조','document_id':'synthetic-whatif-v1'})
 if mode=='bulk':
  continuity['targets']=[combined];ctx['needs']=[x for x in ctx['needs'] if x['origin']!='SOURCE_GOAL']
 else:continuity['targets']=[*per_targets,combined]
 # Model-facing component fixtures, not forged acquired-source or approval receipts.
 v['requirement_context']=requirements.context(v['current_request'],v['issues'],v['evidence_options'])
 s=schema(v);return bind(v,s),s

def metrics(v,s,r):
 ws=r['response_format']['json_schema']['schema'];user=r['messages'][1]['content'];uv=json.loads(user);uv=uv.get('view',uv)
 restored=expand_cards(uv)
 all_strings=[x for _,x in walk(restored) if isinstance(x,str)]
 missing=[o['id'] for o in v['evidence_options'] if o['text'] not in all_strings]
 assert not missing,missing
 ctx=v['read_judgments'];counts={k:len(ctx[k]) for k in ('judgments','needs','conflicts')};counts['scope_reviews']=len(ctx['need_continuity']['targets'])
 nodes=[x for _,x in walk(ws) if isinstance(x,dict)]
 return {'request_bytes':size(r),'schema_bytes':size(ws),'system_bytes':len(r['messages'][0]['content'].encode()),'user_bytes':len(user.encode()),
  'source_utf8_bytes':sum(len(o['text'].encode()) for o in v['evidence_options']),
  'required_review_rows':counts,'required_review_rows_total':sum(counts.values()),
  'scope_evidence_memberships':sum(len(t['available_evidence_refs']) for t in ctx['need_continuity']['targets']),
  'enum_entries_including_alternatives':sum(len(x.get('enum',[])) for x in nodes),
  'source_text_preserved':True,'actual_source_count':len(v['evidence_options'])}

rows=[]
try:
 for case in read(DES/'cases.json'):
  guard.check();begin=time.perf_counter();v,s=fixture(case['source_count'],case['mode'],case['extra_text_chars']);r=wire(v,s)
  row={**case,**metrics(v,s,r),'construction_seconds':time.perf_counter()-begin}
  raw=RUN/(case['id']+'.json.gz');ref=write_raw_json(raw,{'component_fixture':v,'generation_schema':s,'provider_request':r})
  row['raw']=ref;rows.append(row);put(RUN/(case['id']+'-summary.json'),row)
  print(case['id'],row['schema_bytes'],row['user_bytes'],row['required_review_rows_total'],flush=True)
 put(RUN/'result.json',{'status':'MEASURED','rows':rows,'calibration':calibration()[0],'model_calls':0,
  'code_files':len(F['files']),'product_changes':0,'main_changed':False,
  'limits':'Controlled ordinary ASSESS component construction. Synthetic added data, no actual retrieval or judgment. Not provider latency, legal quality, context-capacity certification or schema-caused-timeout proof. One construction per cell.'})
finally:
 guard.done.set();guard.thread.join(timeout=3)
