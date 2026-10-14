"""One audited writing call, compared to the same accepted deterministic answer."""
from pathlib import Path
import hashlib,json,sys,time,traceback
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0766-rich-grounded-answer-stream';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
f=read(D/'probe-freeze.json');S=R/f['candidate'];cid=sys.argv[1]
assert sha(D/'public-probes.json')==f['dataset_sha256'] and sha(Path(__file__))==f['runner_sha256']
for name,h in f['code'].items():assert sha(S/name)==h
sys.dont_write_bytecode=True;sys.path.insert(0,str(S/'02_BACKEND'))
from semantic_runtime.legal_agent import narrative_answer as n, completion_contracts as cc
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport,provider_request
from lawrag.research.experiment_client import ExperimentClient
from semantic_runtime.legal_agent.gateway import genos_wire_schema
case=next(c for c in read(D/'public-probes.json')['cases'] if c['case_id']==cid)
out=A/'artifacts/run-001'/cid;out.mkdir(parents=True,exist_ok=False)
def put(name,v):(out/name).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
t=LocalGemmaTransport(S,R)
assert all(s['document_id'] in t.public_scope for s in case['sources'])
data=n.input_data(case['question'],case['assessment'],case['sources'],'paragraphs')
schema=n.schema(data['answer_claim_ids'])
body={'model':t.binding['model'],'temperature':0,'max_tokens':6400,'stream':False,
    'messages':[{'role':'system','content':n.PROMPT},{'role':'user','content':json.dumps({'view':data},ensure_ascii=False)}],
    'response_format':{'type':'json_schema','json_schema':{'name':n.SCHEMA,'strict':True,'schema':genos_wire_schema(schema)}}}
client=ExperimentClient(R,out/'provider',max_calls=1,max_output_tokens=6400,max_repairs=0)
baseline=cc.compose(case['assessment'],cc.default_plan(case['assessment']))
(out/'baseline.txt').write_text(baseline['text'])
result={'case_id':cid,'status':'failed','source_binding':case['provenance'],'model':t.binding['model'],'semantic_review':'pending'}
start=time.perf_counter()
try:
    raw=client.chat_completions(provider_request(body),phase='public-compose-'+cid,timeout_seconds=180)
    value=json.loads(raw['body_json']['choices'][0]['message']['content'])
    value=n.checked(value,data['answer_claim_ids']);answer=cc.compose(case['assessment'],n.plan(case['assessment'],value))
    cc.verify_composition(case['assessment'],answer)
    assert answer['claims']==baseline['claims'] and answer['limitations']==baseline['limitations']
    put('answer.json',answer);(out/'answer.txt').write_text(answer['text'])
    result.update(status='completed',baseline_chars=len(baseline['text']),answer_chars=len(answer['text']),paragraphs=len(value['paragraphs']),source_binding_preserved=True)
except Exception as exc:
    result.update(error_type=type(exc).__name__,error=str(exc));(out/'error.txt').write_text(traceback.format_exc())
finally:
    result.update(seconds=time.perf_counter()-start,model_calls=client.calls,usage=client.usage)
    put('result.json',result)
    print(json.dumps(result,ensure_ascii=False))
