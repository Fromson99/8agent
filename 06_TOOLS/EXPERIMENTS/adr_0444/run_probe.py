"""Frozen actual CM inputs -> original Pipeline with explicit candidate object injection."""
from pathlib import Path
from copy import deepcopy
import argparse,hashlib,importlib,importlib.util,json,sys,time
R=Path('/home/jin/8-AGENT');D=R/'04_EXPERIMENTS/ADR/ADR-0444-cm-schema-navigation-real-probe';A=D/'artifacts';C=R/'02_BACKEND/lawrag/research/candidates/adr_0444/schema';G=R/'01_DATA/SEMANTIC/GENERATIONS/navigation-source-20260916-v1';RELEASE=Path('08_DEPLOYMENT/RELEASES/navigation-rag-20260916-v1/code');ARMS=['baseline','schema']
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
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
 snap=C/'revisions'/rev['revision_id']/'snapshot';root=snap/RELEASE;runtime=root/'02_BACKEND/semantic_runtime';module('frozen444',runtime/'__init__.py',True)
 mods={key:importlib.import_module('frozen444.'+key) for key in ['navigation_loop','navigation_agent','navigation_match','pipeline','storage']}
 mods['schema']=module('schema444',snap/'02_BACKEND/semantic_runtime/schema_navigation.py');mods['adapter']=module('adapter444',snap/'02_BACKEND/semantic_runtime/cm_schema_adapter.py');return mods,root
class Provider:
 def __init__(self,client):self.client=client
 def call(self,role,system,data,schema):
  value=self.client.generate(system,data,schema,phase=role);return value,self.client.usage[-1]
 def record_local(self,value):return {'kind':'local-contract','data':value}
def prepare():
 if (A/'input-lock.json').exists():raise ValueError('already sealed')
 m=read(D/'실험/manifest.json');cm=read(C/'candidate.json');rev=cm['revisions'][-1]
 m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'schema','experiment_id':m['experiment_id'],'arm_id':'schema','run_ids':['run-001'],'manifest_path':rel(C/'candidate.json'),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':rel(Path(__file__)),'runner_sha256':sha(__file__)}]);(D/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 files=[A/'dataset/product-cases.json',A/'design-before-snapshot.json',A/'authorization.json',A/'source-inventory.json',C/'candidate.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'02_BACKEND/lawrag/research/experiment_client.py',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json']+[R/f['frozen_path'] for f in rev['files']]+list(Path(__file__).parent.glob('*.py'))+[p for p in G.rglob('*') if p.is_file()]
 new(A/'input-lock.json',{'files':{rel(p):sha(p) for p in files},'gold_visible_to_product':False,'model':'gemini-3.1-flash-lite','source_scope':'same159documents authorized for prior CM51 experiment and explicitly requested again'})
 new(A/'grading-lock.json',{'files':{rel(A/'grading/gold.json'):sha(A/'grading/gold.json')},'visible_to_product':False});new(A/'pre-call-manifest.json',m);print('Input and grader locks sealed; no model calls',flush=True)
def check():
 mods,root=load();store=mods['storage'].Store(G);p=mods['pipeline'].Pipeline(root,store,Provider(None));nav=mods['navigation_agent'];agent=p.term_agent;tools=agent.get_index().tools(store.manifest['scope']['document_version_ids']);glossary=nav.glossary_assets(store.path,agent.config)
 try:
  matcher=nav.ReverseMatcher(store.db,tools,glossary);bound=mods['schema'].bind_source_structure(matcher,store);cls=mods['schema'].session_class(mods['navigation_loop']);s=cls(bound,tools,glossary,'연결 검사',store.manifest['scope']['document_version_ids'])
  did=sorted(s.scope)[0];sid=next(x for x in sorted(s.metadata) if s.metadata[x]['document_id']==did and s.metadata[x]['unit_id'] is not None)
  s.source_card(sid);out=s.read(sid);expected=tools.sources[sid]['text'];status='PASS' if out.get('text')==expected else 'BLOCKED' if out.get('status')=='BLOCKED' else 'FAIL'
  report={'scope_documents':len(s.scope),'source_count':len(s.metadata),'catalogue_total':s.catalog()['total'],'sample_source_id':sid,'sample_read_check':status,'sample_original_sha256':tools.sources[sid]['text_sha256'],'owner_mapping_units':len(bound.units),'semantic_capability':s.search('연결','semantic'),'schema_code_equals_parent':sha(C/'revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/schema_navigation.py')==sha(R/'02_BACKEND/lawrag/research/candidates/adr_0442/schema/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/schema_navigation.py'),'model_calls':0}
  s.searchdb.close();glossary.check_unchanged();new(A/'real-adapter-contract.json',report);print(json.dumps(report,ensure_ascii=False),flush=True)
  if status=='FAIL' or not report['schema_code_equals_parent']:raise ValueError('real adapter contract mismatch')
 finally:glossary.close();tools.db.close();store.close()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--prepare',action='store_true');ap.add_argument('--check',action='store_true');args=ap.parse_args()
 if args.prepare:return prepare()
 if args.check:return check()
 if (A/'runs').exists():raise ValueError('already started; no automatic rerun')
 lock=read(A/'input-lock.json')
 for path,h in lock['files'].items():
  if sha(R/path)!=h:raise ValueError('input drift '+path)
 from lawrag.research.experiment_client import GeminiExperimentClient
 mods,root=load();store=mods['storage'].Store(G);auth=read(A/'authorization.json');cases=read(A/'dataset/product-cases.json');limits=read(A/'design-before-snapshot.json')['design']['limits'];results={}
 assert auth['authorized'] and store.manifest['store_sha256']==auth['source_store_sha256'] and sha(A/'dataset/product-cases.json')==auth['product_cases_sha256']
 cls=mods['adapter'].adapter_class(mods['navigation_agent'],mods['navigation_loop'],mods['schema']);runtimes={}
 for arm in ARMS:
  p=mods['pipeline'].Pipeline(root,store,Provider(None));cfg=deepcopy(p.term_agent.config);cfg['limits']=limits;p.term_agent=cls(p,cfg) if arm=='schema' else mods['navigation_agent'].ServingNavigationAgent(p,cfg);runtimes[arm]=p
 (A/'runs').mkdir();started=time.monotonic()
 try:
  for i,c in enumerate(cases):
   if sorted(c['scope_document_ids'])!=sorted(auth['scope_document_ids']):raise ValueError('scope differs from authorization')
   for arm in ARMS if i%2==0 else list(reversed(ARMS)):
    client=GeminiExperimentClient(R,A/'calls'/c['id']/arm,max_calls=limits['max_calls']);p=runtimes[arm];p.provider=Provider(client);start=time.monotonic()
    try:
     out=p.run(c['question'],c['scope_document_ids'],True);p.contracts.validate(out,'urn:8-agent:term-runtime-v1','Result');record={'output':out,'downstream_contract':'PASS'}
    except Exception as e:record={'output':None,'downstream_contract':'FAIL','failure':{'type':type(e).__name__,'message':str(e)}}
    record.update(case_id=c['id'],arm_id=arm,calls=client.calls,usage=client.usage,elapsed_seconds=time.monotonic()-start);new(A/'runs'/f"{c['id']}-{arm}.json",record);results.setdefault(c['id'],{})[arm]=record;s=(record.get('output') or {}).get('retrieval',{}).get('term_agent',{})
    print(json.dumps({'case':c['id'],'arm':arm,'calls':client.calls,'status':s.get('status'),'read':len(s.get('read_source_ids',[])),'selected':len(s.get('selected_ids',[])),'seconds':round(record['elapsed_seconds'],2),'failure':record.get('failure') or s.get('failure')},ensure_ascii=False),flush=True)
  new(A/'results.json',{'cases':results,'elapsed_seconds':time.monotonic()-started,'main_wiring':'unchanged','gold_visible_to_product':False})
 finally:store.close()
if __name__=='__main__':main()
