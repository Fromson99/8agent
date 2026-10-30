from common import *
import sys,gzip
from copy import deepcopy
from types import SimpleNamespace as NS
C=ROOT/read(DES/'candidate.json')['snapshot'];sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent import source_goal_control as sg,investigation_supervisor as su,compact_model_input as compact
from semantic_runtime.legal_agent.navigation_input import NavigationReferences
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1169-supervisor-cm3-memory-reclaimed/artifacts/run-001'
rows=[]
for cid,num in [('cm-001',8),('cm-007',6)]:
 cp=P/cid/'canonical'/f'{num:03}.json.gz';wp=P/cid/'wire'/f'{num:03}.json.gz'
 raw=json.load(gzip.open(cp,'rt'));wire=json.load(gzip.open(wp,'rt'));v=deepcopy(raw['view']);schema=deepcopy(raw['schema'])
 docs=v.get('reference_registry',{}).get('documents',[])
 data={'presentation_id':v.get('presentation_id','saved'), 'issues':v['issues'],'sources':v.get('sources',[]),'laws':[{'document_id':r['document_id'],'name':r['name']} for r in docs]}
 actions={r['target']:{'action':'SEARCH_STRUCTURE','identity':{'document_id':r.get('scope',{}).get('document_id')}} for r in v['tool_options'] if r['choice'] in ('LOCATE','CATALOG_SEARCH')}
 inv=NS(policy={'source_goal_control':True,'supervisor_mode':'enforce'},p={'binding':'saved-comparison'},question=v.get('request',v.get('current_request','')),s=NS(scope=set(read(DES/'corpus.json')['document_ids'])))
 schema=sg.attach(schema,inv,data,actions)
 v['source_target_options']=sg.options(data,actions);v['source_goal_context']=sg.context(inv,data)
 if cid=='cm-007':
  for b in schema['anyOf']:
   if 'action' not in b['properties']:continue
   for name in v.get('read_candidate_page',{}).get('actions',[]):
    b['properties']['action']['anyOf'].append({'type':'object','properties':{'choice':{'const':name}},'required':['choice'],'additionalProperties':False})
 refs=NavigationReferences(v);ws=refs.schema(schema);wv=compact.project(refs.view(v),ws)
 body=deepcopy(wire);body['messages'][0]['content']=sg.PROMPT+'\n'+body['messages'][0]['content'];body['messages'][1]['content']=json.dumps({'view':wv},ensure_ascii=False)
 body['response_format']['json_schema']['schema']=ws
 out=DES/'probe'/cid;put(out/'body.json',body);put(out/'canonical.json',{'view':v,'schema':schema,'data':data,'actions':actions})
 rows.append({'case_id':cid,'body':str((out/'body.json').relative_to(ROOT)),'canonical':str((out/'canonical.json').relative_to(ROOT)),'body_sha256':sha(out/'body.json'),'canonical_sha256':sha(out/'canonical.json'),'parent_canonical':str(cp.relative_to(ROOT)),'parent_canonical_sha256':sha(cp),'parent_wire':str(wp.relative_to(ROOT)),'parent_wire_sha256':sha(wp)})
put(DES/'probe-inputs.json',rows)
put(ART/'evaluation-only/probe-targets.json',{'cm-001':{'document_id':'eae25aa6e8a83c58','name':'코스닥시장 상장규정 시행세칙','coordinate':'제23조'},'cm-007':{'document_id':'4a65961091da5fb7','name':'유가증권시장 상장규정','coordinate':'제13조'}})
print('two saved inputs prepared, no gold/product mixing, no model calls')
