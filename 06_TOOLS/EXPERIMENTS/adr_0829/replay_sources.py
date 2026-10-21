"""Known ADR0827 fixture: read-only rendering check, not fresh model accuracy."""
from pathlib import Path
from types import SimpleNamespace as NS
import sqlite3,json,hashlib,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0829-comparison-main-qualification';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
f=read(D/'freeze.json');C=R/f['code_root'];sys.dont_write_bytecode=True;sys.path[:0]=[str(C/'02_BACKEND'),str(R/'02_BACKEND')]
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.repository import text_hash
from workflow.risk_team_compare_workflow.task_board import report
fixture=read(D/'known-replay.json');p=R/fixture['journal'];assert sha(p)==fixture['journal_sha256']
db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
saved=dict(db.execute('SELECT * FROM workflow_state').fetchone());state=json.loads(saved['checkpoint_json']);original=json.loads(saved['result_json']);assert digest(state)==saved['checkpoint_hash'] and digest(original)==saved['result_hash']
request=json.loads(saved['request_json']);assert digest(request)==saved['request_hash']
run=dict(db.execute('SELECT * FROM run').fetchone());binding=json.loads(run['binding_json'])
generation=R/read(D/'data-binding.json')['path'];nav=sqlite3.connect((generation/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
values=[];source_map={}
for row in db.execute('SELECT * FROM evidence_unit'):
 e=dict(row);e['metadata']=json.loads(e.pop('metadata_json'));e['spans']=[dict(s) for s in db.execute('SELECT * FROM evidence_span WHERE evidence_id=? ORDER BY ordinal',(e['evidence_id'],))];e['text']='\n'.join(s['text'] for s in e['spans']);assert text_hash(e['text'])==e['text_hash']
 source=json.loads(nav.execute('SELECT json FROM source WHERE id=?',(e['source_id'],)).fetchone()[0]);source_map[e['source_id']]=source
 blocks={b['block_id']:b['text'] for b in source['blocks']}
 for span in e['spans']:
  block=blocks[span['block_id']];assert text_hash(block)==span['block_hash'];assert block[span['start_cp']:span['end_cp']]==span['text'];assert text_hash(span['text'])==span['span_hash']
 values.append(e)
services=type('Native',(),{'__module__':'semantic_runtime.workflow_bridge'})()
ctx=NS(request=request,context=NS(binding_hash=run['binding_hash'],binding=binding,run_id=run['run_id']),
 repo=NS(state=lambda:{'revision':saved['revision']},work=NS(budget=lambda:original['usage'])),
 rag=NS(evidence=lambda:values,port=NS(services=services,session=NS(tools=NS(sources=source_map)))))
out=report(ctx,state,'partial',original['error_code']);refs=out['evidence_refs'];adopted=state['rag_results']['external']['evidence_ids']
assert set(refs)==set(adopted) and len(refs)==6 and not out['report']['rows']
assert all(x['legal_assessment']=='UNVERIFIED' for x in out['unreviewed_sources']) and len(out['comparison_items']['items'])==3
assert sha(p)==fixture['journal_sha256']
result={'status':'PASS','fixture':'known ADR0827; technical read-only replay, not new model execution','original_final_citations':len(original['evidence_refs']),'rendered_citations':len(refs),'evidence_ids':refs,'all_exact_original_spans':True,'journal_unchanged':True,'model_calls':0,'legal_rows':0,'field_rows':3,'quality_certified':False}
(A/'artifacts/replay-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');(A/'artifacts/replay-answer.txt').write_text(out['answer']['text']+'\n');print(json.dumps(result,ensure_ascii=False))
