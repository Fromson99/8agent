"""Use the existing ASSESS journal/gateway and COMPOSE publisher for path choices."""
from copy import deepcopy
from ..contracts import digest
from . import ontology_scenarios as scenarios, output_contract as output, completion_contracts as cc
from . import investigation_contracts as ic
from .errors import InvestigationPending, ProposalError
from jsonschema import ValidationError

def catalog_from(payload):
    catalogs=[c['payload']['scenario_catalog'] for c in payload.get('ontology_bundles',[]) if c.get('payload',{}).get('scenario_catalog')]
    if not catalogs:return None
    if len(catalogs)==1:return catalogs[0]
    if len(catalogs)>8:raise scenarios.ContractError('scenario catalog bound')
    merged={'version':scenarios.VERSION,'authority':scenarios.APPROVED_AUTHORITY,
        'package_sha256':digest([c['package_sha256'] for c in catalogs]),
        'paths':[],'withheld':[],'originals':[],'runtime_compilation':False}
    for c in catalogs:
        prefix=c['package_sha256']+':'
        for key in ('paths','withheld','originals'):
            merged[key].extend({**deepcopy(row),'id':prefix+row['id']} for row in c[key])
    return merged

def can_reselect(host):
    budget=host.s.work.budget()
    available=budget['model_limit']-budget['finalization_reserve']-budget['model_reserved']
    return available>=4 and host.s.context.remaining()>host.s.sources.profile['selection_time_reserve_seconds']

def ordinary_after_reentry(selection):
    # A native gap reentry retains the ordinary investigation until this request ends.
    # Counters/checkpoints already persist through restart and same-request reuse.
    return bool((selection.get('investigation_state') or {}).get('gap_rounds'))

def search_choice(issues,reason):
    return {'choices':[{'issue_id':i['id'],'path_ids':[],'status':'NO_MATCH',
        'reason':reason,'next_action':'SEARCH','missing_scope':[reason],'missing_facts':[]} for i in issues]}

def assess(host,catalog,sources,options,issues,utterance,selection,judgment_context):
    schema=scenarios.selection_schema(catalog,issues)
    view=scenarios.selection_input(catalog,utterance,issues,options=options,sources=sources)
    basis={'contract':scenarios.CHOICE_VERSION,'binding':host.host.binding,'package_sha256':catalog['package_sha256'],'catalog_hash':digest(catalog),'evidence_hash':digest(options),'request_hash':digest(utterance),'issues':deepcopy(issues)}
    history=[];failure=None
    value=search_choice(issues,'현재 원문에 결속된 시나리오가 없어 질문에 필요한 원문을 조사해야 합니다.')
    if catalog['paths']:
        for round_ in range(2):
            data={**view,'reselection_remaining':1-round_}
            if history:data['previous_choice']=deepcopy(history[-1])
            def choose(payload,attempt):return host.invoke(scenarios.PROMPT,payload,schema,'memory-assess' if not attempt else 'memory-assess-repair')
            try:
                value=output.bounded_decision(host.s.work,'ontology-scenario-choice',data,schema,choose,lambda v:scenarios.validate_choice(v,catalog,issues),identity={**basis,'selection_round':round_,'previous_choice_hash':digest(history)})
            except (ProposalError,ValidationError) as exc:
                failure='SCENARIO_CHOICE_UNRESOLVED'
                host.s.work.event('SCENARIO_CHOICE_FALLBACK',{'basis_hash':digest(basis),'selection_round':round_,'cause':failure,'error':str(exc)})
                value=deepcopy(history[-1]) if history else search_choice(issues,'시나리오 선택 형식을 확정하지 못해 기존 원문 조사로 돌아갑니다.')
                break
            history.append(deepcopy(value))
            actions={c['next_action'] for c in value['choices']}
            if 'SEARCH' in actions or 'RESELECT' not in actions:break
            if round_ or not can_reselect(host):break
    result=scenarios.materialize_choice(value,catalog,issues,options)
    if result['claims']:host.verify_claims(result['claims'],sources)
    if judgment_context is not None:
        from . import read_judgment_final
        read_judgment_final.incomplete(result,judgment_context)
        result['read_judgment_review']['reason']='SCENARIO_SELECTION_ONLY_PRIOR_JUDGMENTS_REMAIN_PENDING'
    receipt=deepcopy(result['assessment_basis']['scenario_choice'])
    receipt.update(choice_contract=scenarios.CHOICE_VERSION,selection_history=history,
        effective_action='SEARCH' if failure or any(c['next_action']!='ANSWER' for c in value['choices']) else 'ANSWER',
        failure_code=failure)
    result.update(answer_coverage=ic.coverage(result),assessment_basis={**basis,'scenario_choice':receipt})
    host.s.work.event('SCENARIO_SELECTED',{'basis_hash':digest(basis),'choice':value,'selected_paths':receipt['selected_paths'],'effective_action':receipt['effective_action'],'compiler_called':False,'model_legal_text_generated':False})
    return result
