"""Three-valued applicability and typed read-only procedure execution."""
import time
from datetime import date
import json
from jsonschema import validate
from .corrected_memory import MemoryError, digest, encoded
from .shortcut_repository import uid, now


def condition(expr, facts):
    if not isinstance(expr,dict) or not expr: return None
    op=expr.get('op')
    if op in {'all','any'}:
        values=[condition(e,facts) for e in expr.get('args',[])]
        if not values: return None
        if op=='all': return False if False in values else None if None in values else True
        return True if True in values else None if None in values else False
    raw=facts.get(expr.get('field'))
    if not isinstance(raw,dict) or raw.get('kind')=='unknown' or raw.get('value') is None: return None
    value=raw['value'];wanted=expr.get('value')
    try:
        if op=='eq': return type(value) is type(wanted) and value==wanted
        if op=='in': return any(type(value) is type(x) and value==x for x in wanted)
        if op=='before' and raw['kind']=='date': return date.fromisoformat(value)<date.fromisoformat(wanted)
        if op=='duration_lt' and raw['kind']=='duration' and raw.get('unit')==expr.get('unit'):
            if type(value) not in (int,float) or type(wanted) not in (int,float): return None
            return value<wanted
    except (TypeError,ValueError): return None
    return None


def validate_procedure(procedure, catalogue):
    if not procedure.get('stop_rules') or not procedure.get('reentry'): raise MemoryError('procedure needs stop and reentry rules')
    seen=set()
    for step in procedure['steps']:
        if step['id'] in seen or not set(step.get('after',[]))<=seen: raise MemoryError('cyclic or unordered procedure')
        tool=catalogue.get(step['tool'])
        if not tool or tool.get('read_only') is not True or step['contract_hash']!=digest(tool['schema']): raise MemoryError('tool contract not approved')
        if not step.get('purpose') or not step.get('result_check'): raise MemoryError('purpose and result check required')
        if not isinstance(step.get('arguments'),dict): raise MemoryError('typed arguments required')
        # Mapping is closed: literal values or named current input fields.
        for value in step['arguments'].values():
            if not isinstance(value,dict) or set(value) not in ({'literal'},{'input'}): raise MemoryError('invalid argument mapping')
        seen.add(step['id'])
    if not seen: raise MemoryError('empty procedure')
    return True


def evaluate(repo, unit, revision, principal, *, request, facts, source_check,
             catalogue=None, flags=None, interpretation_policy='reviewed-interpretation-v1'):
    flags=flags or {};reasons=[];mode='NONE';adopted=[]
    try:
        value=repo.current(unit,revision,principal)
        # Live adapter must check actual source generation and current permissions.
        sources=[m for m in value['members'] if m['ref'].startswith('source:')]
        if not sources or not all(source_check(m) is True for m in sources): raise MemoryError('current source check failed')
        mode='HINT' if flags.get('hint') else 'NONE'
        if flags.get('procedure') and value.get('procedures'):
            for procedure in value['procedures']:
                validate_procedure(procedure,catalogue or {})
                if condition(procedure['preconditions'],facts) is not True: raise MemoryError('procedure prerequisites unknown or false')
            mode='PROCEDURE'
        if flags.get('judgment'):
            if value['completeness'] not in {'BOUNDED','CLOSED_CANDIDATE'}: raise MemoryError('open issue')
            receipts=[dict(r) for r in repo.db.execute('SELECT * FROM sw_verification WHERE unit=? AND revision=? ORDER BY rowid',(unit,revision))]
            latest={r['kind']:r for r in receipts if r['target_hash']==value['hash'] and r['expires']>time.time()}
            if any(latest.get(k,{}).get('result')!='PASS' for k in ('STRUCTURE','SOURCE','INTERPRETATION')): raise MemoryError('verification incomplete')
            if latest['INTERPRETATION']['policy']!=interpretation_policy: raise MemoryError('interpretation policy mismatch')
            for claim in value['claims']:
                if condition(claim['condition'],facts) is not True: raise MemoryError('claim condition unknown or false')
                if not claim['exceptions_checked'] or claim['unresolved'] or not claim['rationale']: raise MemoryError('claim interpretation incomplete')
                adopted.append(claim['id'])
            if not adopted: raise MemoryError('no eligible claims')
            mode='JUDGMENT'
    except (MemoryError,OSError) as exc:
        reasons.append(str(exc));adopted=[]
        # A failed judgment gate may retain an independently valid lower mode.
    payload={'mode':mode,'reasons':reasons,'adopted_claims':adopted,'facts_hash':digest(facts),
             'unit_id':unit,'revision':revision,'request':request}
    repo.db.execute('INSERT INTO sw_reuse VALUES(?,?,?,?,?,?,?)',
                    (uid('reuse:'),repo.scope(principal),request,unit,revision,encoded(payload),now()))
    return payload


def execute_procedure(procedure, *, inputs, catalogue, execute, verify_result, current_check):
    validate_procedure(procedure,catalogue)
    if condition(procedure['preconditions'],inputs) is not True: return {'status':'REENTER','stage':procedure['reentry'],'reason':'preconditions'}
    results=[]
    for step in procedure['steps']:
        if current_check() is not True: return {'status':'REENTER','stage':procedure['reentry'],'reason':'currentness','results':results}
        args={}
        for key,mapping in step['arguments'].items():
            if 'input' in mapping:
                if mapping['input'] not in inputs: return {'status':'REENTER','stage':procedure['reentry'],'reason':'missing input','results':results}
                args[key]=inputs[mapping['input']]
            else: args[key]=mapping['literal']
        validate(args,catalogue[step['tool']]['schema'])
        result=execute(step['tool'],args)
        results.append({'step':step['id'],'result':result})
        if verify_result(step['result_check'],result) is not True:
            return {'status':'REENTER','stage':procedure['reentry'],'reason':'result check','results':results}
    return {'status':'COMPLETE','results':results}
