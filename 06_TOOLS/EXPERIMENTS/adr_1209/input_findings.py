from common import *
import gzip,collections
f=read(DES/'freeze.json');C=ROOT/f['code_root'];size=lambda v:len(json.dumps(v,ensure_ascii=False,separators=(',',':')))
a=read(ART/'input-wire-size-audit.json');rows=a['rows'];selected=max((r for r in rows if r['adr']==1206),key=lambda r:r['request_chars'])
p=ROOT/selected['source']['path'];d=json.loads(gzip.decompress(p.read_bytes()));u=json.loads(next(m['content'] for m in d['messages'] if m['role']=='user'));v=u.get('view',u);g=v['glossary_candidates']
fields=collections.Counter()
for c in g['candidates']:
 for k,value in c.items():fields[k]+=size(value)
sys.path[:0]=[str(C),str(C/'02_BACKEND')]
from semantic_runtime.legal_agent import need_continuity as nc
state={'binding':'technical-size-probe'}
base={'choice':'FINISH','issue_id':'Q1','answer_progress':{'goals':[{'issue_id':'Q1','status':'NEEDS_SOURCE','material_need':'정의 조문의 적용 범위를 추가 확인할 필요가 있다.','answer_so_far':'현재 원문의 규정과 추가 정의를 구분한다.','basis_refs':['S1'],'next_answer_change':'정의 확보 후 해당 범위가 적용되는지 판단한다.'}]}}
samples=[]
for i in range(1,5):
 nc.record(state,base,'decision-'+str(i));needs=list(state['material_needs'].values())
 samples.append({'declarations':i,'need_count':len(needs),'material_needs_json_chars':size(needs)})
put(ART/'input-size-findings.json',{'wire_requests':len(rows),'units':'Unicode chars and compact JSON chars, not tokenizer counts; provider serialization overhead is counted in total request only','domain_max':selected,'domain_glossary_candidates':len(g['candidates']),'domain_glossary_field_chars_sum':dict(fields),'domain_raw_chars':size(v['raw']),'declared_need_growth_synthetic':samples,'growth_probe_note':'Same need ID, distinct declaration slots; measures stored/projected need JSON only, not a production prompt or token cost. Full declarations are copied into selection declared_needs and final needs.','code_evidence':{n:bind(C/n) for n in ['02_BACKEND/semantic_runtime/ontology_work/profile_schema.py','02_BACKEND/semantic_runtime/ontology_work/glossary_binding.py','02_BACKEND/semantic_runtime/ontology_work/authoring_model.py','02_BACKEND/semantic_runtime/legal_agent/need_continuity.py','02_BACKEND/semantic_runtime/legal_agent/investigation_supervisor.py','02_BACKEND/semantic_runtime/legal_agent/compact_model_input.py']},'unimplemented_recommendations':['Keep strict validation, separately evaluate equivalent schema subtree factoring for authoring requests; do not automatically adopt unexecuted JSON-object transport.','Keep full glossary inspection in server receipt; present a concise concept/card projection for first normalization with ID-bound detail retrieval when needed.','Keep stable open need IDs, reason, scope/target and unconfirmed-action flag in every required model view, while retaining all declaration/decision hashes in server ledger. Evaluate an explicit input projection rather than cutting unresolved needs.','Project connection-scope/tool menus by exact ID and current state; preserve LLM multi-selection/ranges and all source bytes required for final judgment.'],'limits':['No new model request, token or latency claim','No prompt shortening applied in this MAIN release','Existing UNKNOWN/empty content failures are not proven to be caused by input size','Historical runs have different investigation states; maxima are descriptive, not causal A/B']})
print('Historical requests',len(rows),'glossary9 field sums',dict(fields),'need probe',samples)
