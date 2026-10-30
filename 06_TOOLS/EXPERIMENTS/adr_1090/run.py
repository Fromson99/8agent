from common import *
import sys,sqlite3,gzip,time
from copy import deepcopy
from types import SimpleNamespace
sys.dont_write_bytecode=True
f=read(DES/'freeze.json');code=ROOT/f['code_root']
assert all(sha(code/n)==h for n,h in f['files'].items())
assert all(sha(ROOT/n)==h for n,h in f['tests'].items())
sys.path.insert(0,str(code/'02_BACKEND'))
from semantic_runtime.legal_agent import read_candidate_pages as pages,compact_model_input as compact
from semantic_runtime.legal_agent.navigation_input import expand_cards
from semantic_runtime.legal_agent.repository import WorkRepository,text_hash
from semantic_runtime.legal_agent.errors import ContractError,ProposalError
matrix=read(DES/'matrix.json');start=time.monotonic();out=ART/'run-001';out.mkdir(parents=True,exist_ok=True)
results=[]
def require(ok,label):
 if not ok:raise AssertionError(label)
for size,n in matrix['pages']:
 originals=[{'id':f'E{i}','document_name':f'모의 문서 {i}','document_id':f'd{i}','text':f'  제{i}조\n본문 공백·한글·🙂 {i}  '} for i in range(3)]
 judgments={'current_originals':[{'id':f'J{i}','source_refs':[f'E{i}'],'material':[f'M{i}']} for i in range(3)],'judgments':[{'id':f'J{i}','finding':f'판단 {i}','reason':f'이유 {i}','missing':[f'미확인 {i}']} for i in range(3)],'required':['J0','J1','J2']}
 data={'source_stage':'source-law-navigation-1-read-choice','request':'모의 원문 확인','sources':originals,'read_judgments':judgments,
 'read_candidates':[{'target':f'T{i}','preview':f'미리보기 {i}','document_name':f'모의 문서 {i%3}','document_id':f'd{i%3}'} for i in range(n)],
 'tool_options':[{'choice':'LOCATE','target':'L0','label':'위치 찾기','scope':{'document_id':'d0'}}]}
 read_branch={'properties':{'choice':{'const':'READ'},'selections':{'items':{'properties':{'target':{'enum':[f'T{i}' for i in range(n)]}}}}}}
 schema={'anyOf':[read_branch,{'properties':{'choice':{'const':'FINISH'}}}]}
 frozen=deepcopy((data,schema));seen=[];count=max(1,(n+size-1)//size)
 for page in range(count):
  v,w=pages.page_view(data,schema,page,size);ids=[r['target'] for r in v['read_candidates']];seen+=ids
  require(ids==[f'T{i}' for i in range(page*size,min((page+1)*size,n))],'page slice')
  require(w['anyOf'][0]['properties']['selections']['items']['properties']['target']['enum']==ids,'schema page')
  expected=([pages.NEXT] if page+1<count else [])+([pages.PREVIOUS] if page else [])
  require(v['read_candidate_page']['actions']==expected and len(ids)<=20,'move boundary')
  boundview=compact.bind(v,w);projected=compact.project(boundview);decoded=expand_cards(projected)
  require(projected==compact.project(json.loads(json.dumps(boundview,sort_keys=True))),'canonical independent projection')
  require([s['text'] for s in decoded['sources']]==[s['text'] for s in originals],'exact texts')
  require(decoded['read_judgments']==judgments,'judgment correspondence and pending needs')
  require(decoded['tool_options']['LOCATE'][0]['target']=='L0','non-read tools')
 require(seen==[f'T{i}' for i in range(n)] and (data,schema)==frozen,'partition/mutation')
 results.append({'kind':'page','size':size,'candidates':n,'pages':count,'pass':True})
for n,width,reverse in matrix['journal']:
 db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
 db.executescript('CREATE TABLE evidence_unit(evidence_id TEXT PRIMARY KEY,text_hash,metadata_json);CREATE TABLE evidence_span(evidence_id TEXT,ordinal INTEGER,text,PRIMARY KEY(evidence_id,ordinal));')
 expected=[]
 for i in reversed(range(n)) if reverse else range(n):
  eid=f'E{i:04d}';parts=[f' 원문 {i}/{j} \n한글🙂\t' for j in range(width)];body='\n'.join(parts);h=text_hash(body);meta={'source_version':str(i),'rights':'fixture'}
  db.execute('INSERT INTO evidence_unit VALUES(?,?,?)',(eid,h,json.dumps(meta)))
  spans=[{'evidence_id':eid,'ordinal':j,'text':t} for j,t in enumerate(parts)]
  for s in reversed(spans) if reverse else spans:db.execute('INSERT INTO evidence_span VALUES(?,?,?)',(eid,s['ordinal'],s['text']))
  expected.append({'evidence_id':eid,'text_hash':h,'metadata_json':json.dumps(meta),'metadata':meta,'spans':spans,'text':body})
 expected.sort(key=lambda r:r['evidence_id']);queries=[];db.set_trace_callback(queries.append);obj=SimpleNamespace(db=db)
 actual=WorkRepository.evidence(obj);q=len(queries)
 require(actual==expected and q==(2 if n else 1),'independent rows/SQL bound')
 for row in expected:
  queries.clear();require(WorkRepository.evidence(obj,row['evidence_id'])==row and len(queries)==2,'single indexed original')
 try:WorkRepository.evidence(obj,'absent');raise AssertionError('missing original accepted')
 except ProposalError:pass
 if n:
  plan=[r[3] for r in db.execute('EXPLAIN QUERY PLAN SELECT * FROM evidence_span WHERE evidence_id=? ORDER BY evidence_id,ordinal',('E0000',))]
  require(any('SEARCH' in x for x in plan) and all('TEMP B-TREE' not in x for x in plan),'point index plan')
  db.execute("UPDATE evidence_span SET text='corrupt' WHERE evidence_id='E0000' AND ordinal=0")
  try:WorkRepository.evidence(obj);raise AssertionError('corruption accepted')
  except ContractError:pass
 db.close();results.append({'kind':'journal','count':n,'width':width,'reverse':reverse,'whole_selects':q,'pass':True})
with gzip.open(out/'conditions.jsonl.gz','wt',encoding='utf-8') as stream:
 for row in results:stream.write(json.dumps(row)+'\n')
put(out/'result.json',{'strict_success':True,'checks':{'all_declared_conditions':len(results)==len(matrix['pages'])+len(matrix['journal']),'all_conditions_pass':all(r['pass'] for r in results),'exact430files':all(sha(code/n)==h for n,h in f['files'].items()),'main_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(DES/'baseline.json')['pointer_sha256']},'new_primary_page_conditions':len(matrix['pages']),'new_primary_sql_conditions':len(matrix['journal']),'wall_seconds':time.monotonic()-start,'new_model_calls':0,'quality_certified':False,'scope':'Finite engineering contracts only; no legal answer outcome certified'})
print(json.dumps(read(out/'result.json'),ensure_ascii=False))
