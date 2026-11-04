from pathlib import Path
import json
ROOT=Path('/home/jin/8-AGENT');D=ROOT/'04_EXPERIMENTS/ADR/ADR-1319-multiturn-command-assessment-repair/artifacts/design'
C=ROOT/json.loads((D/'candidate-path.json').read_text())['candidate']/'snapshot';P=C/'02_BACKEND/semantic_runtime/legal_agent'
p=P/'memory_methods.py';s=p.read_text();at=s.index('\ndef history_projection')
s=s[:at]+'''
def command_branch(schema, name, context):
    """Expose the same mechanical field constraints enforced by normalize.

    Semantic intent, authorization and restoration receipts are still checked
    after the proposal; this function never chooses a method or a legal scope.
    Persisted legacy EXPLICIT commands remain readable by normalize.
    """
    from copy import deepcopy
    branch = deepcopy(schema)
    props = branch['properties']
    props['method_id'] = {'type':'string', 'const':name}
    targets = offered(context)[name]['targets']
    choices = ([{'type':'string','enum':[t for t in targets if t is not None]}]
               if any(t is not None for t in targets) else [])
    if None in targets:choices.append({'type':'null'})
    props['target'] = {'anyOf':choices}
    if name not in ('CASE_START','EXPERIENCE_REUSE','RESEARCH_REPLAN'):
        props['document_scope_mode'] = {'type':'string','const':'KEEP'}
    if name == 'EXPERIENCE_REUSE':
        branch['allOf'] = [{'anyOf':[
            {'properties':{'target':{'type':'null'}}},
            {'properties':{'document_scope_mode':{'const':'KEEP'}}}]}]
    if name not in ('CASE_START','PURPOSE_REVISE','RESEARCH_REPLAN'):
        props['search_scope_change'] = {'type':'object',
            'properties':{'operation':{'const':'KEEP'},'targets':{'type':'array','maxItems':0},
                          'user_quote':{'const':''}},
            'required':['operation','targets','user_quote'],'additionalProperties':False}
    if name != 'STATE_RESTORE':
        props['restore_event'] = {'type':'null'}
        props['restore_fields'] = {'type':'array','maxItems':0}
    if name in ('ANSWER_PRESENT','HISTORY_EXPLAIN','EXPERIENCE_CONFIRM','WIKI_RELINK','RESEARCH_REENTER','FACT_UPDATE'):
        for field in FIELDS:
            if name == 'FACT_UPDATE' and field == 'facts':continue
            props[field] = {'const':'KEEP'} if field == 'source_category' else {'type':'null'}
    if name == 'FACT_UPDATE':props['facts']['type'] = 'array'
    if name == 'PURPOSE_REVISE':props['task'].update(type='string',minLength=1)
    if name == 'RESEARCH_REENTER':
        props['stage'] = {'enum':['INTENT','PLAN','RECALL','READ','SELECT','ASSESS','COMPOSE']}
    if name in ('EXPERIENCE_REUSE','WIKI_RELINK'):
        props['knowledge_id'] = {'type':'string','enum':[k['id'] for k in context['knowledge']]}
    return branch


def repair_schema(schema, payload, context):
    """A mechanical field correction cannot replace a valid action/target.

    Semantic command-check or admission failures retain the full decision menu.
    No default command, inferred intent, or implicit field correction is applied.
    """
    from copy import deepcopy
    prior = payload.get('rejected_decision')
    if not isinstance(prior,dict) or prior.get('check') is not None:return schema
    raw = prior.get('command')
    if not isinstance(raw,dict):return schema
    item = offered(context).get(raw.get('method_id'))
    if not item or raw.get('target') not in item['targets']:return schema
    issues = payload.get('repair_contract',{}).get('validation',{}).get('issues',[])
    if not issues or any(not i.get('code','').startswith('SCHEMA_') or
        i.get('path','/') in ('/','/method_id','/target') for i in issues):return schema
    value = deepcopy(schema)
    value['properties']['method_id'] = {'const':raw['method_id']}
    value['properties']['target'] = {'const':raw['target']}
    value['description'] = '필드 형식 보완: 원래 method_id와 target을 유지한다. 새로운 목표로 바꾸지 않는다.'
    return value

''' +s[at:];p.write_text(s)
p=P/'corrected_memory.py';s=p.read_text();start=s.index('        branches=[]',s.index('    def resolve'));end=s.index("        closed['properties']['method_id']",start)
s=s[:start]+"        from .memory_methods import command_branch, repair_schema\n        branches=[command_branch(closed,name,context) for name in context['offered_methods']]\n"+s[end:]
s=s.replace("        def propose(payload,attempt):\n            raw=self.invoke(","        def propose(payload,attempt):\n            current_schema=repair_schema(closed,payload,context) if attempt else closed\n            raw=self.invoke(")
s=s.replace(",payload,closed,'memory-resolve' if not attempt else 'memory-resolve-repair')\n            command=prepare(raw)",",payload,current_schema,'memory-resolve' if not attempt else 'memory-resolve-repair')\n            try:\n                output.validate_shape(raw,current_schema)\n                command=prepare(raw)\n            except (output.OutputContractError, ValidationError) as exc:\n                exc.proposal={'command':deepcopy(raw),'check':None}\n                raise")
p.write_text(s)
p=P/'output_contract.py';s=p.read_text().replace("('choice','next_action','operation','kind','status','disposition')","('method_id','choice','next_action','operation','kind','status','disposition')")
old="        except (ProposalError, ValidationError) as exc:\n            retry=not attempt and repairable(exc)"
assert old in s;s=s.replace(old,"        except (ProposalError, ValidationError) as exc:\n            value=deepcopy(getattr(exc,'proposal',value))\n            retry=not attempt and repairable(exc)")
p.write_text(s)
p=P/'read_judgment_final.py';s=p.read_text();at=s.index('\ndef independent_core');s=s[:at]+'''
def repair_choices(value, error):
    """Point at conflicting model decisions without choosing their replacement.

    The same original review validators remain authoritative. Shared evidence
    is a diagnostic link only, never evidence of semantic adoption/completeness.
    """
    if not isinstance(value,dict):return []
    from .output_contract import diagnostics
    relevant = {'SCOPE_CLAIM_EVIDENCE','SCOPE_USE_UNSUPPORTED_RANGE','NEED_CLAIM_LINK',
                'FINAL_REVIEW_UNRESOLVED_GAP'}
    if not any(i['code'] in relevant for i in diagnostics(error).get('issues',[])):return []
    claims = value.get('claims',[])
    review = value.get(FIELD,{})
    if not isinstance(review,dict):return []
    rows = []
    for i,row in enumerate(review.get('judgments',[])):
        if row.get('disposition') not in ('UNRESOLVED','NOT_USED'):continue
        overlaps = [c.get('claim_id') for c in claims if
            set(c.get('evidence_refs',[])) & set(row.get('basis_refs',[]))]
        if not overlaps:continue
        rows.append({'path':'/'+FIELD+'/judgments/'+str(i), 'judgment_id':row.get('id'),
            'current_disposition':row['disposition'],'claims_sharing_evidence':overlaps,
            'alternatives':[
                '현재 원문 판단을 실제 답에 채택했다면 USE 또는 CONDITIONAL과 실제 주장·근거 연결을 직접 선택한다.',
                '채택하지 않았다면 UNRESOLVED/NOT_USED와 이유를 유지하고, 충돌하는 USE 범위·해결 연결을 검토한다. 중요한 미확인은 gaps에 남긴다.'],
            'constraint':'같은 원문을 썼다는 이유만으로 판단을 채택하지 않는다. claim·인용·질문 요구를 임의 삭제하지 않는다.'})
    return rows

''' +s[at:]
s=s.replace("CONDITIONAL은 이번 claims", "USE는 현재 답변에 채택했다는 뜻이다. 'C1에 반영했다'고 판단했다면 UNRESOLVED가 아니라 실제 채택 상태와 연결을 선택한다. 이전 판단의 채택 여부와 조사 완료 여부를 혼동하지 않는다.\nCONDITIONAL은 이번 claims")
p.write_text(s)
p=P/'requirement_coverage.py';s=p.read_text();s=s.replace("PROMPT = '''", "PROMPT = '''이미 답한 요구는 SATISFIED이며 EXCLUDED는 답변 완료 표시가 아니다. EXCLUDED는 이번 질문 범위에서 제외하기로 직접 판단한 요구에만 사용한다. ")
p.write_text(s)
p=P/'completion_execution.py';s=p.read_text();old="feedback = {'errors': str(exc), 'validation':output.diagnostics(exc), 'rejected_assessment': assessment_links.repair_proposal(source_work_review.repair_proposal(value,judgment_context,options))}"
assert old in s;s=s.replace(old,old+"\n                    choices=final_judgment.repair_choices(value,exc)\n                    if choices:feedback['decision_repair_choices']=choices")
p.write_text(s)
print('Edited6 isolated product files; no normalization of legal statuses')
