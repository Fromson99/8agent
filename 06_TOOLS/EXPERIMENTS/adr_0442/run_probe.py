"""Explicit frozen navigation -> original select/assemble/answer, synthetic data only."""
from pathlib import Path
from types import SimpleNamespace
import argparse,hashlib,importlib,importlib.util,json,sys,time
R=Path('/home/jin/8-AGENT');D=R/'04_EXPERIMENTS/ADR/ADR-0442-schema-navigation-independent-probe';A=D/'artifacts';C=R/'02_BACKEND/lawrag/research/candidates/adr_0442/schema';RELEASE=Path('08_DEPLOYMENT/RELEASES/navigation-rag-20260916-v1/code');ARMS=['baseline','schema']
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rel(p):return str(Path(p).relative_to(R))
def new(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
def module(name,path,package=False):
 spec=importlib.util.spec_from_file_location(name,path,submodule_search_locations=[str(path.parent)] if package else None);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def load():
 cm=read(C/'candidate.json');rev=cm['revisions'][-1]
 for f in rev['files']:
  if sha(R/f['frozen_path'])!=f['snapshot_sha256']:raise ValueError('frozen revision drift')
 root=C/'revisions'/rev['revision_id']/'snapshot';runtime=root/RELEASE/'02_BACKEND/semantic_runtime';module('frozen442',runtime/'__init__.py',True)
 mods={key:importlib.import_module('frozen442.'+key) for key in ['navigation_loop','navigation_match','term_agent','contracts','stages']}
 mods['candidate']=module('candidate442',root/'02_BACKEND/semantic_runtime/schema_navigation.py');mods['fixture']=module('fixture442',root/'02_BACKEND/semantic_runtime/schema_probe_fixture.py')
 return mods,root/RELEASE
class Provider:
 def __init__(self,client):self.client=client
 def call(self,role,system,data,schema):return self.client.generate(system,data,schema,phase=role),self.client.usage[-1]
 def record_local(self,value):return {'kind':'local-contract','data':value}
def downstream(mods,root,session,state,case,provider):
 selected=sorted({j['source_id'] for j in state['adopted']});state.update(selected_ids=selected,use_llm=True,final={'findings':[{'text':j['claim'],'source_ids':[j['source_id']]} for j in state['adopted']],'evidence_ids':selected,'open_questions':[{'kind':'EVIDENCE','text':x} for x in state['stop']['unresolved']],'question_for_user':'','next_action':state['status']})
 retrieval={'term_agent':state,'candidates':[{**session.t.sources[s],'ancestors':[],'routes':['navigation'],'score':0} for s in state['read_source_ids']]}
 p=SimpleNamespace(store=SimpleNamespace(manifest={'data_status':'EXAMPLE','generation_id':'synthetic-0442-v1','store_sha256':sha(A/'dataset/corpus.json')}),provider=provider,contracts=mods['contracts'].Contracts(root))
 plan={'id':'query:'+case['id'],'question':case['question'],'scope':{'document_version_ids':case['scope_document_ids']}}
 selection=mods['stages'].select({'retrieved':{'retrieval':retrieval,'query':plan}},None,None)['selected']['selection'];assembly=mods['term_agent'].assemble(p,plan,selection)
 answer=mods['term_agent'].answer(p,plan,assembly)
 if state.get('catalogue') is not None:
  answer={'schema_version':'schema-navigation-probe-v2','kind':'CATALOGUE','text':f"조회 가능한 문서 {len(state['catalogue'])}개: "+', '.join(x['name'] for x in state['catalogue']),'items':state['catalogue'],'coverage':'COMPLETE_ALLOWED_SCOPE','claims':[],'unresolved':[]}
 return {'retrieval':retrieval,'selection':selection,'assembly':assembly,'answer':answer}
def prepare():
 m=read(D/'실험/manifest.json');cm=read(C/'candidate.json');rev=cm['revisions'][-1]
 m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'schema','experiment_id':m['experiment_id'],'arm_id':'schema','run_ids':['run-001'],'manifest_path':rel(C/'candidate.json'),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':rel(Path(__file__)),'runner_sha256':sha(__file__)}])
 (D/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 files=[A/'dataset/corpus.json',A/'dataset/product-cases.json',A/'design-before-snapshot.json',C/'candidate.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'02_BACKEND/lawrag/research/experiment_client.py',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json']+[R/x['frozen_path'] for x in rev['files']]+list(Path(__file__).parent.glob('*.py'))
 new(A/'input-lock.json',{'files':{rel(p):sha(p) for p in files},'gold_visible_to_product':False,'synthetic_only':True});new(A/'pre-call-manifest.json',m)
 print('Prepared hashes; no model calls')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--prepare',action='store_true');args=ap.parse_args()
 if args.prepare:return prepare()
 if (A/'runs').exists():raise ValueError('run exists: no automatic rerun')
 lock=read(A/'input-lock.json')
 for p,h in lock['files'].items():
  if sha(R/p)!=h:raise ValueError('input drift '+p)
 from lawrag.research.experiment_client import GeminiExperimentClient
 mods,root=load();corpus=read(A/'dataset/corpus.json');cases=read(A/'dataset/product-cases.json');limits=read(A/'design-before-snapshot.json')['design']['limits'];results={};(A/'runs').mkdir();start=time.monotonic()
 for i,case in enumerate(cases):
  for arm in ARMS if i%2==0 else list(reversed(ARMS)):
   m,t,g=mods['fixture'].build(corpus,mods['navigation_match']);cls=mods['navigation_loop'].NavigationSession if arm=='baseline' else mods['candidate'].session_class(mods['navigation_loop'])
   client=GeminiExperimentClient(R,A/'calls'/case['id']/arm,max_calls=limits['max_calls']);provider=Provider(client);started=time.monotonic();s=None
   try:
    s=cls(m,t,g,case['question'],case['scope_document_ids'],limits);state=s.run(provider);output=downstream(mods,root,s,state,case,provider)
    record={'case_id':case['id'],'arm_id':arm,'output':output,'downstream_contract':'PASS'}
   except Exception as e:record={'case_id':case['id'],'arm_id':arm,'output':None,'downstream_contract':'FAIL','failure':{'type':type(e).__name__,'message':str(e)}}
   finally:t.db.close()
   record.update(calls=client.calls,usage=client.usage,elapsed_seconds=time.monotonic()-started)
   new(A/'runs'/f"{case['id']}-{arm}.json",record);results.setdefault(case['id'],{})[arm]=record
   state=(record.get('output') or {}).get('retrieval',{}).get('term_agent',{})
   print(json.dumps({'case':case['id'],'arm':arm,'status':state.get('status'),'calls':client.calls,'read':state.get('read_source_ids',[]),'failure':record.get('failure') or state.get('failure')},ensure_ascii=False),flush=True)
 new(A/'results.json',{'cases':results,'elapsed_seconds':time.monotonic()-start,'main_wiring':'unchanged','gold_visible_to_product':False})
if __name__=='__main__':main()
