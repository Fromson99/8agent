"""Count real sqlite evidence reads in baseline/candidate structured preparation."""
import ast,hashlib,json,sqlite3,sys
from pathlib import Path
from types import SimpleNamespace as S
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1085-compact-agent-input-sql';freeze=json.loads((ADR/'artifacts/design/freeze.json').read_text());code=ROOT/freeze['code_root']
sys.path.insert(0,str(code/'02_BACKEND'))
import semantic_runtime.legal_agent.bounded_source_session as mod
baseline=code.parents[2]/'rev-001/snapshot'
# The exact original method, compiled under the same imports. Stop at save_view
# before model/journal mutation; evidence() executes actual sqlite SELECTs.
source=(baseline/'02_BACKEND/semantic_runtime/legal_agent/bounded_source_session.py').read_text()
klass=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='BoundedSourceSession')
method=next(n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name=='structured')
scope=dict(vars(mod));exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),str(baseline),'exec'),scope)
class Stop(Exception):pass
records=[]
for n in (1,8,80):
 outputs=[]
 for label,call in [('baseline',scope['structured']),('compact',mod.BoundedSourceSession.structured)]:
  db=sqlite3.connect(':memory:');db.execute('CREATE TABLE evidence(id TEXT PRIMARY KEY,payload TEXT)')
  rows=[{'evidence_id':f'E{i}','source_id':f's{i}','text':f'원문 {i}','spans':[{'text':f'원문 {i}'}]} for i in range(n)]
  db.executemany('INSERT INTO evidence VALUES(?,?)',[(r['evidence_id'],json.dumps(r)) for r in rows]);sql=[];db.set_trace_callback(sql.append)
  def evidence(ident=None):
   if ident is None:return [json.loads(r[0]) for r in db.execute('SELECT payload FROM evidence')]
   return json.loads(db.execute('SELECT payload FROM evidence WHERE id=?',(ident,)).fetchone()[0])
  def save_view(*a):outputs.append(a);raise Stop()
  work=S(VERSION=6,evidence=evidence,save_view=save_view,event=lambda *a:None)
  profile={'max_output_tokens':None,'candidate_navigation':{'compact_input':True,'completion_contract':True,'completion_policy_version':'investigation-completion-v8'}}
  obj=S(profile=profile,work=work)
  try:call(obj,'system',{'sources':[{'source_id':r['source_id'],'text':r['text']} for r in rows]}, {},'source-law-navigation-1-read-choice',180)
  except Stop:pass
  else:raise AssertionError('did not reach canonical saved view')
  count=sum(s.startswith('SELECT') for s in sql);assert count==(2*n+1 if label=='baseline' else 1)
  records.append({'evidence_count':n,'arm':label,'selects':count,'plans':[r[3] for r in db.execute('EXPLAIN QUERY PLAN SELECT payload FROM evidence WHERE id=?',('E0',))]})
  db.close()
 assert outputs[0]==outputs[1],'full saved evidence/input changed'
# No source/index query implementation changes: preserve MAIN105 query shapes.
unchanged=[]
for name in ['unit_relations.py','law_navigation.py','source_tools.py','evidence_inventory.py','structure_query.py']:
 rel=Path('02_BACKEND/semantic_runtime/legal_agent')/name
 assert (code/rel).read_bytes()==(baseline/rel).read_bytes(),name
 unchanged.append(str(rel))
result={'status':'PASS','measurements':records,'canonical_views_equal':True,'corpus_sql_modules_unchanged':unchanged,'scope':'request-journal lookup count; no claim of Oracle/GENOS latency'}
(ADR/'artifacts/run-001/sql-contract.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
