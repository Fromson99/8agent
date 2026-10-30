"""Assessment/presentation boundary; validates structure, never infers legal meaning."""
from .errors import ProposalError, ContractError

VERSION = 'assessment-answer-consistency-v1'
PROMPT = ('요청한 쟁점의 직접 결론과 그 근거는 ASSESS claims에서 확정한다. 인용된 표현을 더 구체적인 해석으로 바꾸려면 그 해석도 별도의 근거 있는 claim에 작성한다. 답변 작성 단계에 새 판단을 맡기지 않는다. '
    'PARTIAL/INSUFFICIENT에는 같은 issue_id의 material=true gap으로 미확인 내용을 명시한다. 원문이 필요하면 기존 원문 조사, 실제 사건 사실이 필요하면 MISSING_FACT로 구분한다. '
    'reason에는 남은 의문을 구체적으로 적되 missing_target은 제시된 실제 위치 또는 빈 문자열이다. 번호를 만들어 넣지 않는다. '
    '불필요한 범위만 남았고 질문의 결론이 근거로 확인됐다면 그 판단을 claim과 issue reason에 연결해 COVERED로 평가할 수 있다. 단순히 검사를 통과하려고 부족을 삭제하거나 COVERED로 바꾸지 않는다.')

def enabled(profile):
    return profile.get('candidate_navigation', {}).get('assessment_consistency', False)

def validate_proposal(value):
    """Called after schema validation, before adoption; uses existing repair owner."""
    blocked = {g['issue_id'] for g in value['gaps'] if g['material']}
    problems = [r['issue_id'] + ': ' + r['status'] +
        ' requires an explicit material gap for the same issue. Preserve the unresolved requirement in gaps; do not silently drop it or upgrade coverage to pass validation.'
        for r in value['issue_assessments'] if r['status'] != 'COVERED' and r['issue_id'] not in blocked]
    if problems:
        from .output_contract import OutputContractError,issue
        rows=[issue('ASSESSMENT_MATERIAL_GAP_REQUIRED','/issue_assessments/'+str(n)+'/status',
            related=('/gaps',),expected={'issue_id':r['issue_id'],'material_gap_required':True})
            for n,r in enumerate(value['issue_assessments']) if r['status']!='COVERED' and r['issue_id'] not in blocked]
        raise OutputContractError('; '.join(problems),rows,category='DECISION_CONFLICT')

def may_rewrite(assessment):
    """Choose before COMPOSE invocation/stream creation, including open read judgments."""
    return (assessment.get('disposition') == 'ANSWER'
        and assessment.get('answer_coverage') == 'COVERED'
        and bool(assessment.get('issue_assessments'))
        and all(r['status'] == 'COVERED' for r in assessment['issue_assessments'])
        and not any(g.get('material', True) for g in assessment.get('gaps', []))
        and not assessment.get('limitations')
        and not assessment.get('source_excerpt_reply'))

def verify_publication(assessment):
    """Reject an unresolved committed assessment whose visible boundary was lost."""
    if not may_rewrite(assessment) and not assessment.get('limitations'):
        raise ContractError('unresolved assessment requires visible limitations before composition')
