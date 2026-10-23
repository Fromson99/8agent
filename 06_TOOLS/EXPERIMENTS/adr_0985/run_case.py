"""Exact entry decision plus separate gold-free metadata retrieval probe."""
from common import *
import sys,time,resource
from types import SimpleNamespace as S
sys.dont_write_bytecode=True
arm,cid=sys.argv[1:3];stage=read(ART/'stage.json');C=ROOT/stage['roots'][arm]
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'02_BACKEND')]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
from lawrag.research.experiment_client import ExperimentClient
from semantic_runtime.legal_agent import request_entry as entry,query_scope as qs,structure_query as sq
from semantic_runtime.legal_agent.law_title_hints import hints
from semantic_runtime.legal_agent.completion_v5 import SCOPE_PROMPT
from matcher import build
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
case=next(c for c in read(ART/'cases.json') if c['id']==cid);matcher,allowed=build(C)
if '--preflight' in sys.argv:
 for did in ('SYN_A','SYN_B'):
  scope=qs.resolve({'operation':'REPLACE','user_quote':matcher.documents[did], 'targets':[{'document':matcher.documents[did],'structure':None,'selection':None}]},None,matcher,allowed,matcher.documents[did]);assert scope
  assert len(sq.heading_term_candidates(matcher,{did},'단서와 무관한 질문',{}))==4
 save(ART/'fixture-preflight.json',{'passed':True,'documents':len(allowed),'synthetic_nodes':56,'model_calls':0});print('Preflight passed');raise SystemExit(0)
m=read(ADR/'실험/manifest.json');assert sha(ART/'cases.json')==m['dataset']['sha256']
for row in read(ROOT/stage['candidate_dir']/'candidate.json')['files']:
 if arm=='candidate':assert sha(C/row['target_path'])==row['snapshot_sha256']
clues=hints(case['question'],matcher,allowed);schema,quotes=entry.bind_task_quotes(entry.schema(True,model=True),case['question'])
system=entry.SYSTEM+getattr(entry,'ENTRY_SCOPE_PROMPT',entry.SEARCH_SCOPE_PROMPT)+'\n'+SCOPE_PROMPT+' 이번 통합 입력에서는 배경을 context_quotes에만 작성한다. 각 issue의 request_quote는 시스템이 질문 원문 전체로 고정한다.'
payload={'question':case['question'],'current_goals':[],'capabilities':entry.CAPABILITIES,'law_title_hints':clues,'request_quote_options':quotes}
out=ART/'trials'/cid/arm;out.mkdir(parents=True,exist_ok=False);client=ExperimentClient(ROOT,out/'model',max_calls=1,max_output_tokens=6000)
result={'case_id':cid,'arm':arm,'error':None,'scope':None};start=time.monotonic()
try:
 raw=client.generate(system,payload,schema,phase='request-entry');result['raw']=raw
 value=entry.decode_scope(raw,clues) if hasattr(entry,'decode_scope') else raw
 context={'utterance':case['question'],'goals':[],'knowledge':[], 'allowed_documents':[{'id':d,'name':matcher.documents[d]} for d in allowed]}
 routing,command,intent=entry.accept(S(_entry_title_hints=clues),context,value,scoped=True,admit=False)
 result.update(routing=routing,command=command)
 if command and command.get('search_scope_change'):result['scope']=qs.resolve(command['search_scope_change'],None,matcher,allowed,case['question'],**({'model_resolved':True} if arm=='candidate' else {}))
except Exception as exc:result['error']={'type':type(exc).__name__,'message':str(exc)}
probe=case['retrieval_input'];candidates=sq.heading_term_candidates(matcher,{probe['document_id']},probe['query'],{})
result['retrieval']={'input':probe,'candidates':[{'document_id':d,'canonical_coordinate':matcher.stored_coordinates[(d,u)].canonical_surface(),'unit_id':u} for d,u in sorted(candidates)],'universe':[{'document_id':probe['document_id'],'canonical_coordinate':f'제{n}조','unit_id':str(n)} for n in (21,24,25,26)]}
result.update(calls=client.calls,usage=client.usage,seconds=time.monotonic()-start,maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
save(out/'result.json',result)
print(json.dumps({'case':cid,'arm':arm,'error':result['error'],'scope':[(t['document_name'],t['unit_id']) for t in (result['scope'] or {}).get('targets',[])]},ensure_ascii=False),flush=True)
