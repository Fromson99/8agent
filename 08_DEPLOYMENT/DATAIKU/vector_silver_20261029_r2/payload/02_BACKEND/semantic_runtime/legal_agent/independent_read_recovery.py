"""Read-only planning for an independent source action after review rejection."""
from copy import deepcopy
import json
from ..contracts import digest
from .errors import ContractError
from .output_contract import OutputContractError

EVENT='INDEPENDENT_READ_RECOVERY'

def plan(inv,data,ctx,actions,raw,error):
    if (not inv.policy.get('independent_read_recovery') or not isinstance(error,OutputContractError)
        or error.category!='READ_JUDGMENT_INVALID' or not isinstance(raw,dict)
        or raw.get('choice')!='READ' or ctx.get('wire_version')!='read-judgment-new-entries-v3'):
        return None
    if inv.left()<=max(1,inv.s.profile.get('selection_time_reserve_seconds',30)):return None
    # Every selected action is checked again by expand/availability. No action,
    # judgment reference, missing target, or reason is invented here.
    old={h['id']:h for h in ctx['judgments']};selected=[];proof=[]
    from . import tool_availability as available
    evidence=inv.s.repo.evidence()
    from .evidence_inventory import intervals
    for row in raw.get('selections',[]):
        if not isinstance(row,dict) or row.get('relation')!='DIRECT' or row.get('source_ref') is not None:continue
        refs=row.get('judgment_refs',[])
        if any(j not in old or row.get('issue_id') not in old[j]['issue_refs'] for j in refs):continue
        action=actions.get(row.get('target'))
        if action is None or action.get('action')!='READ_ARTICLES':continue
        plan,reason=available.article_plan(inv.s,action['identity'])
        if reason:continue
        sequence=available.article_sequence(inv.s,plan)
        added,calls=available.sequence_cost(inv.s,sequence,evidence)
        if added<=0 or available.budget_reason(inv.s,added,calls,inv.p['read_state']):continue
        bound=[{'source_id':h['source_id'],'document_id':h['document_id'],'offer':o} for h,o in sequence]
        seen=[{'source_id':e['source_id'],'spans':intervals(e['spans'])} for e in evidence if any(h['source_id']==e['source_id'] for h,o in sequence)]
        fingerprint=digest([inv.p['binding'],action['identity'],bound,seen])
        prior=inv.s.repo.db.execute("SELECT payload_json,payload_hash FROM event WHERE kind=? AND json_extract(payload_json,'$.progress_ids') LIKE ?",(EVENT,'%'+fingerprint+'%')).fetchall()
        for text,hashed in prior:
            payload=json.loads(text)
            if digest(payload)!=hashed:raise ContractError('independent read recovery receipt hash changed')
            if fingerprint in payload['progress_ids']:break
        else:
            selected.append(deepcopy(row));proof.append({'id':fingerprint,'target':row['target'],'unread_characters':added,'read_calls':calls,'bound':bound})
    if not selected:return None
    value=deepcopy(raw);value['selections']=selected;value['read_review']={'new_reviews':{}}
    # A separate progress judgment, when present, must pass its original
    # validator unchanged. Rejected read judgments are not its evidence.
    return value,{'version':'independent-read-after-review-v1','progress_ids':[p['id'] for p in proof],
        'proof':proof,'rejected_judgment_ids':sorted(set(ctx.get('required',[]))),
        'judgments_adopted':False,'originals_preserved':True}
