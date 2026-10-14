"""Native seven-stage completion behavior; no alternate runner or judge."""
from copy import deepcopy
from jsonschema import ValidationError
from ..contracts import digest
from . import completion_contracts as cc
from . import completion_v5 as v5, request_repair as rr
from . import investigation_contracts as ic
from . import investigation_chain as trail
from .corrected_memory import Reenter, MemoryError
from .errors import InvestigationPending, ProposalError, ContractError


ASSESS_PROMPT = '''v4: 선택/누적 요건이나 예외가 중요한 claim에는 rule 관측값을 작성한다. 단순 claim은 rule=null이다.
rule.conditions는 원문 span을 참조하고 groups의 ALL/ANY/UNKNOWN 및 root로 중첩 관계를 보존한다. 없는 관계나 예외를 단정하지 않는다.
rule.conclusion은 요건 목록을 반복하지 않는 결론만 쓴다. 조건·예외는 코드가 해당 구조에서 한 번 조립하며 claim.text로 다시 생성하지 않는다.
일반 설명은 GENERAL_RULE과 빈 fact_refs, 특정 사건 적용은 CASE_APPLICATION과 실제 user_fact_sources의 U ID·정확한 사용자 원문 quote를 쓴다. 법령으로 사실 충족을 증명하지 않는다.
같은 결론은 하나의 claim_id로 만들고 관련 issue_refs가 함께 참조한다.
현재 질문 원문의 요구사항·주체·조건·예외를 그대로 유지하여 쟁점별로 판단한다.
제공된 evidence_options의 원문만 법률 근거다. 인용을 다시 쓰지 말고 evidence_refs에 제공된 S ID를 고른다.
claim_id는 C1부터 고유하게 부여하고 각 판단의 issue_refs를 연결한다. claim.text는 선택한 원문의 법률 규칙 또는 현재 사실에 대한 조건부 적용이다.
각 쟁점의 첫 claim은 그 쟁점 질문에 대한 직접 결론으로 쓰고, 이어지는 claim에 요건·예외·조건을 쓴다. 구분·비교를 묻는 쟁점은 대상 사이의 차이를 직접 설명하는 claim을 둔다.
같은 쟁점의 claim끼리 모순되지 않게 한다. 원문이 "다음 중 하나"처럼 선택 요건을 정하면 그 선택 구조를 한 claim 안에 유지하고, 다른 claim에서 그중 하나를 모든 경우의 필수 요건으로 쓰지 않는다. 특례·예외 조문만으로 일반 질문 전체에 답하지 않는다.
필요조건 하나의 충족이나 특정 금지 대상 제외를 전체 적법성으로 확대하지 않는다. 원문에 없는 효과·거래제한·다른 회사 유형·조문을 추가하지 않는다.
사용자 사실을 법령으로 인용하지 않는다. 자료제출처럼 같은 단어라도 질문의 주체·행위가 다르면 WRONG_SUBJECT다.
자료의 본문·다른 항·예외·시행령이 부족하면 material=true gap을 쓰고 NEEDS_INVESTIGATION으로 조사한다.
gap마다 missing_target에 확인하지 못한 원문의 문서·조문·별표 표기를 짧게 쓴다(예: 벤처기업육성에 관한 특별법 시행령 제11조의3, 별표 17-1). 사용자 사실 부족이면 빈 문자열이다.
일반 규칙·정의·절차를 묻는 질문은 특정 회사나 사람의 실제 사실 확인을 요구하지 않는다. 사용자가 특정 사건에 적용해 달라고 요청한 경우에만, 그 결론을 바꾸는 미제공 사실을 MISSING_FACT와 REQUEST_FACT로 기록한다.
법령·시행령·다른 항의 내용이 없다는 것은 사용자 사실 부족이 아니다. MISSING_SOURCE/MISSING_SCOPE/UNREAD_SAVED/UNRESOLVED_REFERENCE 중 맞는 gap과 자료 조사 행동을 선택한다. MISSING_FACT의 material_id는 null이며 법령 목록·적용 범위·규정 내용은 사용자에게 묻지 않는다.
일반 규칙의 조건과 예외를 조건부로 설명하는 것만으로 요청을 충족하면, 실제 적용 사실이 주어지지 않았다는 이유로 gap을 만들지 않는다.
예: 모의 규정의 신고 기한 질문은 규정의 기한을 설명한다. 특정 신청이 기한을 넘겼는지 판단해 달라는 질문에서 신청일이 없으면 사용자 사실 부족이다. 위임된 세부 서류 목록의 원문이 없으면 원문 조사 부족이다.
질문과 무관한 미해결 참조만 material=false로 둘 수 있다. 핵심 gap이 있는 쟁점을 COVERED로 표시하지 않는다.
gap_history는 이전 판단에서 낸 부족과 조사 단계의 처리 결과다. NOT_AVAILABLE은 허용된 자료에서 찾지 못한 것, UNRESOLVED는 조사 한도로 확보하지 못한 것이다. 이미 낸 같은 부족은 다시 조사를 요청해도 실행되지 않는다. 그 gap은 material=true로 남기고 확인된 범위로 LIMITED_ANSWER를 쓴다. NOT_NEEDED에 동의하지 않으면 이유를 gap reason에 구체적으로 쓴다.
navigation_uncovered_issues는 조사 단계가 채택 근거를 찾지 못했다고 보고한 쟁점이다. reference_leads는 아직 읽지 않은 연결의 단서이며 인용 근거가 아니다.
답할 수 없는 요구사항을 없애거나 다른 질문으로 바꾸지 않는다. 저장 자료 메타데이터는 인용 원문이 아니다.
limitations 자유문장은 작성하지 않는다. 필요한 법률 설명은 근거 있는 claim에, 미확인 범위는 gap에 기록한다.
진단 reason은 짧게 쓰고 repair_feedback의 모든 독립 오류를 함께 고친다. JSON 스키마를 따른다.'''

INTENT_PROMPT = ('원문 질문의 주체·행위·요구 범위·예외를 보존해 쟁점을 나눈다. '
    '찾을 수 있을 법한 질문으로 축소하지 않는다. 일반 규칙 설명과 특정 사건에 대한 적용 판단을 목적에서 구분한다. 일반 규칙 질문에 특정 회사나 인물의 사실 확인 요구를 추가하지 않는다. issues에는 요청한 요구사항만 넣고 '
    '질문에 없는 배경 쟁점(일반적인 결정 요건, 관련 제도 전반 등)을 새로 만들지 않는다. 요구가 하나면 Q1 하나만 둔다. '
    '검색 결과나 과거 답변을 정답으로 사용하지 않는다. JSON만 출력한다.')

CLOSED_STATUSES = ('NOT_AVAILABLE', 'NOT_NEEDED', 'UNRESOLVED')


def gap_history(selection):
    """Earlier assessment gaps with the navigation outcome of each round."""
    rounds = (selection.get('investigation_state') or {}).get('gap_rounds', [])
    history = []
    for r in rounds:
        resolved = {x['gap_id']: x for x in r.get('resolutions') or []}
        history.append({'round': r['round'], 'investigative_actions': r.get('actions', 0),
            'newly_adopted_originals': len(set(r.get('adopted_at_close') or []) - set(r.get('adopted_at_open') or [])),
            'gaps': [{'gap_key': g['gap_key'], 'issue_id': g['issue_id'], 'kind': g['kind'],
                      'missing_target': g.get('missing_target', ''), 'reason': g['reason'],
                      'navigation_status': resolved.get(g['gap_id'], {}).get('status'),
                      'navigation_reason': resolved.get(g['gap_id'], {}).get('reason')} for g in r['gaps']]})
    return history


def reference_leads(nav, limit=24):
    """Unread connections of adopted originals as short leads; never quote text."""
    rows = []
    for group in nav.get('groups', []):
        pending = [c for c in group.get('connections', []) if not c.get('already_read')]
        if not pending:
            continue
        policy = pending[0].get('reading_policy') or {}
        anchor, target = group.get('anchor') or {}, group.get('target') or {}
        rows.append({'from': ' '.join(x for x in (anchor.get('document_name'), anchor.get('heading')) if x),
                     'to': ' '.join(x for x in (target.get('document_name'), target.get('heading')) if x),
                     'kind': policy.get('kind'), 'obligation': policy.get('obligation'),
                     'direction': group.get('direction')})
    unresolved = [{'from': ' '.join(x for x in (u.get('document_name'), u.get('heading')) if x),
                   'locator': u.get('locator'), 'reason': u.get('reason_code')} for u in nav.get('unresolved', [])]
    return {'pending_unread': rows[:limit], 'pending_unread_total': len(rows),
            'unresolved': unresolved[:12], 'unresolved_total': len(unresolved),
            'limits': list(nav.get('limits', []))[:4]}


class CompletionExecution:
    def completion_stage(self, stage, state, parts, utterance, format, data):
        profile=getattr(self.s.sources,'profile',{})
        modern=rr.enabled(profile)
        contract=cc.version(profile)
        if stage == 'INTENT':
            from .memory_rag import INTENT
            wire = ic.intent_schema(INTENT)
            if modern:wire=v5.intent_schema(wire)
            from .request_entry import consume
            result = consume(self,state,utterance)
            if result is None:
                result = self.invoke(INTENT_PROMPT+('\n'+v5.SCOPE_PROMPT if modern else ''), {**data, 'current_request': utterance}, wire, 'memory-intent')
            if len({i['id'] for i in result['issues']}) != len(result['issues']):
                raise ProposalError('duplicate request issue')
            if modern:v5.verify_intent(result,utterance)
            return {**result, 'completion_contract': contract,
                    'request_text': utterance, 'request_hash': digest(utterance)}
        read = parts['READ']['payload']
        self.host.verify(read)
        selection = parts['SELECT']['payload']
        selected = set(selection['final_ids'])
        sources = [s for s in self.selected_originals(parts) if s['source_id'] in selected]
        if stage == 'COMPOSE':
            assessment = parts['ASSESS']['payload']
            self.verify_claims(assessment['claims'], sources)
            # Preserve the seventh durable stage with no extra generative call.
            # Accepted wording is already produced in ASSESS; formatting is deterministic.
            plan = cc.default_plan(assessment, format, selection.get('issues'))
            result = cc.compose(assessment, plan)
            cc.verify_composition(assessment, result)
            self.s.work.event('COMPOSITION_RENDERED', {'contract': result['completion_contract'],
                'assessment_hash': digest(assessment), 'plan': plan,
                'text_hash': digest(result['text']), 'model_call': False})
            self.s.work.event('FINAL_REVIEW_SKIPPED', {'stage': stage, 'policy': 'disabled',
                'structural_render_verified': True, 'claim_review_status': 'UNREVIEWED',
                'quality_certified': False})
            return result

        self.issues = selection['issues']
        self.saved_material_ids = [r['material_id'] for r in selection.get('saved_inventory', [])]
        options = cc.evidence_options(sources)
        fact_sources = [{'id':'U0','text':utterance}] + [
            {'id':'U'+str(n),'text':str(f.get('value',''))} for n,f in enumerate(state.get('facts',[]),1)]
        schema = cc.assessment_schema(self.issues, self.saved_material_ids, options,
            contract=cc.CONTRACT, facts=fact_sources)
        history = gap_history(selection)
        if modern:
            schema=v5.assessment_schema(self.issues,self.saved_material_ids,options,fact_sources,
                [g['gap_key'] for r in history for g in r['gaps']])
        current_basis = {ref for group in (selection.get('investigation_state') or {}).get('groups',{}).values()
            for decision in group.get('issue_decisions',{}).values() if decision.get('status') in ('ADOPT','KEEP')
            for ref in decision.get('basis_refs',[])}
        rounds = (selection.get('investigation_state') or {}).get('gap_rounds',[])
        raised = {g['gap_key'] for r in rounds for g in r['gaps']
            if not (current_basis - set(r.get('adopted_at_close') or r.get('adopted_at_open') or []))}
        closed = {g['gap_key']: g['navigation_status'] for r in history for g in r['gaps']
                  if g['navigation_status'] in CLOSED_STATUSES}
        investigation = selection.get('investigation_state') or {}
        fallback = bool(selection.get('adoption_fallback'))
        context = {k: v for k, v in data.items() if k != 'investigation_chain'}
        if data.get('investigation_chain'):
            context['investigation_chain'] = trail.compact(data['investigation_chain'],
                brief=self.s.profile.get('candidate_navigation',{}).get('compact_input',False))
        basis = {'contract':contract,'request_hash':digest(utterance),'state_hash':digest(state),
            'binding':self.host.binding,'evidence_hash':digest(options),'issues':self.issues,
            'gap_outcomes':[{k:v for k,v in r.items() if k != 'investigative_actions'} for r in history],
            'stop_reason':selection.get('stop_reason')}
        signature = digest(basis)
        if hasattr(self.s.work, 'db'):
            import json
            row=self.s.work.db.execute("SELECT payload_json,payload_hash FROM event WHERE kind='ASSESSMENT_VALIDATED' AND json_extract(payload_json,'$.basis_hash')=? ORDER BY seq DESC LIMIT 1", (signature,)).fetchone()
            if row is not None:
                saved=json.loads(row[0])
                if digest(saved)!=row[1]:raise ContractError('assessment cache journal hash mismatch')
                cached=saved['assessment']
                self.verify_claims(cached['claims'], sources)
                self.s.work.event('ASSESSMENT_REUSED', {'basis_hash':signature})
                return deepcopy(cached)
        model_sources=sources
        if modern:
            context,model_sources=v5.project_assessment(context,sources,options)
            self.s.work.event('ASSESSMENT_SOURCE_PROJECTION',{'sources':len(sources),'spans':len(options),
                'source_hash':digest(sources),'evidence_hash':digest(options),'contract':contract})
        feedback = None
        value = None
        notes = ['ADOPTION_FALLBACK'] if fallback else []
        normalized = False
        for attempt in range(2):
            try:
                value = self.invoke(ASSESS_PROMPT+('\n'+v5.PROMPT if modern else ''), {**context,
                    'current_request': utterance,
                    'original_requirements': parts['INTENT']['payload'],
                    'issues': self.issues, 'sources': model_sources, 'evidence_options': options,
                    'saved_inventory': selection.get('saved_inventory', []),
                    'reference_leads': reference_leads(selection.get('reference_navigation', {})),
                    'gap_history': history,
                    'navigation_uncovered_issues': investigation.get('uncovered_issues', []),
                    'adoption_fallback': fallback,
                    'reentry_budget': getattr(self, 'reentry_counters', {}),
                    'user_fact_sources': fact_sources,
                    'repair_feedback': feedback}, schema,
                    'memory-assess' if not attempt else 'memory-assess-repair')
                if modern:
                    accepted, proposal=v5.prepare(value,schema,self.issues,options,fact_sources)
                    accepted=rr.bind_gaps(accepted,self.s.sources,rounds)
                    result=v5.materialize(accepted,options,self.issues,proposal)
                else:
                    value = cc.with_targets(value)
                    value, bound_refs = cc.bind_rule_evidence(value, options)
                    if bound_refs:self.s.work.event('COMPLETION_RULE_REFS_BOUND',{'changes':bound_refs,'assessment_hash':digest(value)})
                    problems = cc.assessment_errors(value, schema, self.issues)
                    for claim in value.get('claims',[]):
                        if claim.get('rule') is not None:problems.extend(cc.rule_errors(claim, fact_sources))
                    if problems:
                        raise ProposalError('; '.join(problems))
                    result = cc.materialize_assessment(value, options, self.issues)
                if result['claims']:
                    self.verify_claims(result['claims'], sources)
                break
            except (MemoryError, ProposalError, ValidationError) as exc:
                self.s.work.event('COMPLETION_ASSESSMENT_REJECTED', {
                    'attempt': attempt, 'error': str(exc), 'assessment_hash': digest(value)})
                if not attempt:
                    feedback = {'errors': str(exc), 'rejected_assessment': value}
                    continue
                # A second structural rejection becomes a weaker visible answer, not a failed request.
                candidate, changes = (None,'v5 source/structure contract unresolved') if modern else cc.normalize_assessment(value, schema, self.issues)
                if candidate is not None and any(cc.rule_errors(c, fact_sources) for c in candidate['claims'] if c.get('rule') is not None):
                    candidate, changes = None, 'unverified user fact or condition provenance'
                if candidate is not None:
                    try:
                        result = cc.materialize_assessment(candidate, options, self.issues)
                        self.verify_claims(result['claims'], sources)
                    except (MemoryError, ProposalError, ContractError) as verify_error:
                        candidate, changes = None, str(verify_error)
                if candidate is None:
                    self.s.work.event('COMPLETION_ASSESSMENT_UNNORMALIZABLE', {'reason': changes})
                    raise InvestigationPending('원문에 연결된 판단을 확정하지 못했습니다.', stage='ASSESS',
                        diagnostics={'schema_version': contract, 'stage': 'ASSESS',
                            'cause_codes': ['ASSESSMENT_CONTRACT_UNRESOLVED'],
                            'normalization': changes, 'resume_available': False}) from exc
                self.s.work.event('COMPLETION_ASSESSMENT_NORMALIZED', {
                    'changes': changes, 'rejected_hash': digest(value), 'assessment_hash': digest(candidate)})
                notes.append('ASSESSMENT_NORMALIZED'); normalized = True
                break

        actionable = [g for g in result['gaps'] if g['material'] and g['kind'] != 'MISSING_FACT']
        # Only gaps not raised in an earlier round may reopen investigation.
        if modern:raised={cc.gap_key(g) for g in actionable if not rr.may_reopen(g,investigation)}
        fresh = [] if normalized else [g for g in actionable if cc.gap_key(g) not in raised]
        repeated = [g for g in actionable if cc.gap_key(g) in raised]
        count = getattr(self, 'reentry_counters', {}).get('ASSESS_GAP_REENTRY', 0)
        limit = self.s.sources.profile['candidate_navigation']['assessment_reentry_limit']
        budget = self.s.work.budget()
        can_investigate = (budget['model_reserved'] < budget['model_limit'] - budget['finalization_reserve']
                           and self.s.context.remaining() > self.s.sources.profile['selection_time_reserve_seconds']
                           and (not modern or investigation.get('no_progress',0)<self.s.sources.profile['max_no_progress']))
        if fresh and count < limit and can_investigate:
            self.s.work.event('ASSESSMENT_GAP_REENTRY_PLANNED', {'fresh': [cc.gap_key(g) for g in fresh],
                'repeated': [cc.gap_key(g) for g in repeated], 'count': count, 'limit': limit})
            raise Reenter('SELECT', 'material assessment gap requires additional originals', {
                'reentry_kind': 'ASSESS_GAP_REENTRY', 'gaps': fresh, 'assessment': result,
                'investigation_state': selection['investigation_state']})
        stop_reason = selection.get('stop_reason')
        if fresh:
            stop_reason = 'ASSESSMENT_REENTRY_LIMIT' if count >= limit else 'INVESTIGATION_BUDGET'
        elif repeated and not normalized and any(closed.get(cc.gap_key(g)) is None for g in repeated):
            stop_reason = 'REPEATED_ASSESSMENT_GAP'
        if repeated:
            self.s.work.event('ASSESSMENT_GAP_REPEATED', {'repeated': [cc.gap_key(g) for g in repeated],
                'closed': {cc.gap_key(g): closed.get(cc.gap_key(g)) for g in repeated}})
        if not result['claims']:
            raise InvestigationPending('질문에 답할 근거가 충분히 확인되지 않았습니다.', stage='ASSESS',
                diagnostics={'schema_version': contract, 'stage': 'ASSESS',
                    'cause_codes': [stop_reason or 'NO_SUPPORTED_CLAIMS'],
                    'issues': [i['id'] for i in self.issues], 'resume_available': False})
        if actionable or result['disposition'] == 'NEEDS_INVESTIGATION':
            result['disposition'] = 'LIMITED_ANSWER'
        cc.refresh_limitations(result, self.issues, stop_reason, closed=closed, notes=notes)
        result.update(answer_coverage=ic.coverage(result), semantic_quality_certified=False)
        result['assessment_basis'] = basis
        self.s.work.event('ASSESSMENT_VALIDATED', {'basis_hash':signature, 'assessment':result})
        self.s.work.event('MEMORY_SEMANTIC_REVIEW_SKIPPED', {'stage': 'ASSESS', 'policy': 'disabled',
            'payload_sha256': digest(result), 'quality_certified': False})
        return result
