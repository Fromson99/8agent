import ast,json,sqlite3
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as S
import pytest
from semantic_runtime.legal_agent import repository as repo,bounded_source_session as session
from semantic_runtime.legal_agent.errors import ContractError,ProposalError
ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1085/compact-r1/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent'
def original(module,klass,method):
 tree=ast.parse((BASE/Path(module.__file__).name).read_text());node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==klass);func=next(n for n in node.body if isinstance(n,ast.FunctionDef) and n.name==method);scope=dict(vars(module));exec(compile(ast.fix_missing_locations(ast.Module(body=[func],type_ignores=[])),str(BASE),'exec'),scope);return scope[method]
old_evidence=original(repo,'WorkRepository','evidence');old_structured=original(session,'BoundedSourceSession','structured')
def setup(n):
 db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
 db.executescript('CREATE TABLE evidence_unit(evidence_id TEXT PRIMARY KEY,source_id,document_id,text_hash,metadata_json);CREATE TABLE evidence_span(evidence_id TEXT,ordinal INTEGER,block_id,start_cp,end_cp,text,block_hash,span_hash,PRIMARY KEY(evidence_id,ordinal));')
 for i in range(n):
  parts=[f'원문 {i} 첫째\n',f'  둘째 {i}'];text='\n'.join(parts);eid=f'E{i:03d}'
  db.execute('INSERT INTO evidence_unit VALUES(?,?,?,?,?)',(eid,f's{i}','d',repo.text_hash(text),'{"version":"1"}'))
  for k in (1,0):db.execute('INSERT INTO evidence_span VALUES(?,?,?,?,?,?,?,?)',(eid,k,f'b{k}',0,len(parts[k]),parts[k],'block',repo.text_hash(parts[k])))
 return db
@pytest.mark.parametrize('n',[0,1,8,80])
def test_actual_sql_counts_and_rows(n):
 db=setup(n);obj=S(db=db);queries=[];db.set_trace_callback(queries.append)
 before=old_evidence(obj);old_count=len(queries);queries.clear()
 after=repo.WorkRepository.evidence(obj);new_count=len(queries)
 assert after==before and old_count==n+1 and new_count==(2 if n else 1)
 if n:
  queries.clear();assert repo.WorkRepository.evidence(obj,'E000')==before[0] and len(queries)==2
  plan=[r[3] for r in db.execute('EXPLAIN QUERY PLAN SELECT * FROM evidence_span WHERE evidence_id=? ORDER BY evidence_id,ordinal',('E000',))]
  assert all('TEMP B-TREE' not in s for s in plan) and any('SEARCH' in s for s in plan)
 with pytest.raises(ProposalError):repo.WorkRepository.evidence(obj,'missing')
 db.close()
@pytest.mark.parametrize('kind',['text','order'])
def test_corrupt_span_cannot_become_verified_batch(kind):
 db=setup(2);db.execute('UPDATE evidence_span SET text=? WHERE evidence_id=? AND ordinal=0',('corrupt','E001'))
 with pytest.raises(ContractError):repo.WorkRepository.evidence(S(db=db))
 db.close()
@pytest.mark.parametrize('n',[1,8,80])
def test_whole_input_preparation_actual_sql_and_canonical_evidence(n):
 class Stop(Exception):pass
 values=[];counts=[]
 for fn,ev in [(old_structured,old_evidence),(session.BoundedSourceSession.structured,repo.WorkRepository.evidence)]:
  db=setup(n);queries=[];db.set_trace_callback(queries.append);obj=S(db=db)
  def evidence(ident=None):return ev(obj,ident)
  def save(*args):values.append(args);raise Stop()
  work=S(VERSION=6,evidence=evidence,save_view=save,event=lambda *a:None)
  profile={'max_output_tokens':None,'candidate_navigation':{'minimal_input':False,'compact_input':True,'completion_contract':True,'completion_policy_version':'investigation-completion-v8'}}
  data={'sources':[{'source_id':f's{i}','text':f'원문 {i} 첫째\n\n  둘째 {i}'} for i in range(n)]}
  with pytest.raises(Stop):fn(S(profile=profile,work=work),'system',data,{},'source-law-navigation-1-read-choice',180)
  counts.append(len(queries));db.close()
 assert values[0]==values[1] and counts==[5*n+1,2]
 print('ACTUAL_SQL',n,counts)
