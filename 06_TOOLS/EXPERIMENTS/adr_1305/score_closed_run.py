"""Post-run manual semantic assessment; no network, product calls, or model judge."""
from common import *
from collections import Counter

def find_field(value, name):
    if isinstance(value, dict):
        if name in value:
            yield value[name]
        for child in value.values():
            yield from find_field(child, name)
    elif isinstance(value, list):
        for child in value:
            yield from find_field(child, name)

rows = []
diagnostics = []
for article, assessment_n, repair_n, verdict in [(365, 5, 6, 'ERROR'), (369, 8, 9, 'INCOMPLETE')]:
    cell = f'ontology-{article}-sqlite'
    folder = ART/'live'/cell
    assessment_path = folder/'canonical'/f'{assessment_n:03}-output.json.gz'
    proposal = read(assessment_path)
    repair_path = folder/'canonical'/f'{repair_n:03}.json.gz'
    feedback, = find_field(read(repair_path), 'repair_feedback')
    issues = feedback['validation']['issues']
    repaired_path = folder/'canonical'/f'{repair_n:03}-output.json.gz'
    repeated = proposal == read(repaired_path) if repaired_path.exists() else None
    diagnostics.append({
        'cell': cell,
        'feedback_category': feedback['validation']['category'],
        'feedback_error': feedback['errors'],
        'feedback_issue_codes': dict(Counter(i['code'] for i in issues)),
        'feedback_issue_count': len(issues),
        'issue_count_scope': 'Only the issues actually transmitted in this repair prompt; not a complete validator inventory.',
        'repair_assessment_identical': repeated,
        'assessment_semantic_sha256': hashlib.sha256(json.dumps(proposal,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        'proposed_claim_count': len(proposal['claims']),
        'judgment_dispositions': dict(Counter(j['disposition'] for j in proposal['read_judgment_review']['judgments'])),
        'evidence': [{'path':str(p.relative_to(ROOT)), 'sha256':sha(p)} for p in [assessment_path,repair_path,*([repaired_path] if repaired_path.exists() else [])]],
    })
    if article == 365:
        basis = '제365조 원문을 확보했고 최초 ASSESS의 C1~C3는 연1회 일정시기/연2회 이상 결산회사의 매기/임시총회 필요시 수시라는 핵심 세 규칙을 맞게 제시했다. 다만 전체 원문범위 검토가 빠져 SOURCE_WORK_SCOPE_REQUIRED로 거절됐다. 보완의 여섯 번째 물리호출이 Near AI shared-pool HTTP429여서 제품API503으로 종료됐다. 자동전환/재전송0, 최종답변/채택주장0이다. 최종 내용오답 판정은 불가하다.'
        checks = [
            {'claim':'C1','source_unit':'1389','criterion':'매년 1회 일정한 시기에 정기총회 소집','draft_core_rule_match':True},
            {'claim':'C2','source_unit':'1390','criterion':'연 2회 이상 결산기인 회사는 매기에 총회 소집','draft_core_rule_match':True},
            {'claim':'C3','source_unit':'1391','criterion':'임시총회는 필요한 경우 수시 소집','draft_core_rule_match':True},
        ]
    else:
        assert repeated is True
        basis = '제369조 원문을 확보했고 최초/보완 ASSESS의 C1~C3는 1주1개/자기주식 의결권 없음/상호보유의 주체·10분의1 초과 임계값·역방향 보유주식 제한을 원문과 일치하게 제시했다. 별도 준용·계산 규정까지 확장하여 총7주장을 생성했다. 판단은 UNRESOLVED인데 gap은 비어 있고 범위는 USE여서 채택근거 연결과 상태가 맞지 않았다. FINAL_REVIEW_UNRESOLVED_GAP·SCOPE_CLAIM_EVIDENCE·SCOPE_USE_UNSUPPORTED_RANGE 보완 안내에도 동일 평가 JSON을 반환했다. 기존 보완1회 소진 후 API200으로 확보원문만 반환했고 최종주장0/INCOMPLETE다. HTTP200을 완성 정답으로 세지 않는다.'
        checks = [
            {'claim':'C1','source_unit':'1421','criterion':'1주당 의결권 1개','draft_core_rule_match':True},
            {'claim':'C2','source_unit':'1422','criterion':'회사가 가진 자기주식은 의결권 없음','draft_core_rule_match':True},
            {'claim':'C3','source_unit':'1423','criterion':'회사, 모회사 및 자회사 또는 자회사의 타회사 발행주식 총수 10분의1 초과 보유; 그 다른 회사가 가진 회사 또는 모회사 주식에 의결권 없음','draft_core_rule_match':True},
        ]
    rows.append({'case_id':f'ontology-{article}','cell':cell,'verdict':verdict,
                 'basis':basis,'error_taxonomy':'other','required_rules':3,
                 'final_covered_rules':None,'final_claim_count':0,
                 'draft_core_rules_matched':3,'draft_rule_checks':checks,
                 'draft_is_successful_final_answer':False,
                 'required_article_retrieved':True,
                 'repair_assessment_identical':repeated})

put(ART/'review-failure-diagnosis.json',{'rows':diagnostics,'new_model_calls':0,'product_changes':0})
put(ART/'semantic-review.json',{
    'method':'Manual source-based review of recorded claims, original scoring-only article spans, final API response and repair feedback. Not an external-model judge.',
    'rows':rows,'required_articles_retrieved':2,'planned_questions':2,
    'completed_correct_answers':0,'final_content_accuracy':None,
    'final_content_accuracy_reason':'No completed final answer exists; technical error and source-only incomplete response are not scored as legal wrong answers.',
    'draft_core_rules_matched':6,'draft_core_rules_checked':6,
    'draft_review_scope':'Only the six question-specific core rules; no assertion of full legal quality or validation of all four additional claims.',
    'external_judge_calls':0,'gold_supplied_to_product':False,
    'limits':'Two previously known stored-source questions; not a general correctness rate or a provider stability comparison.'})
print(json.dumps({'semantic_verdicts':[r['verdict'] for r in rows],
                  'feedback_counts':[{k:d[k] for k in ['cell','feedback_issue_codes','repair_assessment_identical']} for d in diagnostics]},ensure_ascii=False))
