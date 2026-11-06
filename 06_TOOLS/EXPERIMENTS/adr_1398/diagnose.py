"""Inspect immutable actual commands and their executed query; no model calls."""
from common import *
reka=ART/'public-live/reka-provider-matrix';deep=ART/'public-live/deepinfra-provider-matrix'
records=[]
for n in (7,8,9,10,12,13,14,15,17,18,19,20):
 p=reka/'canonical'/f'{n:03}-output.json.gz';records.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'value':read(p)})
command=read(deep/'canonical/007-output.json.gz');check=read(deep/'canonical/008-output.json.gz');view=read(deep/'canonical/009.json.gz')['view'];derivations=read(deep/'authorized-derivations.json')
d=next(x for x in derivations if x['request_id'].endswith('turn-3'))
assert command['method_id']=='RESEARCH_REENTER' and command['task'] is None and command['queries'] is None
assert check['valid'] is True and d['original_question']!=d['effective_question']
assert view['request']==d['effective_question'] and view['current_request']==d['original_question']
put(ART/'command-and-execution-diagnosis.json',{'reka':{'actual_commands_and_reviews':records,'T3_T4_T5_are_clarify_not_answer_success':True,'new_topic_T4_repair_identical_to_initial':read(reka/'canonical/012-output.json.gz')==read(reka/'canonical/014-output.json.gz')},'deepinfra':{'command':command,'review':check,'actual_question':d['original_question'],'executed_retrieval_question':d['effective_question'],'request':view['request'],'current_request':view['current_request'],'issues':view['issues'],'state_fields_not_rewritten_by_server':True,'actual_answer_not_completed':True},'harness_defect':{'where':'lifecycle.author_post','error':'Invalid phase name','authoring_physical_sends':0,'prefix_gate_checked_HTTP200_but_not_semantic_success':True,'not_a_product_Qwen_construction_failure':True},'interpretation':'제공자 변경만으로 해결되지 않았다. REKA는 현재 발언과 어긋난 명령을 보완하지 못했다. DeepInfra는 같은 유형의 명령을 valid로 통과시켜 기존 목적과 쟁점으로 조사를 실행했다. 임시총회 답변이 완성됐다는 뜻은 아니며, 미완료 감독 응답의 내부 원인은 확인되지 않았다.','required_next_design':'후속 관계와 함께 실제 task·queries·facts·scope 변경을 모델이 제시하고, 원래 목표의 재개와 현재 질문의 목적 변경을 구분해 검증해야 한다. 서버 임의 목표/명령 보정이나 검증 삭제로 통과시키지 않는다.'})
print('Actual proposal/review/query disagreement saved; no external calls.')
