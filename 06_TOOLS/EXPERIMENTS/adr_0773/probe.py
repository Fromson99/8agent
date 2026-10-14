from pathlib import Path
import importlib.util,json,sys,tempfile
R=Path(__file__).resolve().parents[3];code=Path(sys.argv[1]).resolve();sys.path[:0]=[str(code/'02_BACKEND'),str(R/'05_TESTS/CONTRACTS')];sys.dont_write_bytecode=True
fixture=R/'02_BACKEND/lawrag/research/candidates/adr_0773/successful-publication-r2/snapshot/05_TESTS/CONTRACTS/test_successful_core_routes.py'
spec=importlib.util.spec_from_file_location('probe_fixture',fixture);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
try:from semantic_runtime.legal_agent import successful_answer as success
except ImportError:success=None;m.publish=lambda *a,**kw:None
from semantic_runtime.ad_store import Store,SCHEMA
from semantic_runtime.ad_backend import Backend
from semantic_runtime.legal_agent.corrected_memory import MemoryError
states=['success','recovered_success','failed','interrupted','pending_export','empty','clarification','tampered_receipt','stale_revision','retired_route','foreign_team','rejected'];out=[]
for state in states:
 with tempfile.TemporaryDirectory() as tmp:
  fixture=m.routes.__wrapped__(Path(tmp));r=next(fixture);repo=r.cases.shortcut;db=repo.db;p=dict(r.p)
  m.core.finalize(r.cases,r.result,r.p)
  for row in db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='sw_event'").fetchall():db.execute('DROP TRIGGER "'+row[0]+'"')
  if state in ('failed','interrupted','pending_export','empty','clarification'):db.execute("DELETE FROM sw_event WHERE kind='ANSWER_PUBLISHED'")
  if state in ('failed','interrupted'):db.execute('UPDATE sw_intake SET status=?',(state.upper(),))
  if state=='recovered_success' and success:success.fail(r.cases,r.p);m.publish(r.cases,r.result,r.p)
  if state=='tampered_receipt':db.execute("UPDATE sw_event SET hash='broken' WHERE kind='ANSWER_PUBLISHED'")
  if state=='stale_revision':db.execute('UPDATE goal SET revision=revision+1')
  if state=='retired_route':db.execute("UPDATE route SET status='RETIRED'")
  if state=='foreign_team':p['team_id']='other'
  if state=='rejected':
   db.executescript(SCHEMA);db.execute("INSERT INTO ad_object(kind,entity,workspace,review,trashed,revision,changed_at) VALUES('shortcut',?,'t','REJECTED',0,1,0)",(r.cases.active_case,))
  store=Store(repo.path)
  values={'ad_shortcut':bool(Backend(store,p['team_id']).list('shortcut')),'native_wiki':bool(repo.search(p)['pages'])};store.close()
  try:repo.compiler_input(r.cases.active_case,p);values['compiler']=True
  except MemoryError:values['compiler']=False
  for surface,admitted in values.items():out.append({'state':state,'surface':surface,'admitted':admitted,'expected':state in ('success','recovered_success')})
  fixture.close()
Path(sys.argv[2]).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
