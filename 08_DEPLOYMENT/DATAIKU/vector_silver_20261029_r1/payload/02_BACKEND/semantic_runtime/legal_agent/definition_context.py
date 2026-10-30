"""Bounded source context after an explicit READ, without an applicability claim.

Only exact verified incoming definitions of wording in the selected original are
eligible. Never recursively expand these supplementary reads. Acquired material
uses the same source reader and delivery ledger; acquiring is not model delivery.
"""
from copy import deepcopy
import sqlite3
import time
from ..contracts import digest
from . import connection_scope as cs, unit_relations as rel, unit_reading as ur
from . import law_candidates as lc, tool_availability as availability
from .errors import BudgetExhausted, ContractError, ToolExecutionError

VERSION='bounded-definition-context-v1'
MAX_READS=4
MAX_CHARS=12000


def record_failure(inv, error, *, stage, identity, offer, group_id, anchor_key,
                   origin='DEFINITION_CONTEXT', revision=VERSION):
    """Use the investigation failure ledger without creating a second step.

    The failed extent is distinct from a body already acquired before an
    ancestor failed. Only a verified reader handle can identify that ancestor.
    """
    from . import request_repair as rr, tool_policy as policy
    from .tool_outcome import exception_outcome
    failed_scope = None
    if stage == 'READ' and identity is not None and offer is not None:
        failed_scope = {**{key: identity[key] for key in ('source_id', 'document_id')},
                        'block_ids': list(offer['block_ids'])}
    progress = getattr(error, 'read_progress', {})
    if stage == 'CONTEXT' and progress.get('remaining_target', {}).get('target'):
        target = inv.s.resolve(progress['remaining_target']['target'], 'P')
        failed_scope = {key: deepcopy(target[key]) for key in ('source_id', 'document_id', 'block_ids')}
    targets = [deepcopy(identity)] if identity is not None else []
    key = digest({'origin': revision, 'binding': inv.p['binding'], 'anchor': anchor_key,
                  'stage': stage, 'targets': targets, 'failed_scope': failed_scope})
    receipts = list(progress.get('completed_receipt_refs', []))
    if group_id is not None:
        receipts.extend(inv.p['selected'][group_id]['evidence_ids'])
    receipts = list(dict.fromkeys(receipts))
    outcome = exception_outcome(error, action={'tool': 'READ_ARTICLES', 'args': {'operation_key': key}},
        binding_hash=inv.s.context.binding_hash, surface='navigation', receipt_refs=receipts,
        effects='OBSERVATION_COMMITTED' if receipts else 'NONE')
    budget = inv.s.repo.budget()
    originals = bool(inv.read_records())
    choice = policy.choose_recovery(policy.require_registered('navigation', 'READ_ARTICLES'), outcome,
        policy.RecoveryState(distinct_alternative=originals, verified_originals=originals),
        policy.RecoveryBudget(deadline_expired=time.monotonic() >= inv.s.context.deadline,
            investigation_available=budget['tool_used'] < budget['tool_limit'],
            finalization_available=budget['model_reserved'] < budget['model_limit']))
    row = {'operation_key': key, 'origin': origin, 'failure_stage': stage,
        'failed_scope': failed_scope, 'completed_group_id': group_id,
        'code': rr.recoverable_tool_failure(error) or outcome.cause_code,
        'action': 'READ_ARTICLES', 'targets': targets, 'queries': [], 'step_id': 'context:' + key,
        'status': 'PARTIAL' if group_id is not None else 'UNRESOLVED', 'absence_proven': False,
        'recovery_policy': {'version': policy.VERSION, 'action': choice.action, 'owner': choice.owner},
        'tool_outcome': outcome.to_dict()}
    failures = inv.p.setdefault('tool_failures', [])
    if not any(previous['operation_key'] == key for previous in failures):
        failures.append(row)
        inv.s.repo.event('LAW_TOOL_RECOVERY', {**row, 'error_type': type(error).__name__, 'error': str(error)})
    return choice.action


def plans(groups):
    result=[];seen=set()
    for group in groups:
        if group['direction']!='INCOMING':continue
        for link in group['connections']:
            if link['already_read'] or not link.get('defines_anchor_wording'):continue
            options=[group['offers'][key] for key in link['endpoint_scopes']]
            chosen=next(((h,o) for h,o in options if o['extent']=='subtree'),None)
            if chosen is None:continue
            hit,offer=chosen;key=(hit['source_id'],offer['unit_id'],tuple(offer['block_ids']))
            if key in seen:continue
            seen.add(key);result.append((group,link,hit,offer))
    return sorted(result,key=lambda row:row[1].get('witness_source_order',0))


def acquire(inv, primary_groups):
    if not inv.policy.get('definition_context'):return []
    state=inv.p.setdefault('definition_context',{'revision':VERSION,'reserved_reads':0,'reserved_chars':0,'anchors':{},'reads':{}})
    added=[]
    for gid in primary_groups:
        if gid not in inv.p.get('requested_originals',[]):raise ContractError('definition context requires an explicitly requested original')
        record=inv.p['selected'][gid]
        key=digest([inv.p['binding'],record['source_id'],record['offer']])
        previous=state['anchors'].get(key)
        if previous and previous['status'] in ('COMPLETE','UNAVAILABLE'):
            added.extend(previous.get('groups',[]));continue
        spans=cs._spans([p for e in record['evidence'] for p in e['spans']],set(map(str,record['offer']['block_ids'])))
        scope=cs._scope('explicit READ definition context',None,[{'source_id':record['source_id'],
            'document_id':record['document_id'],'spans':spans}])
        receipt=state['anchors'].setdefault(key,{'status':'STARTED','groups':[],'omitted':[],'source_id':record['source_id']})
        inv.save()
        stage='CATALOG';identity=offer=None;new_id=None;rid=None
        try:
            with cs.bound(inv.s,scope):
                groups,statuses,limits,unresolved=rel.catalog(inv.s,[record['source_id']],inv.read_records(),set())
            receipt['scan_limits']=limits
            for group,link,hit,offer in plans(groups):
                stage='READ';new_id=None
                identity={'source_id':hit['source_id'],'document_id':hit['document_id'],'unit_id':offer['unit_id']}
                rid=digest([inv.p['binding'],hit['source_id'],offer])
                previous_read=state['reads'].get(rid)
                if previous_read and previous_read['status'] in ('COMPLETE','PARTIAL','FAILED'):
                    if previous_read.get('group_id'):receipt['groups'].append(previous_read['group_id'])
                    continue
                if previous_read is None:
                    added_chars,_=availability.sequence_cost(inv.s,
                        [(hit,offer),*availability.context_plans(inv.s,hit,offer)],inv.s.repo.evidence())
                    if state['reserved_reads']>=MAX_READS or state['reserved_chars']+added_chars>MAX_CHARS:
                        receipt['omitted'].append({'reference_id':link['reference_id'],'reason':'CONTEXT_BOUND'});continue
                    state['reserved_reads']+=1;state['reserved_chars']+=added_chars
                    state['reads'][rid]={'status':'RESERVED','reference_id':link['reference_id'],'scope_hash':digest(offer)}
                    inv.save()
                checked,unavailable=availability.article_plan(inv.s,identity)
                if unavailable:raise ContractError('verified definition context changed: '+unavailable)
                hit,checked_offer=checked
                if set(checked_offer['block_ids'])!=set(offer['block_ids']):raise ContractError('definition context endpoint extent changed')
                material=ur.read(inv.s,hit,checked_offer,action_state=inv.p['read_state'])
                if not material['complete']:raise ContractError('definition context read incomplete')
                inv.add_reads([{**material,'hit':hit}])
                new_id=lc.token(inv.s,'B',[hit['source_id'],lc.parent_offer(inv.s,hit)['id']])
                g=inv.p['groups'][new_id]
                stage='CONTEXT'
                state['reads'][rid]['group_id']=new_id
                receipt['groups'].append(new_id)
                inv.register_read(g,material,reason='선택 원문의 위임 문구를 직접 정의하는 원문 문맥; 적용 판단 전')
                state['reads'][rid].update(status='COMPLETE',group_id=new_id)
                inv.save()
                inv.s.repo.event('DELEGATED_DEFINITION_CONTEXT_ACQUIRED',{'revision':VERSION,'anchor_group':gid,
                    'group_id':new_id,'reference_id':link['reference_id'],'source_id':material['source_id'],
                    'offer':material['offer'],'model_selected_target':False,'automatic_adoption':False,
                    'navigation_delivery_claimed':False,'recursion':False})
            receipt['status']='COMPLETE'
        except (BudgetExhausted,TimeoutError,ToolExecutionError,sqlite3.OperationalError) as error:
            from .request_repair import recoverable_tool_failure
            if not isinstance(error,BudgetExhausted) and recoverable_tool_failure(error) is None:raise
            receipt.update(status='UNAVAILABLE',reason=type(error).__name__,source_absence_proven=False)
            if rid is not None and state['reads'].get(rid,{}).get('status')=='RESERVED':
                state['reads'][rid].update(status='PARTIAL' if new_id is not None else 'FAILED',reason=type(error).__name__)
            recovery=record_failure(inv,error,stage=stage,identity=identity,offer=offer,
                                    group_id=new_id,anchor_key=key)
            inv.s.repo.event('DELEGATED_DEFINITION_CONTEXT_UNAVAILABLE',deepcopy(receipt))
            inv.save()
            if recovery=='STOP':raise
        receipt['groups']=list(dict.fromkeys(receipt['groups']));added.extend(receipt['groups']);inv.save()
    return list(dict.fromkeys(added))
