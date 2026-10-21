"""Native seven-stage completion behavior; no alternate runner or judge."""
from copy import deepcopy
from jsonschema import ValidationError
from ..contracts import digest
from . import completion_contracts as cc
from . import completion_v5 as v5, request_repair as rr
from . import investigation_contracts as ic
from . import investigation_chain as trail
from . import output_contract as output
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


MODERN_ASSESS_PROMPT = """evidence_options의 id/text는 실제 읽은 원문이고 sources의 evidence_refs가 문서·조문과 연결한다. 위치·해시·채택 상태는 서버가 관리한다. 준용 대상도 해당 원문 text가 있으면 그 실제 내용을 답에 사용하며, 이미 제공된 text를 원문 미제공이라고 쓰지 않는다.
제공된 원문 evidence_options로 현재 질문에 직접 답한다. 각 쟁점의 첫 claim은 직접 결론으로 쓰고 요건·예외·차이는 한 번만 설명한다.
일반 규칙은 GENERAL_RULE과 빈 fact_refs로 작성한다. 특정 사건 적용은 CASE_APPLICATION과 실제 제공된 사용자 사실만 쓴다. 질문 문장 자체를 사실 충족의 증거로 쓰지 않는다. 법령으로 사실 충족을 증명하지 않는다.
질문이 일반적인 분류·산식·조건을 묻는다면 사건 적용으로 바꾸지 않는다. 사용자 질문의 가정된 주체는 설명 범위이며 특정 사건 사실을 입증하지 않는다.
분류는 본문과 현재 읽은 예외를 함께 대조해 제외되는 범위와 실제 적용될 범위를 명확히 설명한다. 예외를 읽었는데도 포괄적 일반 규칙만 결론으로 반복하지 않는다. 산식·방법 질문은 준용 근거 이름만 말하지 말고 실제 계산 구조를 설명하며, 그 원문을 못 읽었으면 필요한 조사 gap을 남긴다.
주체·대상·적용 범위·예외를 보존한다. 일부 요건 충족이나 금지 제외만으로 전체 적법성을 단정하지 않는다.
다른 항에 붙은 단서를 전체 조문에 확대하지 않는다. 일반 방법 질문에는 기본 규칙과 특례 방법을 구분하며, 특례만으로 전체 질문에 답하지 않는다.
서로 다른 요건·효과의 규칙은 별도 claim으로 표현한다. 조건·norms·exceptions를 먼저 작성하고 그 범위에 맞는 action 결론을 마지막에 작성한다. 문구가 다른 취득방법이라는 이유만으로 두 규칙을 배타적이라고 추론하지 않는다.
특정 의무의 제외 규정은 그 의무에 대한 제외다. 재량적 PERMISSION이나 전체 행위의 허용으로 바꾸지 않는다. 예외의 성립에 다른 독립 규칙의 요건까지 충족해야 한다는 조건을 추가하지 않는다. 모의 예: A가 X를 제외하고 B가 Y일 때 적용되면, X는 A에서 제외되며 B는 Y 충족 여부로 별도 판단한다.
질문의 넓은 실무 용어가 특정 법정 자격과 같은 뜻인지 단정하지 않는다. 해당 자격이면 어떤 규칙인지, 아니라면 어떤 조건을 확인해야 하는지 구분해 답한다. ‘각각’이 가리키는 문장 속 대상 범주를 개별 구성원 전체로 확대하지 않는다.
특정 항·호만 준용된 경우 그 항·호의 실제 내용만 연결한다. 인접한 항의 분모·산식·정의나 다른 제도의 적용 범위를 함께 끌어오려면 별도 근거가 필요하다. 한정 준용 범위 밖 조항을 읽지 않았다는 사실만으로 material gap을 만들지 않는다.
필요한 적용 조건과 효과가 원문에 완결되어 있으면 확인된 범위로 답한다. 아직 알지 못하는 다른 예외가 있을지도 모른다는 추측은 원문 부족의 근거가 아니다. 구체적으로 미확인인 요청 사항이나 원문이 명시한 필요한 위임 범위만 gap에 쓴다. 같은 claim을 중복 생성하지 않는다. 인용은 제공된 ID만 선택한다.
issue_assessments에는 해당 쟁점의 충족 상태만 선택한다. disposition과 쟁점별 진단 reason은 서버가 조립한다. 상태 선택의 내부 검토나 반복 설명은 쓰지 않는다.
요청에 필요한 미확인 내용만 gaps에 남긴다. gap reason은 부족한 내용 한 문장이다. 법령 원문 미확인은 사용자 사실 부족이 아니다.
일반 규칙 질문에는 특정 사건 사실을 요구하지 않는다. 요청에 필요 없는 참조는 조사하지 않아도 된다.
같은 부족은 previous_gap_key로 연결하고 material=true를 보존한다. 조사 재개 가능 여부와 최종 상태는 서버가 결정한다.
이미 읽은 원문을 미확보라고 쓰지 않는다. 현재 sources와 evidence_options가 실제 근거이며 목록·미리보기·과거 답변은 근거가 아니다.
법률 내용은 claim, 부족은 gap에 한 번씩 쓴다. repair_feedback의 구체 오류만 수정한다."""


CONDITION_GUIDANCE = """출력 전용 condition_tree는 null 또는 {"leaves":[{"text":"조건 A","evidence_refs":["S1"]},{"text":"조건 B","evidence_refs":["S2"]}],"expression":"ANY(1,2)"}다.
leaves에 조건을 한 번씩 쓰고 expression은 1부터 시작한 조건 위치로 관계만 표시한다. 하나는 1, 모두는 ALL(1,2), 하나 이상은 ANY(1,2), 관계 미확인은 UNKNOWN(1,2), 중첩은 ALL(1,ANY(2,3))이다.
모든 조건을 관계식에 포함한다. 최대 중첩 3단계, 그룹마다 1~8개 자식이다. 서버는 조건·원문 ID·ALL/ANY/UNKNOWN 관계를 그대로 복원한다.
GENERAL_RULE의 fact_refs 및 gap 종류에 따라 확정되는 고정값은 시스템이 조립한다. 법률 내용과 실제 부족 종류는 직접 판단한다.
JSON은 들여쓰기·빈 줄 없이 간결하게 출력한다."""


def restore_condition(value):
    """Parse an explicit bounded relation; never infer a missing connective."""
    if value is None:return None
    import re
    leaves=value['leaves'];expression=value['expression']
    if not 1<=len(leaves)<=585 or len(expression)>4096:
        raise ProposalError('condition leaves/expression exceeds bounded contract')
    tokens=[];cursor=0
    for match in re.finditer(r'ALL|ANY|UNKNOWN|[0-9]+|[(),]',expression):
        if expression[cursor:match.start()].strip():
            raise ProposalError(f'condition expression invalid token at character {cursor}')
        tokens.append(match.group());cursor=match.end()
    if expression[cursor:].strip():raise ProposalError(f'condition expression invalid token at character {cursor}')
    pos=0;used=set()
    def parse(depth):
        nonlocal pos
        if depth>3:raise ProposalError('condition expression exceeds canonical depth 3')
        if pos>=len(tokens):raise ProposalError('condition expression missing operand')
        token=tokens[pos];pos+=1
        if token.isdigit():
            index=int(token)
            if not 1<=index<=len(leaves):raise ProposalError(f'condition leaf {index} outside 1..{len(leaves)}')
            used.add(index)
            return {'mode':'LEAF',**deepcopy(leaves[index-1])}
        if token not in ('ALL','ANY','UNKNOWN') or pos>=len(tokens) or tokens[pos]!='(':
            raise ProposalError(f'condition expression expected leaf or operator at token {pos}')
        pos+=1;children=[parse(depth+1)]
        while pos<len(tokens) and tokens[pos]==',':
            pos+=1
            if len(children)>=8:raise ProposalError('condition group exceeds 8 children')
            children.append(parse(depth+1))
        if pos>=len(tokens) or tokens[pos]!=')':raise ProposalError('condition expression missing closing parenthesis')
        pos+=1
        return {'mode':token,'children':children}
    tree=parse(0)
    if pos!=len(tokens):raise ProposalError('condition expression has trailing tokens')
    if used!=set(range(1,len(leaves)+1)):raise ProposalError('condition expression must include every provided leaf')
    return tree


def assessment_fact_sources(utterance,state,*,modern):
    # A request's wording is scope, not automatically an admitted case fact.
    facts=state.get('facts',[])
    if modern and not facts:return []
    return [{'id':'U0','text':utterance}]+[{'id':'U'+str(n),'text':str(f.get('value',''))} for n,f in enumerate(facts,1)]


def assessment_projection(schema):
    """Same semantic tree and model coverage; host owns control/structure fields."""
    wire=deepcopy(schema)
    wire['properties'].pop('disposition');wire['required'].remove('disposition')
    row=wire['properties']['issue_assessments']['items']
    row['properties'].pop('reason');row['required'].remove('reason')
    def leaf(node):
        if isinstance(node,dict):
            if node.get('properties',{}).get('mode',{}).get('const')=='LEAF':return deepcopy(node)
            for v in node.values():
                found=leaf(v)
                if found:return found
        elif isinstance(node,list):
            for v in node:
                found=leaf(v)
                if found:return found
    def visit(node):
        if isinstance(node,list):
            for v in node:visit(v)
        elif isinstance(node,dict):
            for v in list(node.values()):visit(v)
            props=node.get('properties',{})
            if {'kind','material_id','suggested_action','missing_target'}<=set(props):
                branches=[]
                for kind in props['kind']['enum']:
                    branch=deepcopy(node);bp=branch['properties'];bp['kind']={'const':kind}
                    if kind=='MISSING_FACT':
                        bp['material_id']={'const':None};bp['missing_target']={'const':''}
                        bp['suggested_action']={'const':'REQUEST_FACT'}
                    else:bp['suggested_action']['enum']=[a for a in bp['suggested_action']['enum'] if a!='REQUEST_FACT']
                    branches.append(branch)
                node['anyOf']=branches
            if 'condition_tree' not in props or 'fact_refs' not in props:return
            atomic=leaf(props['condition_tree'])
            if atomic is None:raise ContractError('condition wire missing canonical leaf contract')
            atomic['properties'].pop('mode');atomic['required'].remove('mode')
            props['condition_tree']={'anyOf':[{'type':'null'},cc.obj({
                'leaves':{'type':'array','minItems':1,'maxItems':585,'items':atomic},
                'expression':{'type':'string','minLength':1}})]}
            node['properties']={k:props[k] for k in props if k!='action'}
            node['properties']['action']=props['action']
            general=deepcopy(node);general['properties']['kind']={'const':'GENERAL_RULE'};general['properties']['fact_refs']['maxItems']=0
            application=deepcopy(node);application['properties']['kind']={'const':'CASE_APPLICATION'}
            node['anyOf']=[general] if node['properties']['fact_refs'].get('maxItems')==0 else [general,application]
    visit(wire)
    def decode(raw):
        output.validate_shape(raw,wire)
        value=deepcopy(raw)
        for claim in value['claims']:
            if claim.get('rule') is not None:claim['rule']['condition_tree']=restore_condition(claim['rule']['condition_tree'])
        for row in value['issue_assessments']:
            claims=sum(row['issue_id'] in c['issue_refs'] for c in value['claims'])
            gaps=sum(g['issue_id']==row['issue_id'] for g in value['gaps'])
            row['reason']=f"판단 상태 {row['status']}; 근거 주장 {claims}개, 미확인 {gaps}개."
        value['disposition']=('NEEDS_INVESTIGATION' if any(g['material'] and g['kind']!='MISSING_FACT' for g in value['gaps']) else
            'ANSWER' if all(r['status']=='COVERED' for r in value['issue_assessments']) else 'LIMITED_ANSWER')
        output.validate_shape(value,schema)
        return value
    def expand(raw):
        try:return decode(raw)
        except (ProposalError,ValidationError) as exc:
            exc.proposal=deepcopy(raw)
            raise
    return wire,expand


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


INTENT_PROVENANCE_PROMPT = ('question/current_request는 이번 사용자 발언 원문이며 request_quote와 background_quotes의 유일한 인용 출처다. '
    'resolved_goal_context와 investigation_chain은 이전 조사와 대명사의 대상을 이해하는 문맥이다. '
    '그 문구를 이번 사용자가 발언한 배경이나 사실로 복사하지 않는다. '
    '이번 발언에 별도 업무 배경이 없으면 background_quotes=[]다. '
    '쟁점 question과 subject에는 이전 문맥을 해소한 대상을 설명할 수 있지만 request_quote는 이번 발언에서 그대로 선택한다.')


def intent_input(data, utterance):
    """Preserve goal context while giving current-utterance quotes one source."""
    view={**data,'question':utterance,'current_request':utterance}
    if data.get('question') and data['question']!=utterance:
        view['resolved_goal_context']={'text':data['question'],
            'provenance':'resolved_goal_not_current_utterance','quote_source':False}
    return view


class CompletionExecution:
    def completion_stage(self, stage, state, parts, utterance, format, data):
        profile=getattr(self.s.sources,'profile',{})
        modern=rr.enabled(profile)
        contract=cc.version(profile)
        from . import narrative_answer as narrative
        from .workflow_execution import task_context, task_instructions
        task=task_context()
        rich = narrative.enabled(profile) and task is None
        from . import completion_v6,completion_v7,completion_v8
        content_impl=completion_v8 if contract==cc.V8 else completion_v7 if contract==cc.V7 else completion_v6 if contract==cc.V6 else v5
        if stage == 'INTENT':
            from .memory_rag import INTENT
            wire = ic.intent_schema(INTENT)
            if modern:wire=v5.intent_schema(wire)
            from .request_entry import consume
            result = consume(self,state,utterance)
            def verify_intent(value):
                output.validate_shape(value,wire)
                if len({i['id'] for i in value['issues']}) != len(value['issues']):
                    raise output.OutputContractError('duplicate request issue',
                        [output.issue('DUPLICATE_ISSUE_ID','/issues')],category='DECISION_CONFLICT')
                if modern:
                    try:v5.verify_intent(value,utterance)
                    except MemoryError as exc:
                        raise output.OutputContractError(str(exc),
                            [output.issue('REQUEST_SCOPE_CONFLICT','/issues')],category='DECISION_CONFLICT') from exc
            if result is None:
                def propose(payload,attempt):
                    return self.invoke(INTENT_PROMPT+('\n'+v5.SCOPE_PROMPT+'\n'+INTENT_PROVENANCE_PROMPT if modern else ''),payload,wire,
                        'memory-intent' if not attempt else 'memory-intent-repair')
                result=output.bounded_decision(self.s.work,'request-intent',
                    intent_input(data,utterance) if modern else {**data,'current_request':utterance},wire,propose,verify_intent,
                    identity={'state':state,'request':utterance,'binding':self.host.binding})
            else:verify_intent(result)
            return {**result, 'completion_contract': contract,
                    'request_text': utterance, 'request_hash': digest(utterance)}
        read = parts['READ']['payload']
        self.host.verify(read)
        selection = parts['SELECT']['payload']
        selected = set(selection['final_ids'])
        sources = [s for s in self.selected_originals(parts) if s['source_id'] in selected]
        if stage == 'COMPOSE':
            assessment = parts['ASSESS']['payload']
            if assessment.get('source_excerpt_reply'):
                cc.verify_source_excerpt_reply(assessment, sources)
                rich = False  # No accepted judgment to paraphrase; publish exact originals.
            else:
                self.verify_claims(assessment['claims'], sources)
            # The source-backed judgment remains immutable; presentation is separate.
            if rich:
                wire = narrative.input_data(utterance, assessment, sources, format)
                def write(payload, attempt):
                    return self.invoke(narrative.PROMPT, payload,
                        narrative.schema(wire['answer_claim_ids']),
                        narrative.PHASE if not attempt else 'memory-compose-repair')
                def verify_presentation(value):
                    output.validate_shape(value,narrative.schema(wire['answer_claim_ids']))
                    narrative.plan(assessment,value)
                from .answer_stream import current_sink
                value = output.bounded_decision(self.s.work, 'composition', wire,
                    narrative.schema(wire['answer_claim_ids']),write,verify_presentation,
                    identity={'assessment_hash':digest(assessment),'wire':wire},
                    can_repair=lambda:not (current_sink() and getattr(current_sink(),'started',False)))
                plan = narrative.plan(assessment, value)
            else:
                plan = cc.default_plan(assessment, format, selection.get('issues'))
            result = cc.compose(assessment, plan)
            cc.verify_composition(assessment, result)
            if rich:
                from .answer_stream import current_sink
                sink = current_sink()
                if sink is not None and getattr(sink, 'started', False):
                    emitted = getattr(sink, 'text', '')
                    if not result['text'].startswith(emitted):
                        raise ContractError('final narrative differs from streamed paragraphs')
                    if result['text'][len(emitted):]:sink(result['text'][len(emitted):])
            self.s.work.event('COMPOSITION_RENDERED', {'contract': result['completion_contract'],
                'assessment_hash': digest(assessment), 'plan': plan,
                'text_hash': digest(result['text']), 'model_call': rich,
                'presentation': narrative.VERSION if rich else 'structured'})
            self.s.work.event('FINAL_REVIEW_SKIPPED', {'stage': stage, 'policy': 'disabled',
                'structural_render_verified': True, 'claim_review_status': 'UNREVIEWED',
                'quality_certified': False})
            return result

        self.issues = selection['issues']
        self.saved_material_ids = [r['material_id'] for r in selection.get('saved_inventory', [])]
        options = cc.evidence_options(sources)
        fact_sources = assessment_fact_sources(utterance,state,modern=modern)
        schema = cc.assessment_schema(self.issues, self.saved_material_ids, options,
            contract=cc.CONTRACT, facts=fact_sources)
        history = gap_history(selection)
        if modern:
            schema=content_impl.assessment_schema(self.issues,self.saved_material_ids,options,fact_sources,
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
        basis = {'output_contract_version':output.VERSION,'schema_hash':digest(schema),'contract':contract,'answer_presentation':profile.get('answer_presentation','structured'),'request_hash':digest(utterance),'state_hash':digest(state),
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
                if cached.get('source_excerpt_reply'):
                    cc.verify_source_excerpt_reply(cached, sources)
                else:
                    self.verify_claims(cached['claims'], sources)
                self.s.work.event('ASSESSMENT_REUSED', {'basis_hash':signature})
                return deepcopy(cached)
        model_sources=sources
        model_options=options
        if modern:
            context,model_sources=v5.project_assessment(context,sources,options)
            self.s.work.event('ASSESSMENT_SOURCE_PROJECTION',{'sources':len(sources),'spans':len(options),
                'source_hash':digest(sources),'evidence_hash':digest(options),'contract':contract})
        feedback = None
        value = None
        notes = ['ADOPTION_FALLBACK'] if fallback else []
        normalized = False
        decision_journal = output.DecisionJournal(self.s.work,'assessment',basis,schema)
        prior = decision_journal.state()
        start = prior['attempt'] if prior and prior['status']=='ACCEPTED' else (
            prior['attempt']+1 if prior and prior['status']=='REJECTED' else 0)
        if start>1 or prior and prior['status']=='REJECTED' and not prior.get('repairable'):
            raise InvestigationPending('같은 판단의 수정 한도를 소진했습니다.',stage='ASSESS',
                diagnostics={'cause_codes':['ASSESSMENT_CONTRACT_UNRESOLVED'],'resume_available':False})
        if prior and prior['status']=='REJECTED':
            feedback={'errors':prior['error'],'validation':prior['failure'],'rejected_assessment':prior.get('proposal')}
        from .law_candidates import answer_first
        answer_policy = ('\n현재 사용자 질문에 직접 답하는 검증 가능한 주장만 작성한다. 확보한 일반 원칙·수치·조건으로 답할 수 있으면 그 범위를 먼저 답한다. 모든 가능한 예외를 조사한 것으로 말하지 않는다. 실제로 부족한 사항은 gaps에 그대로 남긴다. 질문에 답하는 주장이 하나라도 있으면 추가 조사는 자동 실행하지 않고 사용자의 후속 질문으로 이어진다. 현재 질문에 답할 주장이 전혀 없으면 claims를 비우고 구체적으로 필요한 원문만 요청한다. 구체적인 조건·예외·대상을 묻는 질문에서 다른 조문이나 세칙에 정한다는 위치 안내만 확보했다면 그 구체 내용까지 답한 것으로 보지 않는다. 그 밖에 현재 질문에 직접 답하는 근거도 없으면 claims=[]로 두고 실제 위임 대상 원문을 요청한다. 후속 질문은 그 질문의 요청 범위를 기준으로 판단하고 이전 질문의 답만 반복하지 않는다.' if modern and answer_first(self.s.sources.profile) else '')
        generation_schema,expand_assessment=assessment_projection(schema) if modern else (schema,lambda v:v)
        for attempt in range(start,2):
            cached = decision_journal.reserve(attempt)
            value = None
            try:
                value = deepcopy(cached['value']) if cached else expand_assessment(self.invoke((MODERN_ASSESS_PROMPT if modern else ASSESS_PROMPT)+task_instructions()+('\n'+content_impl.PROMPT if modern else '')+('\n'+narrative.ASSESS_GUIDANCE if rich else '')+('\n'+CONDITION_GUIDANCE if modern else '')+answer_policy, {**context,
                    'current_request': utterance,
                    **({'workflow_task':task} if task else {}),
                    'original_requirements': parts['INTENT']['payload'],
                    'issues': self.issues, 'sources': model_sources, 'evidence_options': model_options,
                    'saved_inventory': selection.get('saved_inventory', []),
                    'reference_leads': reference_leads(selection.get('reference_navigation', {})),
                    'gap_history': history,
                    'navigation_uncovered_issues': investigation.get('uncovered_issues', []),
                    'adoption_fallback': fallback,
                    'reentry_budget': getattr(self, 'reentry_counters', {}),
                    'user_fact_sources': fact_sources,
                    'repair_feedback': feedback}, generation_schema,
                    'memory-assess' if not attempt else 'memory-assess-repair'))
                if modern:
                    accepted, proposal=content_impl.prepare(value,schema,self.issues,options,fact_sources)
                    accepted=rr.bind_gaps(accepted,self.s.sources,rounds)
                    result=content_impl.materialize(accepted,options,self.issues,proposal)
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
                    try:self.verify_claims(result['claims'], sources)
                    except MemoryError as exc:
                        raise output.OutputContractError(str(exc),[output.issue('CLAIM_EVIDENCE_INVALID','/claims')],
                            category='EVIDENCE_CONTRACT_INVALID') from exc
                if not cached:decision_journal.accept(attempt,value)
                break
            except (ProposalError, ValidationError) as exc:
                value=getattr(exc,'proposal',value)
                if not cached:decision_journal.reject(attempt,exc,value)
                self.s.work.event('COMPLETION_ASSESSMENT_REJECTED', {
                    'attempt': attempt, 'error': str(exc), 'assessment_hash': digest(value)})
                if not attempt and output.repairable(exc):
                    feedback = {'errors': str(exc), 'validation':output.diagnostics(exc), 'rejected_assessment': value}
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
        from .law_candidates import answer_first
        defer_to_user = modern and answer_first(self.s.sources.profile) and bool(result['claims'])
        if fresh and not defer_to_user and count < limit and can_investigate:
            self.s.work.event('ASSESSMENT_GAP_REENTRY_PLANNED', {'fresh': [cc.gap_key(g) for g in fresh],
                'repeated': [cc.gap_key(g) for g in repeated], 'count': count, 'limit': limit})
            raise Reenter('SELECT', 'material assessment gap requires additional originals', {
                'reentry_kind': 'ASSESS_GAP_REENTRY', 'gaps': fresh, 'assessment': result,
                'investigation_state': selection['investigation_state']})
        stop_reason = selection.get('stop_reason')
        if fresh and defer_to_user:
            stop_reason = 'USER_FOLLOWUP_RESEARCH'
            self.s.work.event('ASSESSMENT_RESEARCH_DEFERRED_TO_USER', {
                'gaps': [cc.gap_key(g) for g in fresh], 'supported_claim_ids': [c['claim_id'] for c in result['claims']],
                'reason': 'publish supported current-question scope with unresolved limitations'})
        elif fresh:
            stop_reason = 'ASSESSMENT_REENTRY_LIMIT' if count >= limit else 'INVESTIGATION_BUDGET'
        elif repeated and not normalized and any(closed.get(cc.gap_key(g)) is None for g in repeated):
            stop_reason = 'REPEATED_ASSESSMENT_GAP'
        if repeated:
            self.s.work.event('ASSESSMENT_GAP_REPEATED', {'repeated': [cc.gap_key(g) for g in repeated],
                'closed': {cc.gap_key(g): closed.get(cc.gap_key(g)) for g in repeated}})
        if not result['claims'] and not options:
            raise InvestigationPending('질문에 답할 근거가 충분히 확인되지 않았습니다.', stage='ASSESS',
                diagnostics={'schema_version': contract, 'stage': 'ASSESS',
                    'cause_codes': [stop_reason or 'NO_SUPPORTED_CLAIMS'],
                    'issues': [i['id'] for i in self.issues], 'resume_available': False})
        if not result['claims']:
            result['source_excerpt_reply'] = cc.source_excerpt_reply(sources)
            result['disposition'] = 'LIMITED_ANSWER'
            stop_reason = stop_reason or 'NO_SUPPORTED_CLAIMS'
            self.s.work.event('ASSESSMENT_SOURCE_EXCERPT_REPLY', {
                'schema_version': cc.SOURCE_REPLY_CONTRACT, 'stop_reason': stop_reason,
                'source_ids': [s['source_id'] for s in sources],
                'legal_conclusion_confirmed': False, 'model_call': False})
        if actionable or result['disposition'] == 'NEEDS_INVESTIGATION':
            result['disposition'] = 'LIMITED_ANSWER'
        cc.refresh_limitations(result, self.issues, stop_reason, closed=closed, notes=notes)
        result.update(answer_coverage=ic.coverage(result), semantic_quality_certified=False)
        result['assessment_basis'] = basis
        self.s.work.event('ASSESSMENT_VALIDATED', {'basis_hash':signature, 'assessment':result})
        self.s.work.event('MEMORY_SEMANTIC_REVIEW_SKIPPED', {'stage': 'ASSESS', 'policy': 'disabled',
            'payload_sha256': digest(result), 'quality_certified': False})
        return result


def assessment_original_view(sources, options):
    """Host owns span/receipt verification; models receive exact originals once."""
    headers = [{k:deepcopy(row[k]) for k in ('source_id','document_name','heading',
                'evidence_refs','article_complete','read_scopes') if k in row} for row in sources]
    originals = [{'id':row['id'],'text':row['text']} for row in options]
    return headers, originals
