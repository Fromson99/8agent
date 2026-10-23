from common import *
question='모의출장규정에 따라 국내 출장에서 지급하는 경비 항목은 무엇인가?'
base={'id':'E1','document_id':'D1','source_id':'synthetic:1','heading':'모의출장규정 제1조','text':'제1조 국내 출장에 지급하는 경비는 철도운임과 숙박비다.'}
need={**base,'text':'제1조 국내 출장에 지급하는 경비의 항목은 제2조에서 정한다.'}
chain={**base,'id':'E2','source_id':'synthetic:2','heading':'모의출장규정 제2조','text':'제2조 국내 출장 경비의 항목은 별표 1에 정한 항목으로 한다.'}
cases=[]
for ident,sources,target,title in [('enough',[base],'T2','제9조 해외출장 예외'),('missing',[need],'T2','제2조 국내 출장 지급 항목'),('chain',[need,chain],'T3','별표 1 국내 출장 경비 항목')]:
 actions={target:{'id':target,'action':'READ_ARTICLES','identity':{'document_id':'D1','source_id':'synthetic:'+target},'label':title}}
 data={'current_request':question,'issues':[{'id':'Q1','request_quote':question}], 'sources':sources,'basis':[{'id':x['id'],'branch_id':'B1'} for x in sources], 'laws':[{'id':'L1','document_id':'D1','name':'모의출장규정','articles':[{'read_action':target,'article':title,'preview':'아직 본문을 읽지 않았다.'}]}], 'branches':[], 'presentation_id':'synthetic-'+ident,'state_version':9,'control_contract':'control','completion_contract':'investigation-completion-v8','read_batch_limit':8,'investigation_scope':{'request':question}}
 cases.append({'id':ident,'synthetic':True,'question':question,'data':data,'actions':actions,'prior_opinion':ident=='chain'})
save(ART/'stage-inputs.json',cases)
save(ART/'stage-gold.json',{'role':'offline_evaluator_only','cases':{'enough':{'choice':'FINISH'},'missing':{'choice':'READ','target':'T2'},'chain':{'choice':'READ','target':'T3'}},'rationale':'Evidence-present/delegated-evidence-missing pair plus a narrowing dependency chain; synthetic rules, no real legal truth.'})
