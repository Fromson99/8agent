"""Typed current application and historical comparison, independent of prose style.

The server owns values and predicate results. The model selects their roles and
claim links. Neither this contract nor a numeric predicate certifies legal truth.
"""
from copy import deepcopy
from decimal import Decimal
import re
from .errors import ContractError
from .output_contract import issue

VERSION='scenario-application-v3'
LEGACY_VERSION='scenario-application-v2'
SERVER_VERSION='scenario-application-v4'
SUPPORTED_VERSIONS=(LEGACY_VERSION,VERSION,SERVER_VERSION)
PROMPT='''가정 검토에서는 변경된 조건을 실제로 적용하는 주장만 application_links에 연결한다. 일반 원문 규칙·변경과 무관한 승인 미확인·예외 비적용 설명에는 별도 가정 연결이 필요하지 않다. 변경된 각 조건에는 최소 하나의 실제 적용 주장이 있어야 한다. application_values의 CURRENT 값은 applied_value_refs로 선택한다. 현재 적용 explanation과 CASE_APPLICATION 결론에는 현재 값만 쓴다. 비교가 필요하면 같은 필드의 HISTORICAL 참조를 comparison_value_refs에 선택하고, 변경 전후를 설명하는 문장 전체를 선택 필드 comparison_text에 둔다. comparison_text는 현재 적용 결론과 구분하여 표시된다. 비교 참조를 붙여도 현재 적용 설명에 이전 한도를 쓰면 안 된다. GENERAL_RULE의 원문과 원래 한도는 그대로 보존한다. 값·서버 계산표를 다시 쓰거나 설명 길이를 채울 필요는 없다. 245만 원과 2,450,000원은 같은 금액이다. 승인·예외 미확인은 계속 미확인이며 숫자 TRUE가 최종 허용을 뜻하지 않는다.'''
MONEY=re.compile(r'(?<![0-9A-Za-z_.,+\-])[+-]?[0-9][0-9,.]*\s*(?:천|만|억)?\s*(?:KRW|원)(?![A-Za-z])')


def inputs(explanation,state,comparison):
    from . import scenario_facts
    fields={}
    for bundle in explanation['ontology']['bundles']:
        plan=(bundle.get('assembly') or {}).get('evaluation_plan')
        for name,field in (plan or {}).get('spec',{}).get('fields',{}).items():
            if name in fields and fields[name]!=field:raise ContractError('scenario input field conflict')
            fields[name]=field
    _,facts,_=scenario_facts.bind(state,fields,comparison['fact_bindings'])
    values={name:deepcopy(field['baseline']) for name,field in fields.items() if field['kind']=='RULE'}
    values.update(facts);values.update(deepcopy(comparison['changes']))
    return values


def values(context):
    result={}
    for number,(name,row) in enumerate(sorted(context.get('changed_fields',{}).items()),1):
        result['scenario-value:'+str(number)+':current']={'field':name,'role':'CURRENT','typed':deepcopy(row['after'])}
        if row.get('before') is not None:
            result['scenario-value:'+str(number)+':before']={'field':name,'role':'HISTORICAL','typed':deepcopy(row['before'])}
    # A context without an approved field still retains explicit FACT changes.
    for name,typed in sorted(context.get('changes',{}).items()):
        if name not in context.get('changed_fields',{}):
            result['scenario-value:fact:'+name]={'field':name,'role':'CURRENT','typed':deepcopy(typed)}
    return result


def extend_shape(shape,context,*,version=None):
    version=version or VERSION
    if version==SERVER_VERSION:
        from .scenario_computation import enabled
        if not enabled(context):
            raise ContractError('server computation contract requires a bound evaluation catalog')
        shape['properties']['version']={'const':version}
        shape['properties'].pop('application_links',None)
        shape['required']=[k for k in shape['required'] if k!='application_links']
        shape['required'].append('version')
        return
    from .scenario_review import condition_options
    def refs(options):return {'type':'array','uniqueItems':True,'items':{'type':'string','enum':list(options)}}
    props={'claim_id':{'type':'string'},'condition_ids':refs(condition_options(context)),
        'applied_value_refs':refs(values(context)),'comparison_value_refs':refs(values(context))}
    required=list(props)
    if version==VERSION:props['comparison_text']={'type':'string'}
    shape['properties']['version']={'const':version}
    shape['properties']['application_links']={'type':'array','items':{'type':'object','additionalProperties':False,'properties':props,'required':required}}
    shape['required']=list(dict.fromkeys([*shape['required'],'version','application_links']))


def amount_mentions(text):
    from .scenario_facts import typed_value
    return [typed_value(match.group(),{'type':'money','unit':'KRW'},written_units=True) for match in MONEY.finditer(text)]


def application_text(content):
    text=content.get('explanation') or ''
    rule=content.get('rule') or {}
    if rule.get('kind')=='CASE_APPLICATION':
        text+=' '+str(rule.get('conclusion',''))+' '+' '.join(row.get('text','') for row in rule.get('norms',[]))
    return text


def _errors_v2(value,context,facts):
    from .scenario_review import condition_options, numbers
    options=condition_options(context);catalog=values(context);problems=[]
    def fail(code,path,expected):problems.append(issue(code,path,expected=expected))
    claims={r['claim_id']:r.get('answer_content') or r for r in value.get('claims',[])}
    applications={key:row for key,row in claims.items() if row.get('explanation') or (row.get('rule') or {}).get('kind')=='CASE_APPLICATION'}
    used=set();seen=set()
    for index,link in enumerate(value['scenario_review'].get('application_links',[])):
        path='/scenario_review/application_links/'+str(index);cid=link['claim_id']
        if cid not in applications or cid in seen:
            fail('SCENARIO_APPLICATION_LINK',path,{'actual_claim_ids':list(applications),'duplicate':cid in seen});continue
        seen.add(cid);conditions=link['condition_ids'];used.update(conditions)
        required={field for c in conditions for field in options[c]['changed_inputs']}
        applied=[catalog[ref] for ref in link['applied_value_refs']]
        previous=[catalog[ref] for ref in link['comparison_value_refs']]
        if (any(row['role']!='CURRENT' for row in applied) or {row['field'] for row in applied}!=required
                or len(applied)!=len(required)):
            fail('SCENARIO_CURRENT_VALUE_BINDING',path+'/applied_value_refs',{'required_fields':sorted(required),
                'current_refs':[key for key,row in catalog.items() if row['role']=='CURRENT' and row['field'] in required]})
        if any(row['role']!='HISTORICAL' or row['field'] not in required for row in previous):
            fail('SCENARIO_COMPARISON_BINDING',path+'/comparison_value_refs',{'rule':'historical values of these same applied fields only'})
        text=application_text(applications[cid])
        # Numeric mentions are checked only against the typed monetary inputs.
        # Values need not be repeated: the deterministic display supplies them.
        allowed=[*context.get('typed_inputs',{}).values(),*[r['typed'] for r in applied],*[r['typed'] for r in previous]]
        allowed.extend(context['evaluations'][list(options).index(key)]['result']['value'] for key in conditions
            if context['evaluations'][list(options).index(key)]['result'].get('value') is not None)
        for fact in facts:
            from .scenario_facts import typed_value
            literal=typed_value(fact['value'],{'type':'money','unit':'KRW'},written_units=True)
            if literal is not None:allowed.append(literal)
        money={Decimal(str(r['value'])) for r in allowed if r['type']=='money' and r['unit']=='KRW'}
        if context.get('typed_inputs'):
            for literal in amount_mentions(text):
                if literal is None or Decimal(literal['value']) not in money:
                    fail('SCENARIO_NUMERIC_LITERAL',path,{'claim_id':cid,'observed':literal,'allowed_KRW':sorted(map(str,money))})
        # An unlabelled reuse of replaced values stays a failure. Explicit
        # comparisons permit before-values without reclassifying them as current.
        current=set().union(*(numbers(str(r['value'])) for r in context.get('typed_inputs',{}).values())) if context.get('typed_inputs') else set()
        current|=set().union(*(numbers(str(r['value'])) for r in context['changes'].values())) if context['changes'] else set()
        current|=set().union(*(numbers(f['value']) for f in facts)) if facts else set()
        historic=set().union(*(numbers(str(r['typed']['value'])) for r in catalog.values() if r['role']=='HISTORICAL')) if catalog else set()
        permitted=set().union(*(numbers(str(r['typed']['value'])) for r in previous)) if previous else set()
        observed=numbers(MONEY.sub(' ',text)) | {Decimal(r['value']) for r in amount_mentions(text) if r is not None}
        if observed & (historic-current-permitted):
            fail('SCENARIO_SUPERSEDED_RULE' if context['kind']=='RULE' else 'SCENARIO_SUPERSEDED_FACT',path,
                {'claim_id':cid,'rule':'choose CURRENT inputs; declare historical comparison explicitly'})
    if seen!=set(applications):fail('SCENARIO_APPLICATION_LINK','/claims',{'missing_claim_ids':sorted(set(applications)-seen)})
    affected={key for key,row in options.items() if row['changed_inputs']}
    if value.get('claims') and not affected<=used:fail('SCENARIO_APPLICATION_COVERAGE','/scenario_review/application_links',{'missing_condition_ids':sorted(affected-used)})
    return problems


def errors(value,context,facts):
    if value['scenario_review'].get('version')==LEGACY_VERSION:
        return _errors_v2(value,context,facts)
    from .scenario_review import condition_options, numbers
    from .scenario_facts import typed_value
    options=condition_options(context);catalog=values(context);problems=[]
    def fail(code,path,expected):problems.append(issue(code,path,expected=expected))
    claims={r['claim_id']:r.get('answer_content') or r for r in value.get('claims',[])}
    applications={cid:row for cid,row in claims.items() if application_text(row).strip()}
    current=[r for r in context.get('typed_inputs',{}).values() if r is not None]+list(context.get('changes',{}).values())
    current += [r['typed'] for r in catalog.values() if r['role']=='CURRENT']
    for fact in facts:
        literal=typed_value(fact['value'],{'type':'money','unit':'KRW'},written_units=True)
        if literal is not None:current.append(literal)
    computed=[r['result']['value'] for r in context.get('evaluations',[]) if r['result'].get('value') is not None]
    historic=[r['typed'] for r in catalog.values() if r['role']=='HISTORICAL']
    def numeric(rows):
        return set().union(*(numbers(str(r['value'])) for r in rows if r['type'] in ('money','decimal','ratio','duration'))) if rows else set()
    def money(rows):return {Decimal(str(r['value'])) for r in rows if r['type']=='money' and r['unit']=='KRW'}
    stale=numeric(historic)-numeric(current)
    used=set();seen=set();by_claim={}
    for index,link in enumerate(value['scenario_review'].get('application_links',[])):
        path='/scenario_review/application_links/'+str(index);cid=link['claim_id']
        if cid not in applications or cid in seen:
            fail('SCENARIO_APPLICATION_LINK',path,{'eligible_claim_ids':list(applications),'duplicate':cid in seen});continue
        seen.add(cid);by_claim[cid]=link;conditions=link['condition_ids'];used.update(conditions)
        required={field for condition in conditions for field in options[condition]['changed_inputs']}
        applied=[catalog[ref] for ref in link['applied_value_refs']]
        previous=[catalog[ref] for ref in link['comparison_value_refs']]
        if any(row['role']!='CURRENT' for row in applied) or {row['field'] for row in applied}!=required or len(applied)!=len(required):
            fail('SCENARIO_CURRENT_VALUE_BINDING',path+'/applied_value_refs',{'required_fields':sorted(required),
                'current_refs':[key for key,row in catalog.items() if row['role']=='CURRENT' and row['field'] in required]})
        if any(row['role']!='HISTORICAL' or row['field'] not in required for row in previous):
            fail('SCENARIO_COMPARISON_BINDING',path+'/comparison_value_refs',{'rule':'historical values of these same applied fields only'})
        comparison=link.get('comparison_text','')
        if comparison:
            if not comparison.strip() or not previous:
                fail('SCENARIO_COMPARISON_BINDING',path+'/comparison_text',{'rule':'full comparison prose requires explicit historical refs'})
            allowed=money(current+computed+[row['typed'] for row in previous])
            for literal in amount_mentions(comparison):
                if literal is None or Decimal(literal['value']) not in allowed:
                    fail('SCENARIO_NUMERIC_LITERAL',path+'/comparison_text',{'claim_id':cid,'observed':literal,'allowed_KRW':sorted(map(str,allowed))})
            permitted=numeric([row['typed'] for row in previous])
            observed=numbers(MONEY.sub(' ',comparison)) | {Decimal(r['value']) for r in amount_mentions(comparison) if r is not None}
            if observed & (stale-permitted):
                fail('SCENARIO_COMPARISON_BINDING',path+'/comparison_text',{'rule':'historical values must belong to selected comparison refs'})
    affected={key for key,row in options.items() if row['changed_inputs']}
    if value['scenario_review'].get('version')!=SERVER_VERSION and value.get('claims') and not affected<=used:
        fail('SCENARIO_APPLICATION_COVERAGE','/scenario_review/application_links',{'missing_condition_ids':sorted(affected-used),'rule':'link an actual current application for each changed condition; unchanged explanations need no link'})
    # Every current explanation is checked, including unlinked explanations.
    # Selecting a historical comparison never authorizes it as a current value.
    for cid,content in applications.items():
        text=application_text(content);path='/claims/'+cid+'/explanation'
        observed=numbers(MONEY.sub(' ',text)) | {Decimal(r['value']) for r in amount_mentions(text) if r is not None}
        invalid=observed & stale
        if invalid:
            fail('SCENARIO_SUPERSEDED_RULE' if context['kind']=='RULE' else 'SCENARIO_SUPERSEDED_FACT',path,
                {'claim_id':cid,'observed_previous':sorted(map(str,invalid)),
                 'current_inputs':deepcopy(context.get('typed_inputs',{})),
                 'rule':('server displays before/after values; explain current conditions and legal scope' if value['scenario_review'].get('version')==SERVER_VERSION else 'current explanation uses current values; retain full before/after prose in application_links.comparison_text')})
        link=by_claim.get(cid,{})
        selected=[context['evaluations'][list(options).index(key)]['result']['value'] for key in link.get('condition_ids',[])
            if context['evaluations'][list(options).index(key)]['result'].get('value') is not None]
        if value['scenario_review'].get('version')==SERVER_VERSION:
            selected=computed
        allowed=money(current+selected)
        if context.get('typed_inputs'):
            for literal in amount_mentions(text):
                if literal is None or Decimal(literal['value']) not in allowed:
                    fail('SCENARIO_NUMERIC_LITERAL',path,{'claim_id':cid,'observed':literal,'allowed_current_KRW':sorted(map(str,allowed))})
    return problems


def literal_text(typed):
    raw=typed['value']
    if typed['type'] in ('money','decimal','ratio','duration'):
        number=Decimal(str(raw));number=format(number,'f')
        if '.' in number:number=number.rstrip('0').rstrip('.')
        if typed['unit']=='KRW':return number+'원'
        return number+(' '+typed['unit'] if typed['unit'] else '')
    return str(raw)+(' '+typed['unit'] if typed['unit'] else '')


def display(receipt,context):
    from .scenario_review import condition_options
    options=condition_options(context);catalog=values(context);rows=[]
    def label(row):return context.get('changed_fields',{}).get(row['field'],{}).get('field',{}).get('concept') or row['field']
    labels={'TRUE':'조건 충족','FALSE':'조건 불충족','UNKNOWN':'미확인','CONFLICT':'입력 충돌','VALUE':'계산값'}
    for link in receipt['application_links']:
        current=[catalog[key] for key in link['applied_value_refs']]
        history=[catalog[key] for key in link['comparison_value_refs']]
        text='현재 가정: '+', '.join(label(row)+' '+literal_text(row['typed']) for row in current) if current else '현재 조건'
        if history:text+='; 변경 전 비교: '+', '.join(label(row)+' '+literal_text(row['typed']) for row in history)
        if link['condition_ids']:text+='; '+', '.join('조건 '+str(list(options).index(key)+1)+' '+labels[options[key]['status']] for key in link['condition_ids'])
        text+=' (수치 조건이며 최종 허용 판단은 별도 검토)'
        if receipt.get('version')==VERSION and link.get('comparison_text'):
            text+='\n변경 전후 비교 설명: '+link['comparison_text']
        rows.append({'claim_id':link['claim_id'],'text':text})
    return rows
