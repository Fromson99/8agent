from common import *
candidate=read(DES/'candidate-repaired.json');C=ROOT/candidate['code_root']
sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent import investigation_supervisor as supervisor
P=next((ROOT/'04_EXPERIMENTS/ADR').glob('ADR-1383-*/artifacts/usage-live'))
rows=[]
for tag in ('charter-explicit-ontology-on','charter-on-ontology-on'):
 d=P/tag;calls=read(d/'calls.json')
 for call in calls:
  if call['stage'] not in ('memory-assess','memory-assess-repair'):continue
  number=call['number'];v=read(d/'canonical'/f'{number:03}.json.gz')['view'];p=read(d/'canonical'/f'{number:03}-output.json.gz')
  raw=read(d/'raw'/f'call-{number:03}'/'request.json.gz')
  body=supervisor.ontology_review_input(v['current_request'],v,p,v['evidence_options'],v.get('user_fact_sources',[]))
  schema=supervisor.ontology_review_schema([c['claim_id'] for c in p['claims']])
  encoded=lambda x:len(json.dumps(x,ensure_ascii=False,separators=(',',':')))
  input_characters=len(supervisor.ONTOLOGY_REVIEW_PROMPT)+encoded(body)+encoded(schema)
  full=sum(len(m['content']) for m in raw['messages'])+encoded(raw['response_format']['json_schema']['schema'])
  row={'case':tag,'source_call':number,'old_input_characters_including_schema':full,'projected_review_characters_including_schema':input_characters,
   'projected_review_schema_characters':encoded(schema),'old_assessment_schema_characters':encoded(raw['response_format']['json_schema']['schema']),
   'source_prompt_tokens':call['usage']['prompt_tokens'],'source_output_tokens':call['usage']['completion_tokens'],'pass_output_characters':encoded({'decision':'PASS'}),
   'no_physical_model_calls':True,'latency_estimated':False,'scope':'Application-level projected input before common gateway/domain augmentation, not an actual new provider payload or tokenizer measurement'}
  rows.append(row)
put(ART/'review-size.json',{'rows':rows,'source_literal_unchanged':True})
for r in rows:print(r['case'],r['source_call'],r['old_input_characters_including_schema'],r['projected_review_characters_including_schema'],r['old_assessment_schema_characters'],r['projected_review_schema_characters'])
