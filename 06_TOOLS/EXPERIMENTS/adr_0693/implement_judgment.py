from pathlib import Path
R=Path(__file__).resolve().parents[3];S=R/'02_BACKEND/lawrag/research/candidates/adr_0693/consistent-judgment/snapshot'
def edit(p,a,b):
 f=S/p;t=f.read_text();assert a in t,(p,a[:60]);f.write_text(t.replace(a,b))
p='02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py'
edit(p,"CONTRACT = 'investigation-completion-v3'\nKNOWN = (V1, V2, CONTRACT)","V3 = 'investigation-completion-v3'\nCONTRACT = 'investigation-completion-v4'\nKNOWN = (V1, V2, V3, CONTRACT)")
edit(p,"assessment.get('completion_contract') == CONTRACT", "assessment.get('completion_contract') in (V3, CONTRACT)")
edit(p,'def assessment_schema(issues, materials, options):','def assessment_schema(issues, materials, options, *, contract=None, facts=()):')
edit(p,"    # Optional on the wire (like structure_filter):", "    if contract == CONTRACT:\n        claim = schema['properties']['claims']['items']\n        claim['properties']['rule'] = rule_schema([o['id'] for o in options], facts)\n        claim['required'].append('rule')\n    # Optional on the wire (like structure_filter):")
edit(p,"    return errors\n\n\ndef normalize_assessment", "    for claim in claims:\n        if claim.get('rule') is not None:\n            errors.extend(rule_errors(claim))\n    return errors\n\n\ndef normalize_assessment")
edit(p,"        claims.append({**deepcopy(claim), **quotes[0], 'evidence': quotes[1:],", "        if claim.get('rule') is not None:\n            problems = rule_errors(claim)\n            if problems:raise ContractError('; '.join(problems))\n            claim = {**claim, 'text': render_rule(claim['rule'])}\n        claims.append({**deepcopy(claim), **quotes[0], 'evidence': quotes[1:],")
edit(p,"    for note in notes:\n        items.append", "    # Recovery/normalization are operational diagnostics, never user limitations.\n    for note in ():\n        items.append")
edit(p,"    if stop_reason:\n        items.append({'id': 'L-stop'", "    if stop_reason and not items:\n        items.append({'id': 'L-stop'")
edit(p,"'text': STOP_WORDS.get(stop_reason, '조사 한도에 도달하여 확인한 근거 범위에서 답변합니다.')", "'text': '확인한 원문 범위에서 답변하며, 나머지 범위는 확인하지 못했습니다.'")
edit(p,"evidence_refs={'type': 'array'}, span_receipts={'type': 'array'})", "evidence_refs={'type': 'array'}, span_receipts={'type': 'array'},\n                               rule={'type': ['object', 'null']})")
edit(p,"'limitation_items': {'type': 'array'}, 'stop_reason': {'type': ['string', 'null']}","'limitation_items': {'type': 'array'}, 'stop_reason': {'type': ['string', 'null']}")
# Stored extra bindings remain optional for old versions; new execution always supplies them.
edit(p,"    schema['properties'].update(extra)","    schema['properties'].update(assessment_basis={'type':'object'})\n    schema['properties'].update(extra)")
with (S/p).open('a') as f:f.write('''


def rule_schema(evidence_ids, facts):
    """Request-local model observation; never a new legal source schema."""
    text = {'type':'string','minLength':1,'maxLength':1000}
    conditions = obj({'id':{'type':'string','pattern':'^T[1-9][0-9]*$'},
        'text':text,'evidence_refs':refs(evidence_ids,1)})
    groups = obj({'id':{'type':'string','pattern':'^G[1-9][0-9]*$'},
        'mode':{'type':'string','enum':['ALL','ANY','UNKNOWN']},
        'members':{'type':'array','minItems':1,'maxItems':16,'uniqueItems':True,
                   'items':{'type':'string','pattern':'^[TG][1-9][0-9]*$'}}})
    fact_ids=[x['id'] for x in facts]
    return {'anyOf':[{'type':'null'},obj({
        'kind':{'type':'string','enum':['GENERAL_RULE','CASE_APPLICATION']},
        'subject':text,'action':text,'scope':text,'conclusion':text,
        'conditions':{'type':'array','maxItems':16,'items':conditions},
        'groups':{'type':'array','maxItems':16,'items':groups},
        'root':{'type':['string','null']},
        'exceptions':{'type':'array','maxItems':12,'items':obj({'text':text,'evidence_refs':refs(evidence_ids,1)})},
        'exception_status':{'type':'string','enum':['SOURCE_EXCEPTIONS','NOT_ESTABLISHED']},
        'fact_refs':{'type':'array','items':obj({'id':{'type':'string', **({'enum':fact_ids} if fact_ids else {})},'quote':text}), **({} if fact_ids else {'maxItems':0})}
    })]}


def rule_errors(claim, facts=None):
    rule=claim['rule'];errors=[]
    atoms={x['id']:x for x in rule['conditions']};groups={x['id']:x for x in rule['groups']}
    if len(atoms)!=len(rule['conditions']) or len(groups)!=len(rule['groups']):
        errors.append('condition/group IDs must be unique')
    allowed=set(claim['evidence_refs'])
    if any(not set(x['evidence_refs'])<=allowed for x in [*rule['conditions'],*rule['exceptions']]):
        errors.append('conditions and exceptions require this claim original span references')
    seen=set()
    def visit(key,stack=()):
        if key in stack or len(stack)>4:
            errors.append('condition group cycle or depth exceeds 4');return
        seen.add(key)
        if key in atoms:return
        if key not in groups:errors.append('unknown condition/group reference');return
        for child in groups[key]['members']:visit(child,(*stack,key))
    if rule['root'] is not None:visit(rule['root'])
    if set(atoms)|set(groups)!=seen:errors.append('every condition/group must be reachable from root')
    if bool(rule['exceptions']) != (rule['exception_status']=='SOURCE_EXCEPTIONS'):
        errors.append('exception status must retain source-backed exceptions or uncertainty')
    if rule['kind']=='GENERAL_RULE' and rule['fact_refs']:
        errors.append('general rule must not assert user facts')
    if rule['kind']=='CASE_APPLICATION' and not rule['fact_refs']:
        errors.append('case application requires actual user fact provenance')
    if facts is not None:
        by_id={x['id']:x['text'] for x in facts}
        for ref in rule['fact_refs']:
            if ref['id'] not in by_id or ref['quote'] not in by_id[ref['id']]:
                errors.append('user fact quote absent from current request/facts')
    return errors


def render_rule(rule):
    atoms={x['id']:x for x in rule['conditions']};groups={x['id']:x for x in rule['groups']}
    def render_node(key):
        if key in atoms:return atoms[key]['text']
        g=groups[key];items=[render_node(k) for k in g['members']]
        prefix={'ALL':'다음 요건을 모두 충족: ','ANY':'다음 요건 중 하나 이상 충족: ','UNKNOWN':'요건 사이의 관계 미확인: '}[g['mode']]
        return '('+prefix+'; '.join(items)+')'
    text=rule['subject']+' · '+rule['action']+' · '+rule['scope']+'\\n'+rule['conclusion']
    if rule['root'] is not None:text+='\\n적용 조건: '+render_node(rule['root'])
    if rule['exceptions']:text+='\\n원문상 예외: '+'; '.join(x['text'] for x in rule['exceptions'])
    else:text+='\\n예외 적용 여부는 확인되지 않았습니다.'
    if rule['fact_refs']:text+='\\n사용자가 제공한 전제: '+'; '.join(x['quote'] for x in rule['fact_refs'])
    return text
''')
p='02_BACKEND/semantic_runtime/legal_agent/completion_execution.py'
edit(p,"        schema = cc.assessment_schema(self.issues, self.saved_material_ids, options)","        fact_sources = [{'id':'U0','text':utterance}] + [\n            {'id':'U'+str(n),'text':str(f.get('value',''))} for n,f in enumerate(state.get('facts',[]),1)]\n        schema = cc.assessment_schema(self.issues, self.saved_material_ids, options,\n            contract=cc.CONTRACT, facts=fact_sources)")
edit(p,"'repair_feedback': feedback}, schema,", "'user_fact_sources': fact_sources,\n                    'repair_feedback': feedback}, schema,")
edit(p,"                if problems:\n                    raise ProposalError", "                for claim in value.get('claims',[]):\n                    if claim.get('rule') is not None:problems.extend(cc.rule_errors(claim, fact_sources))\n                if problems:\n                    raise ProposalError")
edit(p,"                if candidate is not None:\n                    try:","                if candidate is not None and any(cc.rule_errors(c, fact_sources) for c in candidate['claims'] if c.get('rule') is not None):\n                    candidate, changes = None, 'unverified user fact or condition provenance'\n                if candidate is not None:\n                    try:")
edit(p,"ASSESS_PROMPT = '''", "ASSESS_PROMPT = '''v4: 선택/누적 요건이나 예외가 중요한 claim에는 rule 관측값을 작성한다. 단순 claim은 rule=null이다.\nrule.conditions는 원문 span을 참조하고 groups의 ALL/ANY/UNKNOWN 및 root로 중첩 관계를 보존한다. 없는 관계나 예외를 단정하지 않는다.\nrule.conclusion은 요건 목록을 반복하지 않는 결론만 쓴다. 조건·예외는 코드가 해당 구조에서 한 번 조립하며 claim.text로 다시 생성하지 않는다.\n일반 설명은 GENERAL_RULE과 빈 fact_refs, 특정 사건 적용은 CASE_APPLICATION과 실제 user_fact_sources의 U ID·정확한 사용자 원문 quote를 쓴다. 법령으로 사실 충족을 증명하지 않는다.\n같은 결론은 하나의 claim_id로 만들고 관련 issue_refs가 함께 참조한다.\n")
# Cache by actual request, source binding, adopted spans and gap outcomes.
edit(p,"        feedback = None\n        value = None", "        basis = {'contract':cc.CONTRACT,'request_hash':digest(utterance),'state_hash':digest(state),\n            'binding':self.host.binding,'evidence_hash':digest(options),'issues':self.issues,\n            'gap_outcomes':[{k:v for k,v in r.items() if k != 'investigative_actions'} for r in history],\n            'stop_reason':selection.get('stop_reason')}\n        signature = digest(basis)\n        if hasattr(self.s.work, 'heads'):\n            cached = next((h['payload'] for h in self.s.work.heads('completion_assessment',current=True)\n                if h['entity_id']==signature), None)\n            if cached is not None:\n                self.verify_claims(cached['claims'], sources)\n                self.s.work.event('ASSESSMENT_REUSED', {'basis_hash':signature})\n                return deepcopy(cached)\n        feedback = None\n        value = None")
edit(p,"        return result\n", "        return result\n")
needle="        result.update(answer_coverage=ic.coverage(result), semantic_quality_certified=False)"
edit(p,needle,needle+"\n        result['assessment_basis'] = basis\n        if hasattr(self.s.work, 'put'):\n            with self.s.work.transaction():\n                seq = self.s.work.event('ASSESSMENT_VALIDATED', {'basis_hash':signature,'payload_hash':digest(result)})\n                self.s.work.put('completion_assessment', signature, result, seq)")
# Keep COMPOSE reference to the same approved request/evidence state.
edit('02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py',"    return {'text': render(assessment, plan), 'claims':", "    return {**({'assessment_basis': deepcopy(assessment['assessment_basis'])} if 'assessment_basis' in assessment else {}),\n            'text': render(assessment, plan), 'claims':")
# Never render diagnostic recovery payloads in the signed judgment projection.
p='02_BACKEND/semantic_runtime/legal_agent/judgment_view.py'
edit(p,"                    row['structure_recovery']=[r for r in payload.get('structure_recovery',[]) if r.get('document_id') in allowed]", "                    # Rejected actions and recovery causes stay in the request journal.")
edit(p,"'judgment': claim['text'], 'quote': claim['quote']}", "'judgment': claim['text'], 'quote': claim['quote'],\n                                    **({'claim_id':claim['claim_id'],'rule':claim.get('rule')} if 'claim_id' in claim else {})}")
print('v4 source-bound condition structures, shared claims, per-gap receipts and judgment memo implemented')
