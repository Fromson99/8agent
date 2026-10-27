"""The server computes closure; a model cannot directly declare READY."""


def evaluate(repo, packed, *, exhausted=False, limitations=()):
    claims = repo.heads('claim', current=True)
    reviews = {r['payload'].get('claim_id'): r['payload'] for r in repo.heads('review', current=True)
               if 'claim_id' in r['payload']}
    unresolved = list(limitations)+list(packed['unresolved'])
    conflicting_issues = {a['payload']['issue_id'] for a in repo.heads('assessment', current=True)
                          if a['payload']['relation'] == 'contradicts'}
    accepted, covered, needs_rewrite, needs_research = [], set(), False, False
    for claim in claims:
        r = reviews.get(claim['entity_id'])
        if not r or r['claim_version'] != claim['version'] or r['verdict'] != 'SUPPORTED':
            unresolved.append(r['reason'] if r else '현재 답변 문장의 근거 검토가 완료되지 않았습니다.')
            needs_rewrite |= bool(r and r['verdict'] == 'NEEDS_REWRITE')
            needs_research |= bool(r and r['verdict'] == 'NEEDS_RESEARCH')
            continue
        if not set(claim['payload']['evidence_ids']) <= set(packed['evidence_ids']):
            unresolved.append('현재 조립 근거에 포함되지 않은 문장은 제외했습니다.')
            continue
        findings = [repo.head('finding', f) for f in claim['payload']['finding_ids']]
        if any(f['payload']['issue_id'] in conflicting_issues for f in findings):
            # A supportive review cannot silently override a live contradiction.
            # Resolve/retract the assessment or revise the issue before asserting.
            unresolved.append('상충 판단이 해결되지 않은 쟁점의 결론은 답변에서 제외했습니다.')
            continue
        covered.update(f['payload']['issue_id'] for f in findings)
        if claim['payload']['purpose'] == 'answer':
            accepted.append(claim)
    facts = repo.heads('fact', current=True)
    missing_facts = [f['payload']['name'] for f in facts if f['payload']['status'] == 'unknown']
    unresolved.extend('사용자 사실 확인 필요: '+name for name in missing_facts)
    for assessment in repo.heads('assessment', current=True):
        if assessment['payload']['relation'] == 'contradicts':
            unresolved.append('현재 쟁점에 상충하는 원문 판단이 남아 있습니다: '+assessment['payload']['reason'])
    for issue in repo.heads('issue', current=True):
        p = issue['payload']
        if p['state'] == 'SUPERSEDED':
            continue
        if p['state'] == 'UNRESOLVED':
            unresolved.append(p['reason'])
        elif p['required'] and issue['entity_id'] not in covered:
            unresolved.append('확인하지 못한 쟁점: '+p['text'])
    # All Q IDs being attached to issues does not satisfy this independent check.
    direct = next((h['payload'] for h in repo.heads('review', current=True) if h['entity_id'] == 'R:question'), None)
    if direct is None:
        unresolved.append('질문 원문과 최종 답변의 직접 대조가 완료되지 않았습니다.')
    else:
        retained = {c['entity_id'] for c in accepted}
        for q in direct['question_checks']:
            if q['status'] != 'RESOLVED' or not set(q['claim_ids']) <= retained or not q['claim_ids']:
                unresolved.append('질문 '+q['question_piece_id']+': '+q['reason'])
                needs_research |= q['status'] == 'MISSING' and bool(q['follow_up_reads'])
        if direct['whole_question']['status'] != 'RESOLVED':
            unresolved.append(direct['whole_question']['reason'])
            needs_research |= bool(direct['whole_question']['follow_up_reads'])
    pending = any(t['status'] == 'PENDING' for t in repo.frontier())
    if pending:
        unresolved.append('검토에서 요청한 추가 원문 확인이 남아 있습니다.')
    if not accepted:
        unresolved.append('확인 가능한 근거가 부족합니다.')
    if any(repo.evidence(e)['temporal_status'] == 'unknown' for c in accepted for e in c['payload']['evidence_ids']):
        unresolved.append('저장된 원문 판본의 현행 적용 여부는 확인하지 못했습니다.')
    unresolved = list(dict.fromkeys(unresolved))
    gate = 'CLARIFY' if missing_facts else 'BOUNDED' if unresolved else 'READY'
    decision = 'FINAL'
    if not exhausted and pending and needs_research:
        decision = 'RESEARCH'
    elif not exhausted and needs_rewrite:
        decision = 'RECOMPOSE'
    # Detailed reasons stay intact below; the bounded control port is a summary.
    reason = '; '.join(unresolved) or '현재 근거와 검사를 통과했습니다.'
    if len(reason) > 10000:
        reason = f'확인 필요 항목 {len(unresolved)}개. 전체 사유는 answer.unresolved에 보존했습니다.'
    return {'control': {'decision': decision, 'gate': gate, 'reason': reason,
                        'state_revision': repo.run()['state_revision'], 'evidence_revision': repo.run()['evidence_revision']},
            'claims': accepted, 'unresolved': unresolved}
