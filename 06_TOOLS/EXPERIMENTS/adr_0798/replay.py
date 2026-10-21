"""Read-only replay of the same recorded child returns through both handoffs.

This isolates transport policy, not retrieval quality. Native RAG is substituted
only by its exact saved envelope; publication refs and source bytes are checked.
"""
from pathlib import Path
from types import SimpleNamespace
import sys,json,sqlite3,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0798-workflow-handoff-scoped-question';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
arm=sys.argv[1];f=read(D/'freeze.json');base=read(D/'baseline.json')
C=R/(base['manifest']['code_root'] if arm=='baseline' else f['code_root'])
rf=read(D/'replay-freeze.json');assert sha(Path(__file__))==rf['runner_sha256']
sys.dont_write_bytecode=True;sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime import workflow_rag
from semantic_runtime.workflow_bridge import SourcePort,Services
from semantic_runtime.storage import Store
from semantic_runtime.legal_agent.repository import WorkRepository
from semantic_runtime.legal_agent.source_tools import SourceSession
from semantic_runtime.contracts import digest
from workflow.runtime import Runtime

class ReadOnlyChild:
 def __init__(self,path):
  self.path=Path(path);self.db=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True);self.db.row_factory=sqlite3.Row
  self.binding=json.loads(self.run()['binding_json'])
 def run(self):return dict(self.db.execute('SELECT * FROM run').fetchone())
 def budget(self):return dict(self.db.execute('SELECT * FROM budget').fetchone())
 def evidence(self,ident=None):return WorkRepository.evidence(self,ident)
 def close(self):self.db.close()
workflow_rag.UnifiedRepository=ReadOnlyChild
parent_id='58629daa5e05c9b00bbc21e4e4cec8de'
old=R/'04_EXPERIMENTS/ADR/ADR-0795-main72-workflow-comparison/artifacts/live-v2/runtime'
store=Store(R/read(D/'data-binding.json')['path'],verify=True)
nav=sqlite3.connect((store.path/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
parent=SimpleNamespace(db=sqlite3.connect(':memory:'));parent.db.row_factory=sqlite3.Row;collected={}
parent.db.execute('CREATE TABLE workflow_child_run(call_id TEXT,run_id TEXT,journal TEXT,binding_hash TEXT)')
parent.evidence=lambda ident=None:collected[ident] if ident else list(collected.values())
parent.event=lambda *a,**k:None
def observation(action,result,values=(),verify=None):
 for v in values:verify(v);collected[v['evidence_id']]=v
 return result
parent.record_observation=observation
session=SourceSession.__new__(SourceSession);session.store=store;session.repo=parent
session.context=SimpleNamespace(run_id=parent_id,query={'generation_id':store.manifest['generation_id']},
    request={'principal':{'user_id':'jin','team_id':'risk_team'},'use_llm':True,'as_of':None})
session.tools=SimpleNamespace(sources={});session.scope=[]
port=SourcePort.__new__(SourcePort);port.session=session;port._verification_deadline=None
service=Services.__new__(Services);service.runtime=old;service.release={};service.profile={'max_context_chars':10**9}
port.services=service;port.categories={};port.all_scope=[]
results={};inputs={}
for side in ('internal','external'):
 path=next((old/'workflows'/parent_id/'children'/side/'legal-agent/runs').glob('*/*/journal.sqlite'))
 child=ReadOnlyChild(path);rid=child.run()['run_id'];docs=child.binding['scope']['document_version_ids']
 envelope_path=old/'workflows'/parent_id/'children'/side/'runs'/(rid+'.json');envelope=read(envelope_path)
 assert sha(envelope_path)==rf['envelopes'][side]
 inputs[side]=[{'doc_id':e['document_id'],'node':int(e['unit_id'])} for e in child.evidence()]
 for e in child.evidence():session.tools.sources[e['source_id']]=json.loads(nav.execute('SELECT json FROM source WHERE id=?',(e['source_id'],)).fetchone()[0])
 session.scope+=docs;port.all_scope+=docs;port.categories.update({d:side for d in docs})
 key='recorded-'+side;parent.db.execute('INSERT INTO workflow_child_run VALUES(?,?,?,?)',(key,rid,str(path),child.run()['binding_hash']))
 service.pipeline=SimpleNamespace(run=lambda *a,**k:envelope)
 results[side]=workflow_rag.execute(port,{'operation':'ask_rag','side':side,'args':{'question':'유동성비율 관련 외부규정은 무엇이고 내부 규정에는 어떻게 되어 있나?','previous':None}},key)
 child.close()
state={'scope':{'issues':[{'id':'i1','label':'유동성비율','numeric':True}],'missing_user_facts':[]},'history':[],'gaps':[],'rag_results':results}
ctx=SimpleNamespace(rag=SimpleNamespace(port=port,evidence=port.evidence),request={'question':'유동성비율 관련 외부규정은 무엇이고 내부 규정에는 어떻게 되어 있나?','as_of':None},
    repo=SimpleNamespace(work=SimpleNamespace(budget=lambda:{})),context=SimpleNamespace(deadline_at='same-recorded-deadline'))
view=Runtime.view(SimpleNamespace(services=service),ctx,state)
coords=lambda rows:sorted({(r['doc_id'],r['node']) for r in rows})
selected=[{'doc_id':e['document_id'],'node':int(e['unit_id'])} for e in collected.values()]
result={'arm':arm,'code_root':str(C.relative_to(R)),'known_case_replay':True,'new_model_calls':0,
 'read':[{'doc_id':d,'node':n} for d,n in coords(sum(inputs.values(),[]))],
 'selected':[{'doc_id':d,'node':n} for d,n in coords(selected)],
 'evidence_count':len(collected),'original_chars':sum(len(s['text']) for e in collected.values() for s in e['spans']),
 'view_chars':len(json.dumps(view,ensure_ascii=False)),'within_100000':len(json.dumps(view,ensure_ascii=False))<=100000,
 'sides':{s:{'evidence_count':len(r['evidence_ids']),'counts':r.get('bundle',{}).get('counts')} for s,r in results.items()}}
out=A/'artifacts/replay';out.mkdir(exist_ok=True);(out/(arm+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('read','selected')},ensure_ascii=False))
nav.close();store.close()
