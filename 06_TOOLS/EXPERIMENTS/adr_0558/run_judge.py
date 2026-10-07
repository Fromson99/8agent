"""First offline grading: frozen rubric/inputs, API timeout compatibility, two workers."""
import hashlib,importlib.util,json,random,sqlite3,sys
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0558-model-presentation-repair'
def read(p):return json.loads(p.read_text())
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 sys.path.insert(0,str(R/'02_BACKEND'))
 from lawrag.research.experiment_client import ExperimentClient,_schema_for_api
 import jsonschema
 design=read(A/'artifacts/frozen-design.json');judgefile=Path(__file__).with_name('judge.py')
 assert hashlib.sha256(judgefile.read_bytes()).hexdigest()==design['file_hashes'][str(judgefile.relative_to(R))]
 for p,wanted in design['grader_only_hashes'].items():assert hashlib.sha256((R/p).read_bytes()).hexdigest()==wanted
 spec=importlib.util.spec_from_file_location('frozen_judge',judgefile);judge=importlib.util.module_from_spec(spec);spec.loader.exec_module(judge)
 out=A/'artifacts/judge-001';out.mkdir(exist_ok=False)
 write(A/'artifacts/judge-api-compatibility.json',{'reason':'Frozen judge specifies timeout_seconds, public generate has no such parameter. Adapter sends identical frozen messages/schema/temperature/output reservation through audited chat_completions, preserving 120-second limit. Two workers schedule independent evaluations; no rubric, product code, input, repeats or criterion changed.','shim_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'frozen_judge_sha256':hashlib.sha256(judgefile.read_bytes()).hexdigest(),'first_judge_call_not_yet_made':True})
 cases=read(A/'product-cases.json')['cases'];gold={c['case_id']:c for c in read(A/'gold-cases.json')['cases']}
 db=sqlite3.connect('file:'+str(R/design['generation']/'navigation/navigation.sqlite')+'?mode=ro',uri=True)
 jobs=[(c,a) for c in cases for a in ['baseline','presentation','selected-only']];random.Random(558).shuffle(jobs);payloads=[]
 for number,(case,arm) in enumerate(jobs,1):
  result=read(A/'artifacts/run-001'/case['case_id']/arm/'result.json')
  g=gold.get(case['case_id'],{'reference_answer':'안녕: 적절한 인사. 제목 검색: 제목에 내부회계가 들어가는 문서 목록을 제공하고 다른 일반 법률 답변을 만들지 않음.','decisive_source_ids':[]})
  sources=[json.loads(db.execute('select json from source where id=?',(sid,)).fetchone()[0]) for sid in g.get('decisive_source_ids',[])]
  assert all(s['document_id'] in read(A/'product-cases.json')['public_scope_document_ids'] for s in sources)
  payloads.append((number,case['case_id'],arm,{'question':case['question'],'reference_requirement':g,'public_originals':sources,'answer':result.get('result',{}).get('answer',{}),'execution_failure':bool(result.get('error'))}))
 db.close()
 def one(job):
  number,cid,arm,payload=job;client=ExperimentClient(R,out/('blind-'+str(number))/'calls',max_calls=1,max_repairs=0,max_output_tokens=1800)
  body={'model':client.model,'messages':[{'role':'system','content':judge.SYSTEM},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}],'temperature':client.proxy['temperature'],'max_tokens':client.max_output_tokens,'response_format':{'type':'json_schema','json_schema':{'name':'output','strict':True,'schema':_schema_for_api(judge.SCHEMA)}}}
  try:
   response=client.chat_completions(body,phase='offline-'+str(number),timeout_seconds=120)
   verdict=json.loads(response['body_json']['choices'][0]['message']['content']);jsonschema.validate(verdict,judge.SCHEMA)
  except Exception as exc:verdict={'judge_error':type(exc).__name__,'message':str(exc)}
  return {'case_id':cid,'arm':arm,'blind_id':number,'verdict':verdict,'usage':client.usage,'physical_calls':client.calls}
 rows=[]
 with ThreadPoolExecutor(max_workers=2) as pool:
  for future in as_completed([pool.submit(one,job) for job in payloads]):
   row=future.result();rows.append(row);write(out/'results.partial.json',rows);print(row['case_id'],row['arm'],row['verdict'],flush=True)
 rows.sort(key=lambda r:r['blind_id']);write(out/'results.json',{'rows':rows,'usage':[u for row in rows for u in row['usage']],'physical_calls':sum(row['physical_calls'] for row in rows),'same_model_evaluator':True,'in_sample':True})
if __name__=='__main__':main()
