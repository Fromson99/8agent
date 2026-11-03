"""Post-run numeric UI/saved-publication inspection; no new semantic grading or calls."""
from common import *
import importlib.util,os,sqlite3,base64
F=read(DES/'freeze.json');C=ROOT/F['code_root'];P=ART/'live/review-whatif'
sys.path.insert(0,str(C/'02_BACKEND'))
os.environ['GENOS_RAG_ONTOLOGY_CONFIG']=str(DES/'ontology-config.json')
from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
from semantic_runtime.legal_agent.unified_publication import validate_saved
spec=importlib.util.spec_from_file_location('adr1297_numeric_workflow',C/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
rows=[]
initial=read(P/'initial-response.json.gz')['body']
for label in ('initial','low','high','rule','baseline-after'):
 body=read(P/(label+'-response.json.gz'))['body']
 jp=next((P/'runtime').glob('legal-agent/runs/*/'+body['run_id']+'/journal.sqlite'))
 repo=UnifiedRepository(jp)
 try:validate_saved(repo,body)
 finally:repo.close()
 ui=w._review_explanation_text(body);(P/(label+'-ui.txt')).write_text(ui)
 meta=body['assembly']['term_agent'];comp=meta.get('scenario_comparison')
 rows.append({'label':label,'saved_validated':True,'ui_rendered':bool(ui),
  'numeric_heading_rendered':comp is not None and '**가정 비교 — 실제 사건·승인 규칙 유지 / 최종 결론 미확정**' in ui,
  'numeric_nodes':[{'node':r['node_id'],'before':r['before']['status'],'after':r['after']['status']} for r in (comp or {}).get('comparisons',[])],
  'baseline_answer_preserved':body['answer']==initial['answer'],
  'ontology_status':meta['review_explanation']['ontology']['status'],
  'ontology_adoption':meta['review_explanation']['ontology']['adoption']})
unique=set();occurrences=0
for jp in (P/'runtime').rglob('journal.sqlite'):
 db=sqlite3.connect(jp)
 for r in db.execute('SELECT u.document_id,s.block_id,s.start_cp,s.end_cp,s.text FROM evidence_unit u JOIN evidence_span s ON s.evidence_id=u.evidence_id'):
  occurrences+=1;unique.add(tuple(r[:4])+(hashlib.sha256(r[4].encode()).hexdigest(),))
 db.close()
partial=read(P/'raw/call-006/partial-response.json.gz');raw=base64.b64decode(partial['body_base64'])
put(ART/'supplemental-audit.json',{'model_calls':0,'fresh_process':True,'rows':rows,
 'stored_acquired_span_occurrences':occurrences,'unique_acquired_spans':len(unique),
 'timeout_partial_bytes':len(raw),'timeout_partial_whitespace_only':not raw.strip(),
 'timeout_partial_sha256':hashlib.sha256(raw).hexdigest(),
 'current_semantic_display_observed':False,'exact_gap_id_repair_exercised':False,
 'limits':'Numeric WHAT_IF deliberately retains the actual baseline answer and separately renders a hypothetical comparison. This does not test SCENARIO_REVIEW current/history fixes, which timed out before an answer. Source span occurrences include saved copied journals; unique count is separate.'})
print(json.dumps({'saved_and_ui_rows':len(rows),'numeric_ui_rows':sum(r['numeric_heading_rendered'] for r in rows),'unique_acquired_spans':len(unique),'timeout_partial_bytes':len(raw)},ensure_ascii=False))
