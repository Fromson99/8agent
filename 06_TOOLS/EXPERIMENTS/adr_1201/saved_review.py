"""One new reviewer of saved1200 answer/originals; no full007 replay or gold input."""
from common import *
import resource,sqlite3,time,traceback
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
f=read(DES/'freeze-live.json');C=ROOT/f['code_root']
for group in ('files','scripts','inputs'):
 for n,h in f[group].items():assert sha((C if group=='files' else ROOT)/n)==h,n
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
P=ART/'saved-cm007-review';P.mkdir(parents=True,exist_ok=False)
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT)]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
from semantic_runtime.legal_agent import final_original_review as reviewer
from semantic_runtime.contracts import digest
from lawrag.research.experiment_client import ExperimentClient
from resource_guard import Guard
guard=Guard(P);guard.start();began=time.monotonic()
old=ROOT/'04_EXPERIMENTS/ADR/ADR-1200-supervisor-recovery-live-cm007/artifacts/live/cm-007'
b=read(old/'response.json')['body'];refs=b['assembly']['term_agent']['case']['judgment_refs']
with sqlite3.connect((ROOT/read(old/'result.json')['journals'][0]).as_uri()+'?mode=ro',uri=True) as db:
 def stage(name):
  ref=refs[name];raw,h=db.execute('SELECT payload_json,payload_hash FROM entity_version WHERE kind=? AND entity_id=? AND version=?',(ref['kind'],ref['entity_id'],ref['version'])).fetchone();v=json.loads(raw);assert digest(v)==h==ref['payload_hash'];return v
 assess=stage('ASSESS');draft=stage('COMPOSE');selected=stage('SELECT');sources=[s for s in selected['selected_originals'] if s['source_id'] in selected['final_ids']]
question=read(old/'request.json')['json']['question'];scope=set(read(DES/'corpus.json')['document_ids'])
with sqlite3.connect((ROOT/read(DES/'baseline.json')['release']['data_path']/'store.sqlite').as_uri()+'?mode=ro',uri=True) as db:
 for s in sources:
  assert s['document_id'] in scope
  for p in s['adopted_spans']:
   raw=db.execute('SELECT text FROM source_block WHERE document_id=? AND block_id=?',(s['document_id'],str(p['block_id']))).fetchone()[0];assert raw[p['start_cp']:p['end_cp']]==p['text']
data=reviewer.input_data(question,assess,draft,sources)
put(P/'input-reference.json',write_raw_json(P/'input.json.gz',data));put(P/'schema.json',reviewer.schema(data))
assert sha(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')==sha(C/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')
client=ExperimentClient(ROOT,P/'raw',max_calls=2,max_repairs=0,provider_policy=C/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')
def save(path,value):
 if client._key in json.dumps(value,ensure_ascii=False):raise RuntimeError('Secret cannot be recorded')
 if path.name in ('request.json','response.json','output.json'):
  write_summary(path,{'raw_json':write_raw_json(path.with_suffix('.json.gz'),value)})
 else:write_summary(path,value)
client._write=save
put(P/'dispatch.json',{'case_id':'cm-007','kind':'new_reviewer_of_saved_answer','max_physical_calls':2,'gold_in_input':False,'parent_answer_sha256':sha(old/'answer.txt'),'new_full_case_run':False,'input_hash':digest(data)})
result={'case_id':'cm-007','kind':'new_reviewer_of_saved1200','new_full_case_run':False,'gold_in_input':False}
try:
 value=client.generate(reviewer.PROMPT,data,reviewer.schema(data),phase=reviewer.PHASE)
 status=reviewer.validate(value,data);receipt=reviewer.receipt(data,status,value);reviewer.verify(receipt,data);put(P/'review.json',receipt);result.update(status=status,valid=True)
except Exception as exc:
 result.update(status='INCOMPLETE',valid=False,error_type=type(exc).__name__,error=str(exc));(P/'error.txt').write_text(traceback.format_exc())
finally:
 guard.done.set();guard.thread.join(timeout=3)
 result.update(physical_calls=client.calls,usage=client.usage,provider_switches=client.provider_switches,seconds=time.monotonic()-began,main117_unchanged=sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256'])
 put(P/'result.json',result);print(json.dumps(result,ensure_ascii=False),flush=True)
