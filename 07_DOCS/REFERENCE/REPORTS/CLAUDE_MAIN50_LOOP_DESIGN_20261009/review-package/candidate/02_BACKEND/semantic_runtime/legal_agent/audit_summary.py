"""Bounded public projection. Callers render these strings as escaped text."""
LABELS={'reference':'원문 참조','definition':'정의','term':'용어 관계','occurrence':'용어 출현',
    'structure':'문서 구조','knowledge':'원천 지식', 'CITES':'인용', 'APPLIES_MUTATIS_MUTANDIS':'준용',
    'SPECIFIES_DELEGATED_CASES_OF':'위임사항 구체화','DELEGATES_TO':'위임','ANNEX_REFERENCE':'별표·서식 참조',
    'SYNONYM':'동의어','ANTONYM':'반의어','BROADER_TERM':'상위어','NARROWER_TERM':'하위어',
    'RELATED_TERM':'연관어','DEFINITION_LABEL_CANDIDATE':'정의 후보','TERM_OCCURS_IN':'용어 출현',
    'PARENT':'상위 문맥','CHILD':'하위 문맥','SIBLING':'같은 계층 문맥',
    'LABEL_CONCEPT_CANDIDATE':'표제어 개념 후보','SOURCE_DEFINITION':'원천 정의',
    'BROADER_THAN':'포함','NARROWER_THAN':'피포함','OVERLAPS':'부분 중첩',
    'COUNTERPART_OF':'상보적 역할','RELATED_TO':'기능적 연관'}

def display_lines(summary):
    lines=[]
    for a in summary['action_summary']:
        who={'MODEL':'모델 제출 설명','REVIEWER':'검토자 제출 설명','SYSTEM_POLICY':'시스템 정책'}[a['actor']]
        lines.append(f"{who} · {a['tool']} · {a['status']}: {a['reason']}")
    for e in summary['evidence_decisions']:
        if not e['assessments']: lines.append(f"{e['evidence']} · {e['status']}")
        for a in e['assessments']:
            lines.append(f"{e['evidence']} / {a['question_ref']} · v{a['version']} · {a['disposition']}: {a['reason']}")
    for r in summary['relation_checks']:
        direction={'outgoing':'이 원문에서 연결','incoming':'이 원문을 향한 연결'}.get(r['direction'],r['direction'])
        targets=', '.join(r.get('target_labels',[]))
        lines.append(f"{LABELS.get(r['family'],r['family'])} · {LABELS.get(r['predicate'],r['predicate'])} · {direction} · {targets} · 대상 읽기 {'완료' if r['target_read'] else '미완료'} · 모델 제시 {'확인' if r.get('target_presented') else '미확인'}")
        for a in r['assessments']:
            lines.append(f"  {a['question_ref']} · {a['decision']}: {a['reason']}")
    for h in summary['assessment_history']:
        if h['version']>1:
            lines.append(f"판단 변경 · {h['question_ref']} · v{h['version']} · {h['decision']}: {h['reason']}")
    t=summary['totals']
    footer=[f"전체 실행 {t['actions']} · 원문 {t['evidence']} · 관계 {t['relations']} · 미확인 {t['outstanding']}"]
    summary['truncated']=summary['truncated'] or len(lines)+2>64
    if summary['truncated']: footer.append('화면 요약 일부 생략 · 전체 이력은 실행 journal에 보존')
    footer.append('실행 기록: '+summary['audit']['run_id'])
    return lines[:64-len(footer)]+footer
