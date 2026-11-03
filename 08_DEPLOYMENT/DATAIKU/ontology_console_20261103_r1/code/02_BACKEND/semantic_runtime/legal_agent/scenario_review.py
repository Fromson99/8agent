"""Scenario-only input authority and bounded proposal checks.

This validates explicit conditions and stale numeric reuse, not arbitrary legal
semantics. Originals remain unchanged; old case facts are never current sources.
"""
from copy import deepcopy
import re
from .output_contract import OutputContractError, issue
from .errors import ContractError

FIELD = 'scenario_review'
TASK = '기준 사건의 조사 쟁점에 관하여 가정 적용 후 현재 사실과 규칙으로 판단한다. 변경 전 사건의 사실은 현재 사실이 아니다. 미확인 승인·예외는 미확인으로 남긴다.'
PROMPT = '''scenario_review에는 적용 판단 결과와 필요한 주장 연결을 작성한다. condition_results와 가정 식별 해시는 서버가 결속하며 모델이 재작성하지 않는다. 제시된 숫자 평가의 TRUE/FALSE/UNKNOWN/CONFLICT를 현재 조건으로 읽는다. 미확인 요건이 남으면 outcome=UNCONFIRMED로 둔다. baseline_history는 변경 전 기록이고 현재 사실이나 현재 적용 결론의 근거가 아니다. current_case가 있으면 그 facts/scenario, 그렇지 않으면 current_facts와 hypothetical_scenario의 변경값이 현재 사실·가정이다. 원문의 일반 규칙 설명과 가정 적용 판단을 구분한다. 이전 값을 현재 값처럼 재사용하지 않는다. RULE 가정에서는 원문 일반규칙은 원래 판본대로 인용하되, 현재 적용 설명은 changed_fields의 after로 판단한다. application_links에 모든 적용 설명 claim_id와 해당 condition_ids를 연결한다. 조건에 연결된 변경값은 적용 설명에 단위와 함께 명시한다. 원래 한도는 현재 적용 설명에 섞지 않고 GENERAL_RULE 원문 설명에 둔다.'''


def results(context):
    return [{'package_sha256': r['package_sha256'], 'node_id': r['node_id'], 'status': r['result']['status']}
            for r in context.get('evaluations', [])]


def attach(schema, context, *, typed=False, application_version=None):
    if not context: return schema
    if context.get('schema_version') not in ('scenario-context-v2','scenario-context-v3','scenario-context-v4'):
        raise ContractError('legacy hypothetical context requires a new bound branch')
    out = deepcopy(schema)
    out['properties'][FIELD] = {'type': 'object', 'additionalProperties': False,
        'properties': {'context_hash': {'const': context['content_sha256']},
            'condition_results': {'type': 'array', 'const': results(context), 'readOnly': True,
                'items': {'type': 'object', 'additionalProperties': False,
                'properties': {'package_sha256': {'type': 'string'}, 'node_id': {'type': 'string'},
                    'status': {'type': 'string', 'enum': ['TRUE','FALSE','UNKNOWN','CONFLICT','VALUE']}},
                'required': ['package_sha256','node_id','status']}},
            'outcome': {'type': 'string', 'enum': ['UNCONFIRMED','CONDITION_NOT_MET','CONDITIONS_MET']}},
        'required': ['context_hash','condition_results','outcome']}
    if context.get('kind')=='RULE':
        if 'changed_fields' not in context:raise ContractError('legacy rule assumption requires a new bound branch')
        shape=out['properties'][FIELD]
        shape['properties']['application_links']={'type':'array','items':{'type':'object','additionalProperties':False,
            'properties':{'claim_id':{'type':'string'},'condition_ids':{'type':'array','minItems':1,'uniqueItems':True,
                'items':{'type':'string','enum':list(condition_options(context))}}},'required':['claim_id','condition_ids']}}
        shape['required'].append('application_links')
    if typed:
        from .scenario_application import extend_shape
        from . import scenario_computation
        version=application_version or (scenario_computation.APPLICATION_VERSION if scenario_computation.enabled(context) else None)
        extend_shape(out['properties'][FIELD],context,version=version)
    out['required'].append(FIELD)
    return out


def task_input(data,state,rendered_question):
    """Use the original task and separate facts, never parse a rendered string."""
    if data.get('question')!=rendered_question:
        raise ContractError('scenario question is not the bound task/facts rendering')
    result=deepcopy(data);result['question']=state['task']
    return result


def project(data, context, facts):
    """Keep history visible but out of current request/fact authority."""
    out = deepcopy(data)
    from . import scenario_computation
    if scenario_computation.enabled(context):
        out['computed_gap_options']=scenario_computation.gap_options(context)
    history = {k: out.pop(k) for k in ('question','current_request','original_requirements',
               'previous_assessments','investigation_chain','selection_progress') if k in out}
    from .scenario_application import values as application_values
    displayed=deepcopy(context)
    if scenario_computation.enabled(context):
        # Approved execution metadata stays bound in server state. The model
        # reads the current values/results, not another executable-plan copy.
        displayed.pop('calculation_catalog')
    out.update(question=TASK, current_request=TASK, current_facts=deepcopy(facts),
        baseline_history={'authority':'HISTORICAL_ONLY_NOT_CURRENT_FACTS', 'records':history},
        hypothetical_scenario={**displayed, 'expected_condition_results':results(context),
            **({} if scenario_computation.enabled(context) else {'application_conditions':condition_options(context), 'application_values':application_values(context)})})
    return out


def numbers(text):
    # Delimited numbers only; no substring match (1500000 != 21500000).
    from decimal import Decimal
    if not isinstance(text,str):return set()
    return {Decimal(m.group().replace(',', '')) for m in re.finditer(r'(?<![0-9A-Za-z_.])[+-]?\d+(?:,\d{3})*(?:\.\d+)?(?![\d.])', text)}


def check(value, context, facts):
    problems = []
    def fail(code, path, expected=None): problems.append(issue(code, path, expected=expected))
    receipt = value.get(FIELD)
    expected = results(context)
    from jsonschema import Draft7Validator
    from . import scenario_application as typed_application
    typed=isinstance(receipt,dict) and receipt.get('version') in typed_application.SUPPORTED_VERSIONS
    shape=attach({'properties':{},'required':[]},context,typed=typed,application_version=receipt.get('version') if typed else None)['properties'][FIELD]
    # Historical receipts allow a different row order. Generation alone owns
    # the exact constant; saved receipts still pass the complete set check below.
    shape['properties']['condition_results'].pop('const')
    errors=list(Draft7Validator(shape).iter_errors(receipt))
    if errors:
        raise OutputContractError('가정 검토 필드의 형식을 확인하세요.',
            [issue('SCENARIO_REVIEW_SHAPE','/'+FIELD+'/'+ '/'.join(map(str,e.path))) for e in errors], category='SCENARIO_REVIEW_INVALID')
    if not isinstance(receipt, dict) or receipt.get('context_hash') != context['content_sha256']:
        fail('SCENARIO_CONTEXT_MISMATCH','/'+FIELD)
    else:
        actual = receipt.get('condition_results', [])
        key = lambda r: (r.get('package_sha256',''),r.get('node_id',''),r.get('status',''))
        if sorted(map(key,actual)) != sorted(map(key,expected)):
            fail('SCENARIO_CONDITION_CONFLICT','/'+FIELD+'/condition_results',
                 {'expected':expected,'observed':actual,'owner':'SERVER'})
        statuses = {r['status'] for r in expected}
        outcome = receipt.get('outcome')
        if outcome == 'CONDITIONS_MET' and (not statuses or statuses - {'TRUE','VALUE'} or context.get('unresolved') or any(r['result'].get('missing') for r in context.get('evaluations',[]))):
            fail('SCENARIO_UNRESOLVED_CONCLUSION','/'+FIELD+'/outcome')
        if outcome == 'CONDITION_NOT_MET' and 'FALSE' not in statuses:
            fail('SCENARIO_CONDITION_CONFLICT','/'+FIELD+'/outcome')
    if typed:
        problems.extend(typed_application.errors(value,context,facts))
    else:
        # Source quotes/normative rules can legitimately retain the real threshold.
        # Free application explanations must not silently reassert a replaced value.
        active = set().union(*(numbers(f['value']) for f in facts)) if facts else set()
        for typed in context['changes'].values(): active |= numbers(str(typed['value']))
        stale = set().union(*(numbers(r['value']) for r in context.get('superseded_facts', []))) if context.get('superseded_facts') else set()
        stale -= active
        for i, claim in enumerate(value.get('claims', [])):
            explanation = (claim.get('answer_content') or claim).get('explanation') or ''
            if numbers(explanation) & stale:
                fail('SCENARIO_SUPERSEDED_FACT','/claims/'+str(i)+'/explanation')
        if context.get('kind')=='RULE':
            problems.extend(application_errors(value,context))
    if problems:
        messages={
            'SCENARIO_APPLICATION_LINK':'가정 연결이 실제 적용 주장과 일치하지 않습니다.',
            'SCENARIO_APPLICATION_COVERAGE':'변경된 조건을 적용하는 실제 주장을 연결하세요. 일반 설명에는 별도 연결이 필요하지 않습니다.',
            'SCENARIO_SUPERSEDED_RULE':'현재 적용 설명에 이전 규칙값이 있습니다. 현재값으로 판단하고 변경 전후 비교는 comparison_text에 보존하세요.',
            'SCENARIO_SUPERSEDED_FACT':'현재 적용 설명에 이전 사실값이 있습니다. 현재값으로 판단하고 변경 전후 비교는 comparison_text에 보존하세요.',
            'SCENARIO_NUMERIC_LITERAL':'설명에 연결되지 않은 금액 또는 잘못된 단위가 있습니다.',
            'SCENARIO_COMPARISON_BINDING':'변경 전후 비교의 과거 참조와 설명을 확인하세요.',
        }
        if receipt.get('version') == typed_application.SERVER_VERSION:
            for code in ('SCENARIO_SUPERSEDED_RULE','SCENARIO_SUPERSEDED_FACT'):
                messages[code]='현재 적용 설명에 이전 값이 있습니다. 변경 전후 수치는 서버가 별도로 표시하므로, 설명은 현재 조건과 원문의 적용 범위·예외에 집중하세요.'
        message=' '.join(dict.fromkeys(messages.get(p['code'],'가정 검토의 해당 필드와 조건을 확인하세요.') for p in problems))
        raise OutputContractError(message, problems, category='SCENARIO_REVIEW_INVALID')
    return deepcopy(receipt)


def core(value, schema, context, facts):
    if not context: return value, schema, None
    receipt = check(value, context, facts)
    out = deepcopy(value); out.pop(FIELD)
    shape = deepcopy(schema); shape['properties'].pop(FIELD); shape['required'].remove(FIELD)
    return out, shape, receipt


def verify_saved(assessment, context, facts):
    from . import scenario_computation
    if scenario_computation.enabled(context):
        scenario_computation.verify_saved(assessment,context)
    if not assessment.get('claims') and assessment.get('model_proposal',{}).get('review_status') == 'INCOMPLETE':
        return
    from . import scenario_application as typed_application
    receipt=assessment.get('model_proposal',{}).get('scenario_review')
    expected_version=assessment.get('assessment_basis',{}).get('scenario_application_version')
    if expected_version in typed_application.SUPPORTED_VERSIONS and (receipt or {}).get('version')!=expected_version:
        raise ContractError('saved typed scenario receipt missing or downgraded')
    check({'scenario_review':receipt,'claims':assessment.get('claims',[])},context,facts)
    if (receipt or {}).get('version') in (typed_application.LEGACY_VERSION,typed_application.VERSION) and assessment.get('scenario_application_display')!=typed_application.display(receipt,context):
        raise ContractError('saved typed scenario display changed')


def condition_options(context):
    return {'scenario-condition:'+str(i):{'package_sha256':r['package_sha256'],'node_id':r['node_id'],
        'status':r['result']['status'],'changed_inputs':{k:deepcopy(context['changed_fields'][k])
            for k in r.get('input_fields',[]) if k in context.get('changed_fields',{})}}
        for i,r in enumerate(context.get('evaluations',[]),1)}


def application_errors(value,context):
    """Explicit claim/condition links and changed literals, never prose rewriting.

    These are mechanical consistency checks, not a natural-language truth oracle.
    Source GENERAL_RULE content remains bound to the real published rule.
    """
    options=condition_options(context);problems=[]
    def fail(code,path,expected=None):problems.append(issue(code,path,expected=expected))
    claims={c['claim_id']:c.get('answer_content') or c for c in value.get('claims',[])}
    applications={k:c for k,c in claims.items() if c.get('explanation') or (c.get('rule') or {}).get('kind')=='CASE_APPLICATION'}
    links=value[FIELD].get('application_links',[]);seen=set();used=set()
    for i,link in enumerate(links):
        cid=link['claim_id'];path='/'+FIELD+'/application_links/'+str(i)
        if cid not in applications or cid in seen:
            fail('SCENARIO_APPLICATION_LINK',path,{'claim_id':cid,'allowed_claim_ids':list(applications),
                 'already_linked':sorted(seen)});continue
        seen.add(cid);conditions=link['condition_ids'];used.update(conditions)
        content=applications[cid];text=content.get('explanation') or ''
        # CASE_APPLICATION conclusions are current assertions; original quotes
        # and GENERAL_RULE norms are separately verified by the source contracts.
        rule=content.get('rule') or {}
        if rule.get('kind')=='CASE_APPLICATION':
            text+=' '+str(rule.get('conclusion',''))+' '+' '.join(n.get('text','') for n in rule.get('norms',[]))
        for condition in conditions:
            for field_name,field in options[condition]['changed_inputs'].items():
                after=field['after'];before=field['before']
                expected_binding={'claim_id':cid,'condition_id':condition,'field':field_name,
                                  'current':deepcopy(after),'previous':deepcopy(before),
                                  'claim_path':'/claims/'+cid}
                if after['type'] in ('money','decimal','ratio','duration'):
                    if not numbers(str(after['value'])) <= numbers(text):fail('SCENARIO_CHANGED_VALUE_MISSING',path,expected_binding)
                    old=numbers(str(before['value'])) if before else set()
                    if (old-numbers(str(after['value']))) & numbers(text):fail('SCENARIO_SUPERSEDED_RULE',path,expected_binding)
                elif after['type'] in ('text','date') and str(after['value']) not in text:fail('SCENARIO_CHANGED_VALUE_MISSING',path,expected_binding)
    if seen!=set(applications):fail('SCENARIO_APPLICATION_LINK','/claims',{
        'missing_claim_ids':sorted(set(applications)-seen),'allowed_condition_ids':list(options)})
    affected={k for k,v in options.items() if v['changed_inputs']}
    if value.get('claims') and not affected<=used:fail('SCENARIO_APPLICATION_COVERAGE','/'+FIELD+'/application_links')
    # A claim cannot evade old-rule detection by linking only an unchanged condition.
    stale=set()
    for f in context['changed_fields'].values():
        if f['before'] and f['after']['type'] in ('money','decimal','ratio','duration'):
            stale |= numbers(str(f['before']['value']))-numbers(str(f['after']['value']))
    for cid,c in applications.items():
        if numbers(c.get('explanation') or '') & stale:fail('SCENARIO_SUPERSEDED_RULE','/claims/'+cid+'/explanation')
    return problems
