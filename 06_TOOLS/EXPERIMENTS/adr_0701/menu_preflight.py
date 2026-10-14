from pathlib import Path
import json,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0701-structure-preserved-final-holdout';b=json.loads((A/'artifacts/design/bindings.json').read_text());code=R/b['stage'];sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
from semantic_runtime.legal_agent import structure_query as sq
out=A/'artifacts/menu-preflight';out.mkdir(exist_ok=True);t=LocalGemmaTransport(code,R);profile=json.loads((code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text());profile['model_binding']=t.binding
app=create_app(out,R/b['source_generation'],contracts_root=code,workspace_root=R,provider=object(),implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=t,runtime_root=out/'runtime',memory_identity=lambda _:None);p=app.state.pipeline;result=[]
for question,queries,did in [('전문평가제도 운영지침의 전문평가 대상기업은 어떤 기업인가요?', ['전문평가제도 운영지침','전문평가 대상기업'],'03585a977c8651b2'),('중소기업창업 지원법 시행령 제32조', ['중소기업창업 지원법 시행령 제32조','제32조'],'527731af0a9a554c')]:
 request={'question':question,'document_ids':list(t.public_scope),'use_llm':False}
 with p.term_agent.open_session(request,query=p.plan(question,list(t.public_scope)),runtime=out/'sessions') as s:
  page=sq.catalogue(s.sources.matcher,s.sources.scope,queries=[question,*queries],limit=12)
  docs=sorted({x['document_id'] for x in page['items']});assert docs==[did],docs;result.append({'question':question,'document_ids':docs,'items':len(page['items']),'total':page['total'],'model_calls':0})
p.store.close();(out/'result.json').write_text(json.dumps({'status':'passed','cases':result},ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
