"""Author proposed design schemas and synthetic examples; no production changes."""
from pathlib import Path
import json
OUT=Path(__file__).resolve().parent
STR={'type':'string','minLength':1}
HASH={'type':'string','pattern':'^[a-f0-9]{64}$'}
NULLSTR={'type':['string','null']}
def arr(item,minimum=0): return {'type':'array','items':item,'minItems':minimum,'uniqueItems':True}
def ref(name):return {'$ref':'#/$defs/'+name}
def obj(props,required=None):return {'type':'object','properties':props,'required':list(props) if required is None else required,'additionalProperties':False}
def enum(*values): return {'enum':list(values)}
D={}
D['Binding']=obj({'controller_sha256':HASH,'domain_id':STR,'domain_sha256':HASH,'profile_id':STR,'profile_sha256':HASH,'generation_id':STR,'source_store_sha256':HASH,'navigation_sha256':HASH,'fulltext_sha256':HASH,'reference_overlay_sha256':HASH,'auth_scope_sha256':HASH,'provider':STR,'model':STR})
D['EvidenceSpan']=obj({'span_id':STR,'source_id':STR,'generation_id':STR,'source_store_sha256':HASH,'document_id':STR,'source_artifact_sha256':HASH,'unit_id':NULLSTR,'block_id':STR,'start':{'type':'integer','minimum':0},'end':{'type':'integer','minimum':1},'text_sha256':HASH,'role':enum('normative','interpretive','reference'),'temporal_status':enum('verified','unknown'),'valid_from':{'type':['string','null'],'format':'date'},'valid_to':{'type':['string','null'],'format':'date'}})
D['EvidenceRef']=obj({'handle':{'type':'string','pattern':'^E[1-9][0-9]*$'},'span_ids':arr(STR,1),'presented_call_ids':arr(STR,1)})
D['SearchAttempt']=obj({'id':STR,'issue_id':STR,'method':enum('fts','locator','reference','reverse_reference','definition','outline'),'query_sha256':HASH,'scope_sha256':HASH,'result_sha256':HASH,'status':enum('SUCCESS','EMPTY','ERROR','BLOCKED'),'reason':{'type':'string'}})
D['Issue']=obj({'issue_id':STR,'kind':STR,'question_segment_ids':arr(STR,1),'required':{'type':'boolean'},'origin':enum('question','domain_rule','source_signal'),'evidence_state':enum('OPEN','EVIDENCE_LINKED','SEARCHED_UNRESOLVED','CONFLICTED','NOT_APPLICABLE'),'fact_state':enum('not_needed','stated','unknown'),'evidence_refs':arr(STR),'search_attempt_ids':arr(STR),'reason':{'type':'string'}})
D['Issue']['allOf']=[
 {'if':{'properties':{'evidence_state':{'const':'EVIDENCE_LINKED'}}},'then':{'properties':{'evidence_refs':{'minItems':1},'reason':{'minLength':1}}}},
 {'if':{'properties':{'evidence_state':{'const':'SEARCHED_UNRESOLVED'}}},'then':{'properties':{'search_attempt_ids':{'minItems':1},'reason':{'minLength':1}}}},
 {'if':{'properties':{'evidence_state':enum('CONFLICTED','NOT_APPLICABLE')}},'then':{'properties':{'reason':{'minLength':1}}}}
]
D['Budget']=obj({'max_attempts':{'type':'integer','minimum':1},'used_attempts':{'type':'integer','minimum':0},'reserved_composition_attempts':{'type':'integer','minimum':1},'max_nav_rounds':{'type':'integer','minimum':1},'max_input_tokens':{'type':'integer','minimum':1},'max_output_tokens':{'type':'integer','minimum':1},'deadline_utc':{'type':'string','format':'date-time'}})
D['State']=obj({'schema_version':{'const':'legal-agent-state-proposal-v1'},'run_id':STR,'binding':ref('Binding'),'status':enum('BOUND','EXPLORING','READY','BOUNDED','CLARIFY','COMPOSING','VERIFYING','FINAL','FAILED'),'response_class':enum('unresolved','complete','partial','clarify','failed'),'issues':arr(ref('Issue')),'spans':arr(ref('EvidenceSpan')),'evidence':arr(ref('EvidenceRef')),'searches':arr(ref('SearchAttempt')),'selected_source_ids':arr(STR),'budget':ref('Budget')})
schema={'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'urn:8-agent:legal-agent-state-proposal-v1','$comment':'Design-only schema; not installed in PIPELINE. Cross-reference, hash, temporal and transition checks need server code.','$ref':'#/$defs/State','$defs':D}
H='a'*64
binding={k:('g:synthetic' if k=='generation_id' else H if k.endswith('sha256') else 'synthetic-'+k) for k in D['Binding']['properties']}
span={'span_id':'span:1','source_id':'article:synthetic','generation_id':'g:synthetic','source_store_sha256':H,'document_id':'doc:synthetic','source_artifact_sha256':H,'unit_id':'unit:2','block_id':'2','start':0,'end':12,'text_sha256':H,'role':'normative','temporal_status':'unknown','valid_from':None,'valid_to':None}
state={'schema_version':'legal-agent-state-proposal-v1','run_id':'run:synthetic','binding':binding,'status':'BOUNDED','response_class':'partial','issues':[{'issue_id':'I1','kind':'requirement','question_segment_ids':['Q1'],'required':True,'origin':'question','evidence_state':'EVIDENCE_LINKED','fact_state':'unknown','evidence_refs':['E1'],'search_attempt_ids':[],'reason':'합성 규범을 확인했지만 사용자 사실은 미상이다.'}],'spans':[span],'evidence':[{'handle':'E1','span_ids':['span:1'],'presented_call_ids':['call:1']}],'searches':[],'selected_source_ids':['article:synthetic'],'budget':{'max_attempts':8,'used_attempts':2,'reserved_composition_attempts':2,'max_nav_rounds':4,'max_input_tokens':16000,'max_output_tokens':4096,'deadline_utc':'2026-09-19T12:00:00Z'}}
ctx={'id':'article:synthetic','document_id':'doc:synthetic','document_name':'합성 모의규정','block_id':'2','unit_id':'unit:2','text':'합성 규범의 예시입니다.','source_artifact_sha256':H,'blocks':[{'block_id':'2','unit_id':'unit:2','text':'합성 규범의 예시입니다.'}],'ancestors':[{'id':'unit:2','title':'제2조(합성)','family':'kr_article'}],'span_ids':['span:1']}
query={'id':'query:synthetic','question':'합성 질문','generation_id':'g:synthetic','scope':{'document_version_ids':['doc:synthetic']}}
state_for_port={'implementation':'legal-agent-v1','selected_ids':['article:synthetic'],'legal_agent':state}
answer={'schema_version':'term-runtime-v1','id':'answer:synthetic','scope':query['scope'],'query_id':query['id'],'generation_id':'g:synthetic','source_store_sha256':H,'text':'저장된 모의규정의 요건을 확인했습니다. 사용자 사실이 없어 적용 여부는 미확인입니다.','claims':[{'id':'claim:1','text':'저장된 모의규정의 요건을 확인했습니다.','source_ids':['article:synthetic']}],'unresolved':[{'reason':'사용자 사실과 해당 판본의 효력 시점을 확인해야 합니다.'}],'provider_receipt':{'id':'receipt:synthetic','sha256':H,'entailment_status':'not_certified'}}
result={'request':{'question':'합성 질문','document_ids':['doc:synthetic'],'use_llm':True},'query':query,'retrieval':{'candidates':[ctx],'routes':{'legal_agent':1},'vector_status':'NOT_USED','generation_id':'g:synthetic','term_agent':state_for_port},'selection':{'selected':[ctx],'discarded_ids':[],'method':'term-agent','term_agent':state_for_port},'assembly':{'context':[ctx],'unresolved':['사실 미상'],'data_status':'DRAFT','term_agent':state_for_port},'answer':answer}
examples={'notice':'All identities, texts, hashes and budgets are synthetic shape examples, not source or policy attestations.','state':state,'runtime_result':result}
(OUT/'contracts.schema.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2)+'\n')
(OUT/'examples.json').write_text(json.dumps(examples,ensure_ascii=False,indent=2)+'\n')
