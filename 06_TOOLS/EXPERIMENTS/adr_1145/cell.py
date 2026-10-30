"""Frozen direct ASSESS selector probe using saved exact source input.

Full native HTTP integration is verified separately by synthetic transport.
This is NOT a new end-to-end navigation run or a paired latency experiment.
"""
from common import *
import sys,os,gzip,time,sqlite3,resource,traceback
from types import SimpleNamespace
sys.dont_write_bytecode=True
resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
arm,case_id,rep=sys.argv[1:];f=read(ART/'freeze.json');binding=f['arms'][arm];code=ROOT/binding['code_root'];sys.path.insert(0,str(code/'02_BACKEND'))
for n,h in binding['files'].items():assert sha(code/n)==h,n
for n,h in f['inputs'].items():assert sha(ROOT/n)==h,n
for n,h in f['scripts'].items():assert sha(ROOT/n)==h,n
assert read(ART/'check-001.json')['status']==0
# The immutable MAIN108 baseline is bound even if another task promotes MAIN concurrently.
from semantic_runtime.legal_agent import ontology_scenarios as sc, ontology_scenario_runtime as rt,completion_contracts as cc,output_contract as output
from semantic_runtime.legal_agent.memory_rag import NativeExecution
from semantic_runtime.contracts import digest
from lawrag.research.experiment_client import ExperimentClient,_schema_for_api,ExperimentFormatError
p=ROOT/f['source_view'];saved=json.loads(gzip.decompress(p.read_bytes()))['view'];originals=read(ART/'build-input.json')['originals'];bylabel={p['anchor']['label']:p for p in saved['ontology_bundles'][0]['payload']['provisions']}
fragments=[{'anchor':s['anchor'],'text':s['text'],'evidence_refs':bylabel[s['anchor']['label']]['source_refs']} for s in originals]
options=saved['evidence_options'];byref={o['id']:o for o in options}
for s in originals:
 refs=bylabel[s['anchor']['label']]['source_refs'];pieces=[byref[r]['text'] for r in refs]
 assert all(t in s['text'] for t in pieces)
 assert ''.join(s['text'].split())==''.join(''.join(pieces).split()),s['id']
package=read(ART/'package.json');assert sha(ART/'package.json')==read(ART/'build-result.json')['package_sha256']
catalog=sc.bind_current(package,fragments)
# Reconstruct only the saved exact ASSESS span containers. No source discovery/query.
sources=[]
for header in saved['sources']:
 rows=[o for o in options if o['source_id']==header['source_id']]
 sources.append({**header,'text':'\n'.join(o['text'] for o in rows),'adopted_spans':[{k:o[k] for k in ('block_id','start_cp','end_cp','text','evidence_id')} for o in rows]})
assert cc.evidence_options(sources)==options
RUN=ART/'run-001'/arm;RUN.mkdir(parents=True,exist_ok=True)
class Journal:
 def __init__(self,path):
  self.binding={'experiment':'ADR1145','source':'saved-exact-assess'};self.db=sqlite3.connect(path)
  self.db.execute('CREATE TABLE event(seq INTEGER PRIMARY KEY,kind TEXT,payload_json TEXT,payload_hash TEXT)')
 def budget(self):return {'model_limit':40,'finalization_reserve':4,'model_reserved':client.calls}
 def event(self,kind,value):
  self.db.execute('INSERT INTO event(kind,payload_json,payload_hash) VALUES(?,?,?)',(kind,json.dumps(value,ensure_ascii=False),digest(value)));self.db.commit()

all_results=[]
for case in [c for c in read(ART/'cases.json') if c['id']==case_id]:
 out=RUN/(case['id']+'__r'+rep);assert not out.exists(),'Case cannot rerun';out.mkdir()
 client=ExperimentClient(ROOT,out/'raw',max_calls=4,max_output_tokens=None,max_repairs=0)
 journal=Journal(out/'journal.sqlite');result={'arm':arm,'rep':int(rep),'case_id':case['id'],'mode':'direct-product-selector-with-saved-source-input','quality_certified':False};start=time.monotonic()
 class Host:
  def __init__(self):self.s=SimpleNamespace(work=journal,context=SimpleNamespace(remaining=lambda:1800-(time.monotonic()-start)),sources=SimpleNamespace(profile={'selection_time_reserve_seconds':30}));self.host=SimpleNamespace(binding={'experiment':'ADR1145','package':package['package_sha256']})
  def verify_claims(self,claims,src):return NativeExecution.verify_claims(self,claims,src)
  def invoke(self,system,data,schema,phase):
   put(out/f'input-{client.calls+1}.json',{'system':system,'data':data,'schema':schema})
   payload={'model':client.model,'messages':[{'role':'system','content':system},{'role':'user','content':json.dumps(data,ensure_ascii=False)}],'temperature':0,'stream':False,'response_format':{'type':'json_schema','json_schema':{'name':'scenario_choice','strict':True,'schema':_schema_for_api(schema)}}}
   print('MODEL',case['id'],client.calls+1,phase,flush=True)
   raw=client.chat_completions(payload,phase=phase,timeout_seconds=180)
   try:value=output.strict_json(raw['body_json']['choices'][0]['message']['content'])
   except (KeyError,IndexError) as e:raise sc.ProposalError('incomplete provider output') from e
   put(out/f'output-{client.calls}.json',value);return value
 host=Host();issues=[{'id':'Q1','question':case['question']}]
 try:
  assessment=rt.assess(host,catalog,sources,options,issues,case['question'],{},None)
  sc.verify_selected_text(assessment)
  receipt=assessment['assessment_basis']['scenario_choice']
  put(out/'assessment.json',assessment)
  if receipt['effective_action']=='ANSWER':
   answer=cc.compose(assessment,cc.default_plan(assessment,'text',issues));cc.verify_composition(assessment,answer)
   put(out/'answer.json',answer);(out/'answer.txt').write_text(answer['text'])
  else:
   (out/'answer.txt').write_text('SEARCH_REQUESTED: this isolated selector probe stops before ordinary retrieval; the separate native case exercises it.')
  result.update(effective_action=receipt['effective_action'],selection_history=receipt['selection_history'],search_executed=False)
  result.update(status='complete',choice=assessment['assessment_basis']['scenario_choice']['choice'],selected_paths=assessment['assessment_basis']['scenario_choice']['selected_paths'],disposition=assessment['disposition'],original_options=len(options),scenario_paths_offered=len(catalog['paths']),legal_text_model_calls=0,compose_model_calls=0,final_body_exact=all(p['body_sha256']==digest(c['text']) for p,c in zip(assessment['assessment_basis']['scenario_choice']['selected_paths'],assessment['claims'])))
 except Exception as e:
  result.update(status='failed',error_type=type(e).__name__,error=str(e));(out/'error.txt').write_text(traceback.format_exc())
 finally:
  result.update(new_model_calls=client.calls,usage=client.usage,seconds=time.monotonic()-start,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss);put(out/'result.json',result);journal.db.close();all_results.append(result)
 print('CASE_DONE',case['id'],result['status'],result['new_model_calls'],round(result['seconds'],2),flush=True)
 # Unknown provider/transmission or integrity outcomes are not a prompt to spend another case.
 if result['status']=='failed':break
raise SystemExit(any(r['status']!='complete' for r in all_results))
