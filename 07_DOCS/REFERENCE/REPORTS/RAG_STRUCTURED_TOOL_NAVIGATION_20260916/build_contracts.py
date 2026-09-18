"""Generate design-only contract examples; no runtime imports or model calls."""
from pathlib import Path
import copy,json
ROOT=Path(__file__).resolve().parent
S={'type':'string','minLength':1}; ID=S
I={'type':'integer','minimum':0}; CUR={'type':['string','null']}
HASH={'type':'string','pattern':'^[a-f0-9]{64}$'}
def arr(item,minimum=0):return {'type':'array','items':item,'minItems':minimum}
def enum(*items):return {'type':'string','enum':list(items)}
def obj(props,required=None):return {'type':'object','properties':props,'required':list(props) if required is None else required,'additionalProperties':False}
def ref(name):return {'$ref':'#/$defs/'+name}
def write(name,data): (ROOT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
args={
 'CATALOG':obj({'title_query':{'type':'string'},'document_kind':S,'source':S,'version_id':S,'cursor':CUR},[]),
 'STARTS':obj({'slot':enum('documents','terms','structures','explicit'),'cursor':CUR},['slot']),
 'OPEN_TERM':obj({'term_id':ID,'cursor':CUR},['term_id']),
 'GRAPH':obj({'term_id':ID,'direction':enum('outgoing','incoming','both'),'relation_codes':arr(S),'hops':{'type':'integer','minimum':1,'maximum':3},'cursor':CUR},['term_id','direction','hops']),
 'LIST':obj({'term_ids':arr(ID),'match':enum('any','all'),'structure_id':ID,'document_id':ID,'cursor':CUR},[]),
 'STRUCTURE':obj({'document_id':ID,'structure_id':ID,'cursor':CUR},[]),
 'SOURCE_TERMS':obj({'source_id':ID,'read_unit_id':ID,'cursor':CUR},[]),
 'GREP':obj({'literal':S,'match_mode':enum('exact','normalized'),'document_ids':arr(ID),'structure_id':ID,'cursor':CUR},['literal','match_mode']),
 'SEARCH':obj({'mode':enum('fulltext','embedding','hybrid'),'query':S,'document_ids':arr(ID),'structure_id':ID,'cursor':CUR},['mode','query']),
 'READ':obj({'read_unit_id':ID,'structure_id':ID},[]),
 'REFERENCES':obj({'read_receipt_id':ID,'cursor':CUR},['read_receipt_id']),
 'JUDGE':obj({'read_receipt_id':ID,'extent_id':ID,'issue_id':ID,'verdict':enum('adopted','excluded','deferred'),'quote':{'type':'string'},'claim':{'type':'string'},'supersedes':ID},['read_receipt_id','extent_id','issue_id','verdict','quote','claim']),
 'RELEASE':obj({'read_receipt_id':ID}),
 'BRANCH':obj({'operation':enum('open','back','defer','reopen'),'focus_id':ID}),
 'HISTORY':obj({'issue_id':ID,'branch_id':ID,'action_id':ID,'cursor':CUR},[]),
 'STOP':obj({'proposed_status':enum('complete','partial','waiting_user'),'issue_ids':arr(ID,1),'remaining_explanation':{'type':'string'}})
}
args['LIST']['anyOf']=[{'required':['term_ids'],'properties':{'term_ids':arr(ID,1)}},{'required':['structure_id']}]
for tool,fields in [('STRUCTURE',['document_id','structure_id']),('SOURCE_TERMS',['source_id','read_unit_id']),('READ',['read_unit_id','structure_id'])]:args[tool]['oneOf']=[{'required':[f]} for f in fields]
args['JUDGE']['allOf']=[{'if':{'properties':{'verdict':{'const':'adopted'}}},'then':{'properties':{'quote':S,'claim':S}}}]
calls=[obj({'tool':{'const':tool},'issue_id':ID,'reason':S,'args':schema}) for tool,schema in args.items()]
catalogue=obj({'document_id':ID,'name':S,'document_kind':enum('LAW','DECREE','REGULATION','INTERNAL_RULE','OTHER','UNKNOWN'),'version_label':{'type':['string','null']},'metadata_status':enum('VERIFIED','PARTIAL','UNKNOWN'),'root_structure_ids':arr(ID)})
graph=obj({'edge_id':ID,'source_term_id':ID,'target_term_id':ID,'relation_code':S,'relation_label':{'type':['string','null']},'source_status':S,'traversed_from':ID,'traversed_to':ID,'path_edge_ids':arr(ID,1),'provenance_ref':ID})
envelope=obj({'status':enum('OK','EMPTY','PARTIAL','NEEDS_SELECTION','UNAVAILABLE','INVALID_ARGUMENT','STALE_BINDING','BUDGET_BLOCKED','FAILED'),'receipt_id':ID,'tool':enum(*args),'query_fingerprint':HASH,'generation_id':ID,'scope_hash':HASH,'items':arr({'type':'object'}),'total':{'type':['integer','null'],'minimum':0},'total_kind':enum('EXACT','LOWER_BOUND','UNKNOWN'),'next_cursor':CUR,'coverage':obj({'basis':enum('CATALOGUE_FILTER','LITERAL_MATCHES','LEXICAL_MATCHES','VECTOR_WINDOW','GRAPH_FRONTIER','STRUCTURAL_SCOPE','ACTION_STATE'),'enumeration_complete':{'type':'boolean'},'semantic_exhaustiveness':{'const':'NOT_CERTIFIED'}}),'warnings':arr(S),'recovery_options':arr(obj({'tool':enum(*args),'reason':S}))})
envelope['allOf']=[{'if':{'properties':{'status':{'const':'EMPTY'}}},'then':{'properties':{'items':{'maxItems':0}}}},{'if':{'properties':{'total_kind':{'const':'EXACT'}}},'then':{'properties':{'total':{'type':'integer','minimum':0}}}},{'if':{'properties':{'total_kind':{'const':'UNKNOWN'}}},'then':{'properties':{'total':{'type':'null'}}}}]
extent=obj({'extent_id':ID,'document_id':ID,'block_id':ID,'start_char':I,'end_char':{'type':'integer','minimum':1},'text_sha256':HASH,'role':enum('BODY','PARENT_INTRO','ATTACHMENT','TABLE_HEADER','TABLE_ROWS','FOOTNOTE','RESIDUAL')})
read=obj({'read_receipt_id':ID,'generation_id':ID,'scope_hash':HASH,'source_store_sha256':HASH,'read_unit_ids':arr(ID,1),'legacy_source_ids':arr(ID,1),'extents':arr(ref('ReadExtent'),1),'dependency_read_unit_ids':arr(ID),'unit_complete':{'type':'boolean'},'subtree_complete':{'type':'boolean'},'unread_descendant_cursor':CUR,'structure_warnings':arr(S),'delivery_turn_id':CUR})
completion=obj({'kind':enum('CATALOGUE','EVIDENCE','MIXED','WHOLE_SCOPE_REVIEW'),'status':enum('COMPLETE','PARTIAL','WAITING_USER','FAILED','CANCELLED'),'generation_id':ID,'scope_hash':HASH,'issue_states':arr(obj({'issue_id':ID,'status':enum('COMPLETE','PENDING','BLOCKED','WAITING_USER'),'receipt_ids':arr(ID)}),1),'blockers':arr(obj({'issue_id':ID,'code':S,'detail':S})),'coverage_basis':S,'semantic_exhaustiveness':{'const':'NOT_CERTIFIED'}})
completion['allOf']=[{'if':{'properties':{'status':{'const':'COMPLETE'}}},'then':{'properties':{'blockers':{'maxItems':0},'issue_states':{'items':{'properties':{'status':{'const':'COMPLETE'},'receipt_ids':{'minItems':1}}}}}}}]
defs={'ToolCall':{'oneOf':calls},'CatalogueItem':catalogue,'GraphEdge':graph,'ToolResultEnvelope':envelope,'ReadExtent':extent,'ReadReceipt':read,'Completion':completion}
schema={'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'urn:8-agent:design:structured-navigation-contracts-v1','title':'구조 기반 도구 탐색 경계 계약 — 설계 예제','description':'Design-only boundary subset. Not the complete runtime-v2 API schema or deployed configuration. Server must additionally validate IDs, ACL, generation, source ranges, delivery and ledger completeness.','oneOf':[ref('ToolCall'),ref('ToolResultEnvelope'),ref('ReadReceipt'),ref('Completion')],'$defs':defs}
write('contracts.schema.json',schema)
H='a'*64;valid=[];invalid=[]
def case(name,definition,value):return {'name':name,'definition':definition,'value':value}
def call(tool,**a):return {'tool':tool,'issue_id':'issue:1','reason':'모의 질문의 미확인 항목을 확인','args':a}
for tool,a in [('CATALOG',{}),('GRAPH',{'term_id':'term:example','direction':'both','hops':1}),('LIST',{'term_ids':['term:example'],'match':'all'}),('STRUCTURE',{'document_id':'doc:example'}),('SOURCE_TERMS',{'source_id':'article:example'}),('GREP',{'literal':'모의표현','match_mode':'exact'}),('SEARCH',{'mode':'fulltext','query':'모의 검색어'}),('READ',{'read_unit_id':'read:example'}),('JUDGE',{'read_receipt_id':'receipt:read1','extent_id':'extent:1','issue_id':'issue:1','verdict':'adopted','quote':'모의 원문 문장입니다.','claim':'모의 검토 결과'}),('BRANCH',{'operation':'back','focus_id':'branch:parent'}),('STOP',{'proposed_status':'partial','issue_ids':['issue:1'],'remaining_explanation':'필수 구조 원문이 아직 미열람'})]:valid.append(case('call_'+tool,'ToolCall',call(tool,**a)))
citem={'document_id':'doc:example','name':'모의 문서 A','document_kind':'UNKNOWN','version_label':None,'metadata_status':'UNKNOWN','root_structure_ids':['structure:root']};valid.append(case('catalogue_unknown','CatalogueItem',citem))
gitem={'edge_id':'edge:example','source_term_id':'term:a','target_term_id':'term:b','relation_code':'EXAMPLE_CODE','relation_label':None,'source_status':'UNREVIEWED','traversed_from':'term:b','traversed_to':'term:a','path_edge_ids':['edge:example'],'provenance_ref':'binding:example'};valid.append(case('graph_reverse_preserves_source','GraphEdge',gitem))
base={'status':'OK','receipt_id':'receipt:list1','tool':'CATALOG','query_fingerprint':H,'generation_id':'generation:example','scope_hash':H,'items':[citem],'total':1,'total_kind':'EXACT','next_cursor':None,'coverage':{'basis':'CATALOGUE_FILTER','enumeration_complete':True,'semantic_exhaustiveness':'NOT_CERTIFIED'},'warnings':[],'recovery_options':[]};valid.append(case('catalogue_result','ToolResultEnvelope',base))
partial=copy.deepcopy(base);partial.update(status='PARTIAL',tool='SEARCH',items=[],total=None,total_kind='UNKNOWN',next_cursor='cursor:example');partial['coverage'].update(basis='VECTOR_WINDOW',enumeration_complete=False);partial['warnings']=['모의 미색인 구조 존재'];valid.append(case('vector_partial_unknown_total','ToolResultEnvelope',partial))
rd={'read_receipt_id':'receipt:read1','generation_id':'generation:example','scope_hash':H,'source_store_sha256':H,'read_unit_ids':['read:example'],'legacy_source_ids':['article:example'],'extents':[{'extent_id':'extent:1','document_id':'doc:example','block_id':'block:1','start_char':0,'end_char':12,'text_sha256':H,'role':'BODY'}],'dependency_read_unit_ids':[],'unit_complete':True,'subtree_complete':False,'unread_descendant_cursor':'cursor:children','structure_warnings':[],'delivery_turn_id':'turn:2'};valid.append(case('read_unit_not_subtree','ReadReceipt',rd))
comp={'kind':'CATALOGUE','status':'COMPLETE','generation_id':'generation:example','scope_hash':H,'issue_states':[{'issue_id':'issue:1','status':'COMPLETE','receipt_ids':['receipt:list1']}],'blockers':[],'coverage_basis':'모의 권한 범위의 catalogue 필터 집합','semantic_exhaustiveness':'NOT_CERTIFIED'};valid.append(case('catalogue_complete','Completion',comp))
for name,tool,a in [('read_offset','READ',{'read_unit_id':'read:example','offset':2400}),('read_two_targets','READ',{'read_unit_id':'read:example','structure_id':'structure:example'}),('graph_zero_hops','GRAPH',{'term_id':'term:example','direction':'both','hops':0}),('list_unconstrained','LIST',{}),('list_empty_terms','LIST',{'term_ids':[]}),('judge_empty_quote','JUDGE',{'read_receipt_id':'receipt:read1','extent_id':'extent:1','issue_id':'issue:1','verdict':'adopted','quote':'','claim':'모의'})]:invalid.append(case(name,'ToolCall',call(tool,**a)))
bad=call('READ',read_unit_id='read:example');bad['args']=json.dumps(bad['args']);invalid.append(case('args_json_string','ToolCall',bad))
bad=copy.deepcopy(comp);bad['blockers']=[{'issue_id':'issue:1','code':'UNREAD','detail':'필수 원문 미열람'}];invalid.append(case('complete_with_blocker','Completion',bad))
bad=copy.deepcopy(comp);bad['issue_states'][0]['status']='PENDING';invalid.append(case('complete_pending_issue','Completion',bad))
bad=copy.deepcopy(base);bad['status']='EMPTY';invalid.append(case('empty_with_items','ToolResultEnvelope',bad))
bad=copy.deepcopy(partial);bad['total']=100;invalid.append(case('unknown_total_fabricated','ToolResultEnvelope',bad))
write('contract-examples.json',{'status':'DESIGN_ONLY_SYNTHETIC','note':'These examples verify contract shape only. Placeholder hashes/IDs are not actual source evidence. ACL, reading delivery and semantic correctness need runtime checks.','valid':valid,'invalid':invalid})
