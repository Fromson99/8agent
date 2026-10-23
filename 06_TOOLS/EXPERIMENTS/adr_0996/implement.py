from common import *
meta=read(DES/'candidate.json');S=ROOT/meta['path']/'snapshot'/meta['selected_code_relative'];base=S/'02_BACKEND/semantic_runtime/legal_agent'
p=base/'knowledge_delivery.py';s=p.read_text();assert 'USE_FIRST_PROMPT' not in s
s=s.replace("and plan and plan['mode'] == 'consume'", "and plan and plan['mode'] == 'consume' and plan.get('plan', {}).get('items')")
s+='''

USE_FIRST_PROMPT = """
이번 평가는 현재 질문에 필요한 설명을 완성하는 작업이다. 다음 순서를 지킨다.
1. 현재 질문의 요구사항과 legal_review_guidance의 원문별 검토 항목을 대응시킨다. 각 항목을 적용, 조건부 적용, 질문과 무관, 판단 불가 중 하나로 검토한다. 현재 요청에 필요한 새 항목도 식별한다. 저장 지식이 현재 질문의 범위나 결론을 대신하지 않는다.
2. 먼저 현재 evidence_options로 설명할 수 있는 사항을 claims에 작성한다. 저장된 항목의 결론을 복사하지 않고, 실제 원문의 조건·수치·예외를 설명한다. 관련 검토 항목은 claims 또는 gaps에 반영하고, 무관하여 제외하는 항목은 해당 issue_assessments.reason에 짧게 설명한다. 필수 내용을 원문 위치 안내만으로 대신하지 않는다.
3. 그 뒤 남은 미확인 사항을 gaps에 작성한다. 추가 원문 조사 필요성을 제시할 때 gap.reason 한 문장 안에 '답하지 못한 요청 사항 / 제공된 근거로 답할 수 없는 이유 / 확인할 내용이 답에 미치는 영향'을 구체적으로 쓴다. 현재 원문에 이미 있는 사실은 재탐색하지 않는다. 새 질문의 다른 요구사항에 필요한 근거는 별도로 요청한다. 아직 모르는 예외가 있을 수 있다는 추측만으로 조사 범위를 늘리지 않는다.
4. previous_assessments의 의견을 현재 원문으로 재검토한다. 새로운 근거로 반박되지 않고 현재 질문에 필요한 설명은 이번 claims에도 포함한다. 수정·철회는 해당 issue_assessments.reason에 짧은 근거와 이유를 쓴다. 한 항목의 부족 때문에 다른 항목의 근거 있는 설명을 삭제하지 않는다. 과거 의견 자체를 사실로 확정하지 않는다.
5. 최종 점검: 요청한 항목과 관련 검토 항목이 설명 또는 미확인으로 처리되었는지 확인한다. claims와 gaps는 함께 있을 수 있다. 같은 설명·gap·이유는 한 번만 작성한다. 각 진단 reason은 한 문장으로 끝내고 미확인 이유를 되풀이하지 않는다. 기존 JSON 스키마만 사용하고 설명용 새 필드를 추가하지 않는다.
"""

def reuse_mode(execution):
    if not enabled(execution): return 'EXTEND'
    return getattr(execution.host.pipeline.term_agent.transport, 'knowledge_reuse_mode', 'EXTEND')

def assessment_prompt(execution, phase):
    if not phase.startswith('memory-assess') or not enabled(execution): return ''
    mode = reuse_mode(execution)
    if mode == 'CLOSED_EVIDENCE':
        policy = '\\n이번 요청은 CLOSED_EVIDENCE다. 현재 전달된 원문만으로 답하며 평가 이후 추가 탐색은 실행되지 않는다. 부족한 근거나 사실은 gaps에 그대로 기록하고 확인된 claims와 함께 제한 답변을 준비한다. 부족을 숨기거나 추정해서 채우지 않는다.'
    else:
        policy = '\\n이번 요청은 EXTEND다. 현재 전달된 원문을 검토하고, 현재 질문에 필요한 미확인 근거는 기존 조사 경로로 추가 요청할 수 있다.'
    if getattr(execution.host.pipeline.term_agent.transport, 'knowledge_use_first_prompt', False):
        policy += USE_FIRST_PROMPT
    return policy

def block_additional_research(execution, fresh, result):
    if reuse_mode(execution) != 'CLOSED_EVIDENCE': return False
    execution.s.work.event('KNOWLEDGE_CLOSED_EVIDENCE_DECISION', {
        'policy': 'CLOSED_EVIDENCE_AFTER_ORIGINAL_DELIVERY', 'blocked_gaps': deepcopy(fresh),
        'claims_preserved': len(result['claims']), 'gaps_preserved': len(result['gaps']),
        'automatic_legal_approval': False, 'initial_acquisition_excluded': False})
    return True
'''
p.write_text(s)
p=base/'unified_rag.py';s=p.read_text().replace('from .knowledge_delivery import model_input','from .knowledge_delivery import model_input, assessment_prompt').replace('data, delivery = model_input(self, data, phase)','data, delivery = model_input(self, data, phase)\n        system += assessment_prompt(self, phase)');p.write_text(s)
p=base/'completion_execution.py';s=p.read_text();needle="        # A supported claim does not settle the model's remaining material gaps."
assert s.count(needle)==1
s=s.replace(needle,"        from .knowledge_delivery import block_additional_research\n        closed_evidence = block_additional_research(self, fresh, result)\n        can_investigate = can_investigate and not closed_evidence\n"+needle)
s=s.replace("stop_reason = 'ASSESSMENT_REENTRY_LIMIT' if count >= limit else 'INVESTIGATION_BUDGET'", "stop_reason = 'CLOSED_EVIDENCE_POLICY' if closed_evidence else ('ASSESSMENT_REENTRY_LIMIT' if count >= limit else 'INVESTIGATION_BUDGET')")
p.write_text(s)
put(DES/'prompt.json',{'shared_closed':'CLOSED_EVIDENCE blocks only assessment-triggered reentry; initial source acquisition unchanged','candidate_prompt':s if False else (base/'knowledge_delivery.py').read_text().split('USE_FIRST_PROMPT = """',1)[1].split('"""',1)[0],'new_output_schema':False})
print('Candidate prompt and shared closed gate written; no production file changed')
