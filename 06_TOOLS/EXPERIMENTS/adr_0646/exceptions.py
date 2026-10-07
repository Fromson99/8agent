"""Actual-model probe of persisted selection expectations on public synthetic data."""
from pathlib import Path
import json,hashlib,sys,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0646-shortcut-preserve-discovery-route';D=A/'artifacts/design';OUT=A/'artifacts/run-001/procedure-exceptions'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for path,h in json.loads((D/'freeze.json').read_text())['files'].items():assert sha(R/path)==h
C=R/'02_BACKEND/lawrag/research/candidates/adr_0646/procedure'
for row in json.loads((C/'candidate.json').read_text())['revisions'][0]['files']:assert sha(R/row['frozen_path'])==row['snapshot_sha256']
sys.path.insert(0,str(C/'revisions/rev-001/snapshot/02_BACKEND'))
from semantic_runtime.legal_agent.procedure_memory import ProcedureMemory
# Host policy/audit implementation, not any product classifier.
import importlib.util
s=importlib.util.spec_from_file_location('audit',R/'02_BACKEND/lawrag/research/experiment_client.py');a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
assert not OUT.exists();OUT.mkdir(parents=True);client=a.ExperimentClient(R,OUT/'provider',max_calls=4,max_output_tokens=1200,max_repairs=0)
db=sqlite3.connect(OUT/'procedures.sqlite',isolation_level=None);db.row_factory=sqlite3.Row
inputs=json.loads((D/'exception-inputs.json').read_text());rows=[]
for i,item in enumerate(inputs):
 schema={'type':'object','properties':{'selected':{'type':'string','enum':[c['id'] for c in item['menu']]},'reason':{'type':'string'}},'required':['selected','reason'],'additionalProperties':False}
 data={'question':item['question'],'anchor':item['anchor'],'menu':item['menu'],'schema':schema}
 memory=ProcedureMemory(db,{'user_id':'synthetic','team_id':'public','document_ids':['synthetic-law']},{'generation':item['generation']},str(i),lambda *_:None)
 result,deviation=memory.lookup('source-reference-batch-1',item['question'],data);before=client.calls
 if result is None:
  result=client.generate('공개 합성 규정의 명시 준용관계를 따라 다음에 읽을 원문을 고른다. 현재 anchor가 명시하는 조문을 menu에서 고르고 이유를 적는다. 과거 결과를 그대로 복사하지 않는다. JSON만 출력한다.',{'current':data,'deviation':deviation},schema,phase='exception-'+str(i))
  memory.save('source-reference-batch-1',item['question'],data,result,decision='MODEL_ON_DISCOVERY_OR_DEVIATION');memory.activate()
 rows.append({'scenario':item['scenario'],'model_calls':client.calls-before,'deviation':deviation,'result':result})
 put(OUT/'result.json',{'rows':rows,'calls':client.calls,'usage':client.usage})
 print(item['scenario'],client.calls-before,result['selected'],flush=True)
