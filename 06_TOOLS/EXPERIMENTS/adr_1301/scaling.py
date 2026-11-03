from common import *
from copy import deepcopy
from types import SimpleNamespace
import time
F=read(DES/'freeze.json');C=ROOT/F['code_root'];sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent import completion_v8 as v8, completion_execution as ce, read_judgment_final as final, requirement_coverage as requirements, ontology_assessment as ontology, assessment_links as links, source_work_review as work, assessment_input as ai
from semantic_runtime.legal_agent.gateway import ModelGateway
from semantic_runtime.legal_agent.minimal_output import prepare_request
from semantic_runtime.legal_agent.local_gemma import provider_request
from semantic_runtime.legal_agent.navigation_input import expand_cards
PRIOR=ROOT/'04_EXPERIMENTS/ADR/ADR-1299-main134-schema-scaling-diagnosis/artifacts/run-001'
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1297-main134-display-observer-live/artifacts/live/review-whatif'
profile=read(P/'binding.json')['profile'];out=ART/'scaling';out.mkdir(exist_ok=False)
assert all(sha(C/n)==h for n,h in F['files'].items())
def size(v):return len(json.dumps(v,ensure_ascii=False,separators=(',',':')).encode())
def schema(v):
 s=v8.assessment_schema(v['issues'],[r['material_id'] for r in v['saved_inventory']],v['evidence_options'],v['user_fact_sources'],[])
 s=ce.bounded_judgment_notes(s);s=final.attach(s,v['read_judgments'],v['evidence_options']);s=requirements.attach(s,v['requirement_context'],v['evidence_options'])
 s=ontology.usage_schema(s,{'ontology_bundles':v['ontology_bundles']});s=links.attach(s,v['evidence_options'])
 s,_=ce.assessment_projection(s,allowed_targets=['',*(r['target'] for r in v['locator_options'])]);s,_=work.projection(s,v['read_judgments'],v['evidence_options']);s,_=links.projection(s)
 return s
rows=[]
for file in sorted(PRIOR.glob('*-summary.json')):
 old=read(file);raw=read(PRIOR/(old['id']+'.json.gz'));v=raw['component_fixture'];start=time.perf_counter();s=schema(v)
 g=object.__new__(ModelGateway);g.profile=profile;g.compact=True;g.domain={};g.system='';g.prompts={'compose':''}
 g.transport=SimpleNamespace(binding=profile['model_binding']);g.protocol=SimpleNamespace(schema=lambda name:deepcopy(s))
 r=g.request('compose',v,'BoundedSourceDecision');r,_=prepare_request(r,g._generation_schema);r=provider_request(r)
 user=r['messages'][1]['content'];uv=json.loads(user)['view'];before=json.loads(raw['provider_request']['messages'][1]['content'])['view']
 assert ai.META in uv and ai.restore(uv)==before,'entire previous wire exactly restored'
 assert expand_cards(ai.restore(uv))==expand_cards(before)
 count=len(work.eligible(v['read_judgments'],v['evidence_options']))
 counts=deepcopy(old['required_review_rows']);counts['needs']-=count
 row={'id':old['id'],'source_count':old['source_count'],'mode':old['mode'],'extra_text_chars':old['extra_text_chars'],
 'before_schema_bytes':old['schema_bytes'],'after_schema_bytes':size(r['response_format']['json_schema']['schema']),
 'before_user_bytes':old['user_bytes'],'after_user_bytes':len(user.encode()),
 'before_rows':old['required_review_rows_total'],'after_rows':sum(counts.values()),'after_row_counts':counts,'host_source_work_rows':count,
 'question_occurrences_before':raw['provider_request']['messages'][1]['content'].count(v['current_request']),
 'question_occurrences_after':user.count(v['current_request']),
 'first_original_before':raw['provider_request']['messages'][1]['content'].count(v['evidence_options'][0]['text']),
 'first_original_after':user.count(v['evidence_options'][0]['text']),
 'full_input_roundtrip_equal':True,'seconds':time.perf_counter()-start}
 row['raw']=write_raw_json(out/(old['id']+'.json.gz'),{'canonical_fixture_sha256':sha(PRIOR/(old['id']+'.json.gz')),'generation_schema':s,'provider_user':user,'provider_schema':r['response_format']['json_schema']['schema']})
 rows.append(row);print(old['id'],row['before_user_bytes'],row['after_user_bytes'],row['before_rows'],row['after_rows'],flush=True)
put(out/'result.json',{'status':'PASS','rows':rows,'model_calls':0,'oracle_calls':0,'code_unchanged':all(sha(C/n)==h for n,h in F['files'].items()),'limits':'Exact same twelve stored canonical fixtures; model-facing user/schema only. System prompt has new instructions and is not compared here. Not model quality, throughput or Oracle measurement.'})
