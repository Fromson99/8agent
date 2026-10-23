"""One recorded public scope decision using exact entry schema and resolver."""
from common import *
import sys,sqlite3,time,resource
from types import SimpleNamespace as S
sys.dont_write_bytecode=True
arm,cid=sys.argv[1:3];stage=read(ART/'stage.json');C=ROOT/stage['roots'][arm]
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'02_BACKEND')]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
from lawrag.research.experiment_client import ExperimentClient
from semantic_runtime.legal_agent import request_entry as entry, query_scope as qs
from semantic_runtime.legal_agent.law_title_hints import hints
from semantic_runtime.legal_agent.completion_v5 import SCOPE_PROMPT
from semantic_runtime.inherited_navigation import _derive_bindings
from jsonschema import validate
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
manifest=read(ADR/'실험/manifest.json');assert sha(ART/'probe-cases.json')==manifest['dataset']['sha256']
for row in read(ROOT/stage['candidate_dir']/'candidate.json')['revisions'][-1]['files']:
 if arm=='candidate':assert sha(ROOT/row['frozen_path'])==row['snapshot_sha256']
case=next(c for c in read(ART/'probe-cases.json') if c['id']==cid)
request=read(ROOT/'90_RUNTIME/manual_queries/special-resolution-20261022/retry/request.json')['json']
allowed=request['document_ids'];generation=ROOT/stage['base_release']['data_path']
db=sqlite3.connect('file:'+str(generation/'store.sqlite')+'?mode=ro',uri=True)
docs={};metadata={};aliases={};raw={}
for did,name,j in db.execute('SELECT document_id,name,json FROM document WHERE document_id IN (SELECT value FROM json_each(?))',(json.dumps(allowed),)):
 data=json.loads(j).get('document_metadata',{});docs[did]=name;metadata[did]=data
 if data.get('official_abbreviation'):aliases[did]=[data['official_abbreviation']]
 # Public structure metadata only; no body text or internal corpus enters the model.
 if data.get('document_title') in ('상법','민법'):
  for uid,parent,j in db.execute('SELECT unit_id,parent_id,json FROM source_unit WHERE document_id=?',(did,)):
   n=json.loads(j);raw[(did,str(uid))]={**n,'parent':str(parent) if parent is not None else None,'raw_structure':n}
units,coordinates=_derive_bindings(raw);db.close()
matcher=S(documents=docs,document_context=metadata,document_aliases=aliases,units=units,stored_coordinates=coordinates)
clues=hints(case['question'],matcher,allowed)
schema,quotes=entry.bind_task_quotes(entry.schema(True,model=True),case['question'])
system=entry.SYSTEM+(getattr(entry,'ENTRY_SCOPE_PROMPT',entry.SEARCH_SCOPE_PROMPT))+'\n'+SCOPE_PROMPT+' 이번 통합 입력에서는 배경을 context_quotes에만 작성한다. 각 issue의 request_quote는 시스템이 질문 원문 전체로 고정한다.'
payload={'question':case['question'],'current_goals':[], 'capabilities':entry.CAPABILITIES,
 'law_title_hints':clues,'request_quote_options':quotes}
out=ART/'probe'/cid/arm;assert not out.exists();out.mkdir(parents=True)
client=ExperimentClient(ROOT,out/'model',max_calls=1,max_output_tokens=6000)
result={'case_id':cid,'arm':arm,'error':None,'scope':None};start=time.monotonic()
try:
 raw=client.generate(system,payload,schema,phase='request-entry');result['raw']=raw
 value=entry.decode_scope(raw,clues) if hasattr(entry,'decode_scope') else raw
 context={'utterance':case['question'],'goals':[],'knowledge':[], 'allowed_documents':[{'id':d,'name':docs[d]} for d in allowed]}
 repo=S(_entry_title_hints=clues)
 routing,command,intent=entry.accept(repo,context,value,scoped=True,admit=False)
 result.update(routing=routing,command=command)
 if command and command.get('search_scope_change'):
  result['scope']=qs.resolve(command['search_scope_change'],None,matcher,allowed,case['question'])
except Exception as exc:
 result['error']={'type':type(exc).__name__,'message':str(exc)}
result.update(calls=client.calls,usage=client.usage,seconds=time.monotonic()-start,maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
save(out/'result.json',result)
print(json.dumps({'case':cid,'arm':arm,'error':result['error'],'documents':sorted({r['document_name'] for r in (result['scope'] or {}).get('targets',[])})},ensure_ascii=False),flush=True)
