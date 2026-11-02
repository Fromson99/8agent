from common import *
S=ROOT/read(DES/'candidate-path.json')['snapshot'];L=S/'02_BACKEND/semantic_runtime/legal_agent'
def change(name,old,new):
 p=L/name;s=p.read_text();assert old in s,(name,old);p.write_text(s.replace(old,new))
change('scenario_application.py',"VERSION='scenario-application-v2'", "VERSION='scenario-application-v3'\nLEGACY_VERSION='scenario-application-v2'\nSUPPORTED_VERSIONS=(LEGACY_VERSION,VERSION)")
p=L/'scenario_application.py';s=p.read_text();start=s.index("PROMPT='''");end=s.index("MONEY=",start)
s=s[:start]+'''PROMPT=\'''가정 검토에서는 변경된 조건을 실제로 적용하는 주장만 application_links에 연결한다. 일반 원문 규칙·변경과 무관한 승인 미확인·예외 비적용 설명에는 별도 가정 연결이 필요하지 않다. 변경된 각 조건에는 최소 하나의 실제 적용 주장이 있어야 한다. application_values의 CURRENT 값은 applied_value_refs로 선택한다. 현재 적용 explanation과 CASE_APPLICATION 결론에는 현재 값만 쓴다. 비교가 필요하면 같은 필드의 HISTORICAL 참조를 comparison_value_refs에 선택하고, 변경 전후를 설명하는 문장 전체를 선택 필드 comparison_text에 둔다. comparison_text는 현재 적용 결론과 구분하여 표시된다. 비교 참조를 붙여도 현재 적용 설명에 이전 한도를 쓰면 안 된다. GENERAL_RULE의 원문과 원래 한도는 그대로 보존한다. 값·서버 계산표를 다시 쓰거나 설명 길이를 채울 필요는 없다. 245만 원과 2,450,000원은 같은 금액이다. 승인·예외 미확인은 계속 미확인이며 숫자 TRUE가 최종 허용을 뜻하지 않는다.\'''
''' +s[end:];p.write_text(s)
change('scenario_application.py','def extend_shape(shape,context):','def extend_shape(shape,context,*,version=None):\n    version=version or VERSION')
change('scenario_application.py',"    shape['properties']['version']={'const':VERSION}","    required=list(props)\n    if version==VERSION:props['comparison_text']={'type':'string'}\n    shape['properties']['version']={'const':version}")
change('scenario_application.py',"'properties':props,'required':list(props)","'properties':props,'required':required")
change('scenario_application.py','def errors(value,context,facts):','def _errors_v2(value,context,facts):')
# Retain the exact old validator for old saved receipts, not for new generation.
p=L/'scenario_application.py';s=p.read_text();at=s.index('\ndef literal_text(')
new='''
def errors(value,context,facts):
    if value['scenario_review'].get('version')==LEGACY_VERSION:
        return _errors_v2(value,context,facts)
    from .scenario_review import condition_options, numbers
    from .scenario_facts import typed_value
    options=condition_options(context);catalog=values(context);problems=[]
    def fail(code,path,expected):problems.append(issue(code,path,expected=expected))
    claims={r['claim_id']:r.get('answer_content') or r for r in value.get('claims',[])}
    applications={cid:row for cid,row in claims.items() if application_text(row).strip()}
    current=list(context.get('typed_inputs',{}).values())+list(context.get('changes',{}).values())
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
    for index,link in enumerate(value['scenario_review']['application_links']):
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
    if value.get('claims') and not affected<=used:
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
                 'rule':'current explanation uses current values; retain full before/after prose in application_links.comparison_text'})
        link=by_claim.get(cid,{})
        selected=[context['evaluations'][list(options).index(key)]['result']['value'] for key in link.get('condition_ids',[])
            if context['evaluations'][list(options).index(key)]['result'].get('value') is not None]
        allowed=money(current+selected)
        if context.get('typed_inputs'):
            for literal in amount_mentions(text):
                if literal is None or Decimal(literal['value']) not in allowed:
                    fail('SCENARIO_NUMERIC_LITERAL',path,{'claim_id':cid,'observed':literal,'allowed_current_KRW':sorted(map(str,allowed))})
    return problems

'''
s=s[:at]+new+s[at:];p.write_text(s)
change('scenario_application.py',"        rows.append({'claim_id':link['claim_id'],'text':text+' (수치 조건이며 최종 허용 판단은 별도 검토)'})", "        text+=' (수치 조건이며 최종 허용 판단은 별도 검토)'\n        if receipt.get('version')==VERSION and link.get('comparison_text'):\n            text+='\\n변경 전후 비교 설명: '+link['comparison_text']\n        rows.append({'claim_id':link['claim_id'],'text':text})")
change('scenario_review.py','def attach(schema, context, *, typed=False):','def attach(schema, context, *, typed=False, application_version=None):')
change('scenario_review.py',"extend_shape(out['properties'][FIELD],context)","extend_shape(out['properties'][FIELD],context,version=application_version)")
change('scenario_review.py',"typed=isinstance(receipt,dict) and receipt.get('version')==typed_application.VERSION", "typed=isinstance(receipt,dict) and receipt.get('version') in typed_application.SUPPORTED_VERSIONS")
change('scenario_review.py',"context,typed=typed)['properties'][FIELD]", "context,typed=typed,application_version=receipt.get('version') if typed else None)['properties'][FIELD]")
change('scenario_review.py',"if assessment.get('assessment_basis',{}).get('scenario_application_version')==typed_application.VERSION and (receipt or {}).get('version')!=typed_application.VERSION:","expected_version=assessment.get('assessment_basis',{}).get('scenario_application_version')\n    if expected_version in typed_application.SUPPORTED_VERSIONS and (receipt or {}).get('version')!=expected_version:")
change('scenario_review.py',"if (receipt or {}).get('version')==typed_application.VERSION and assessment.get('scenario_application_display')", "if (receipt or {}).get('version') in typed_application.SUPPORTED_VERSIONS and assessment.get('scenario_application_display')")
change('scenario_review.py',"raise OutputContractError('가정 변경값·조건 평가와 최종 제안이 일치하지 않습니다. 이전 사건값을 현재 사실로 사용하지 마세요.', problems, category='SCENARIO_REVIEW_INVALID')", "messages={\n            'SCENARIO_APPLICATION_LINK':'가정 연결이 실제 적용 주장과 일치하지 않습니다.',\n            'SCENARIO_APPLICATION_COVERAGE':'변경된 조건을 적용하는 실제 주장을 연결하세요. 일반 설명에는 별도 연결이 필요하지 않습니다.',\n            'SCENARIO_SUPERSEDED_RULE':'현재 적용 설명에 이전 규칙값이 있습니다. 현재값으로 판단하고 변경 전후 비교는 comparison_text에 보존하세요.',\n            'SCENARIO_SUPERSEDED_FACT':'현재 적용 설명에 이전 사실값이 있습니다. 현재값으로 판단하고 변경 전후 비교는 comparison_text에 보존하세요.',\n            'SCENARIO_NUMERIC_LITERAL':'설명에 연결되지 않은 금액 또는 잘못된 단위가 있습니다.',\n            'SCENARIO_COMPARISON_BINDING':'변경 전후 비교의 과거 참조와 설명을 확인하세요.',\n        }\n        message=' '.join(dict.fromkeys(messages.get(p['code'],'가정 검토의 해당 필드와 조건을 확인하세요.') for p in problems))\n        raise OutputContractError(message, problems, category='SCENARIO_REVIEW_INVALID')")
# Assemble the question from its authoritative components, before model encoding.
change('completion_execution.py',"        if state.get('scenario_context'):\n            context['hypothetical_scenario']=deepcopy(state['scenario_context'])", "        if state.get('scenario_context'):\n            if context.get('question')!=self.host.question(state):\n                raise ContractError('scenario question is not the bound task/facts rendering')\n            context['question']=state['task']\n            context['hypothetical_scenario']=deepcopy(state['scenario_context'])")
# Versioned shared receipts: old saved bindings still validate exactly.
change('assessment_links.py',"VERSION = 'assessment-review-links-v1'", "VERSION = 'assessment-review-links-v2'\nSUPPORTED_VERSIONS = ('assessment-review-links-v1', VERSION)")
change('assessment_links.py',"사용하지 않는 연결을 넣지 않는다.", "UNRESOLVED/EXCLUDED/NOT_USED 등 채택 주장이 없는 행에서는 서버가 claim_refs=[]를 고정한다. 이 행에는 link_ref를 작성하지 않고 해당 basis_refs와 gap/이유를 작성한다. 채택 행의 link_ref 설명에 있는 최소·최대 개수를 지킨다. 사용하지 않는 연결을 넣지 않는다.")
change('assessment_links.py',"            if {'claim_refs','basis_refs'}<=props.keys():\n                props.pop('claim_refs');props.pop('basis_refs')\n                props['link_ref']={'type':'string','pattern':'^review-link:[1-9][0-9]*$'}", "            if {'claim_refs','basis_refs'}<=props.keys():\n                if props['claim_refs'].get('maxItems')==0:\n                    props['claim_refs'].update(const=[],readOnly=True)\n                    return\n                constraints={name:{k:v for k,v in props[name].items() if k in ('minItems','maxItems','uniqueItems')} for name in ('claim_refs','basis_refs')}\n                props.pop('claim_refs');props.pop('basis_refs')\n                import json\n                props['link_ref']={'type':'string','pattern':'^review-link:[1-9][0-9]*$',\n                    'description':'Selected review_links row must satisfy '+json.dumps(constraints,separators=(',',':'))}")
change('assessment_links.py',"        validate_shape(value,schema)\n        return value", "        try:validate_shape(value,schema)\n        except OutputContractError as exc:\n            remapped=[]\n            for entry in exc.issues:\n                item=deepcopy(entry)\n                for binding in bindings:\n                    for field in ('claim_refs','basis_refs'):\n                        original=binding['path']+'/'+field\n                        if item['path']==original or item['path'].startswith(original+'/'):\n                            index=next(i for i,row in enumerate(rows) if row['id']==binding['link_id'])\n                            item['path']=binding['path']+'/link_ref'\n                            item['related_paths']=['/'+FIELD+'/'+str(index)+'/'+field]\n                            item['expected_constraint']={'link_id':binding['link_id'],'field':field,'constraint':entry.get('expected_constraint')}\n                remapped.append(item)\n            raise OutputContractError('선택한 공유 연결이 해당 검토 행의 주장·근거 개수 제약과 일치하지 않습니다.',remapped,category='REQUIREMENT_REVIEW_INVALID') from exc\n        return value")
change('assessment_links.py',"required=assessment.get('assessment_basis',{}).get('review_links_version')==VERSION", "expected=assessment.get('assessment_basis',{}).get('review_links_version')\n    required=expected in SUPPORTED_VERSIONS")
change('assessment_links.py',"if receipt.get('version')!=VERSION or receipt.get('receipt_hash')!=digest({k:v for k,v in receipt.items() if k!='receipt_hash'}):", "if receipt.get('version') not in SUPPORTED_VERSIONS or (required and receipt.get('version')!=expected) or receipt.get('receipt_hash')!=digest({k:v for k,v in receipt.items() if k!='receipt_hash'}):")
# repair_proposal has no assessment basis; preserve either validated receipt version.
change('assessment_links.py',"if receipt.get('version') not in SUPPORTED_VERSIONS or (required and receipt.get('version')!=expected) or receipt.get('receipt_hash')!=digest({k:v for k,v in receipt.items() if k!='receipt_hash'}):return result", "if receipt.get('version') not in SUPPORTED_VERSIONS or receipt.get('receipt_hash')!=digest({k:v for k,v in receipt.items() if k!='receipt_hash'}):return result")
change('review_explanation.py',"'SCENARIO_NUMERIC_LITERAL':'적용 설명의 금액·단위가 연결된 현재값이나 명시한 과거 비교값과 다릅니다.'", "'SCENARIO_NUMERIC_LITERAL':'현재 적용 또는 별도 비교 설명의 금액·단위가 해당 역할의 연결값과 다릅니다.'")
print('Implemented versioned scope, nonadopting links, comparison and structured scenario input')
