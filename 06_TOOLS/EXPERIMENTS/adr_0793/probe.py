"""Frozen deterministic initial-menu probe; no model/gold input to selection."""
from pathlib import Path
import json,sys,os,hashlib,gzip,time
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0793-definition-entry-navigation';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'probe-freeze.json');arm=sys.argv[1];C=R/f['code_roots'][arm]
assert all(hashlib.sha256((R/n).read_bytes()).hexdigest()==h for n,h in f['files'].items())
sys.dont_write_bytecode=True;sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(R/'02_BACKEND')]
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(R),SOURCE_PROVIDER_PROJECT_ROOT=str(R))
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
from semantic_runtime.legal_agent.source_recall import SourceRecall
from semantic_runtime.legal_agent.law_navigation import Investigation
from semantic_runtime.legal_agent.navigation_input import NavigationReferences,compact_cards
T=LocalGemmaTransport(C,R);G=R/read(D/'data-binding.json')['path'];profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile['model_binding']=T.binding
O=A/'artifacts/run-001'/arm;O.mkdir(parents=True,exist_ok=False)
app=create_app(R,G,contracts_root=C,workspace_root=R,provider=object(),implementation='legal-agent-unified-v6',runtime_root=O/'runtime',legal_agent_profile=profile,legal_agent_transport=T)
p=app.state.pipeline;q=read(D/'criteria.json')['live']['question'];scope=T.public_scope
request={'question':q,'document_ids':sorted(scope),'use_llm':False,'public_question':True}
started=time.monotonic()
try:
 with p.term_agent.open_session(request,query=p.plan(q,sorted(scope)),runtime=O/'native') as native:
  s=native.sources;s.entry_search={'mode':'FULLTEXT','queries':['유동성비율 외부규정','유동성비율 내부규정','유동성비율 규정 비교']};s.recall_query_plan={'queries':s.entry_search['queries'],'law_names':[]}
  rec=SourceRecall(s).prepare();inv=Investigation(s,q,rec,None,120,None,None);view,actions=inv.view()
  def ids(values):
   rows={json.dumps({'doc_id':s.tools.sources[i]['document_id'],'node':int(s.tools.sources[i]['unit_id'])},sort_keys=True) for i in values}
   return [json.loads(r) for r in sorted(rows)]
  allids=[i for i,x in s.tools.sources.items() if x['document_id'] in scope]
  recalled=[h['source_id'] for h in rec.get('unit_hits',[])]
  offered=[a['identity']['source_id'] for a in actions.values() if a['action']=='READ_ARTICLES']
  full={'view':view,'actions':actions,'model_view':NavigationReferences(view).view(compact_cards(view)),'record':rec}
  with gzip.open(O/'view.json.gz','wt',encoding='utf-8') as z:json.dump(full,z,ensure_ascii=False)
  rows=view.get('definition_entries',{}).get('items',[])
  result={'arm':arm,'corpus':ids(allids),'recalled':ids(recalled),'offered':ids(offered),'definition_count':len(rows),'definitions':rows,'model_calls':0,'code_root':str(C.relative_to(R)),'elapsed_seconds':time.monotonic()-started}
  put(O/'result.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ('corpus','recalled','offered','definitions')},ensure_ascii=False),flush=True)
finally:p.store.close()
