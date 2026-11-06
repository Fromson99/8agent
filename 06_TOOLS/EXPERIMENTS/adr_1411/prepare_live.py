from common import *
cases=read(ROOT/'01_DATA/review/cm_core_e2e_v3.json')['cases']
C=ROOT/read(DES/'candidate-selected.json')['code_root']
public=read(C/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']
followups={'cm-003':'취득 시점은 상장예비심사 신청일의 6개월 전이고, 벤처금융이나 전문투자자에 해당하지 않는 일반 재무적투자자야. 이 조건으로 이어서 확인해줘.',
 'cm-018':'내가 원하는 건 제49조 제1항의 원칙과 각 호 기준의 관계야. 지금까지 읽은 본문으로 설명하고 미확인 연결은 남겨줘.'}
live=[]
for cid in ('cm-003','cm-018'):
 q=next(c['question'] for c in cases if c['id']==cid)
 live.append({'id':cid,'document_ids':public,'steps':[{'number':1,'question':q},
     {'number':2,'question':followups[cid],'synthetic_followup_not_real_user_facts':True},
     {'number':3,'question':'지금 답변의 조건과 출처를 확인했어. 이 조사 결과를 기억해줘.','requires_resolved':True},
     {'number':4,'question':q+'\n'+followups[cid]+' 같은 조건으로 확인한 경험을 재사용해줘.','requires_saved_knowledge':True,'new_session':True}]})
put(DES/'live-cases.json',live)
put(DES/'provider-policy.json',read(C/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
put(DES/'authorization.json',{'user':'구현해봐 쭉 그리고 실험해보고 메인에 반영까지 해줘',
 'question_authorization_path':'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json',
 'question_authorization_sha256':sha(ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json'),
 'documents':public,'scope':'Financial cm question strings and synthetic followups; public originals intersect actual financial team; no reference answers or internal sources',
 'order':['cm-003 guided','cm-003 baseline','cm-018 guided','cm-018 baseline'],'stop_on_unknown':True})
m=read(ADR/'실험/manifest.json')
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={arm:stages for arm in ('baseline','guided')}
m['dataset'].update(frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),DES/'live-cases.json',DES/'authorization.json',DES/'provider-policy.json',DES/'candidate-selected.json',DES/'criteria.json',DES/'user-steering.json']
paths.extend(ROOT/p for p in ['02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/openrouter_legal_adapter.py','02_BACKEND/lawrag/core/request_deadline.py'])
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'model_calls_before_freeze':0})
print('CM003/018 and natural language continuation/confirmation/reuse frozen; global40 calls')
