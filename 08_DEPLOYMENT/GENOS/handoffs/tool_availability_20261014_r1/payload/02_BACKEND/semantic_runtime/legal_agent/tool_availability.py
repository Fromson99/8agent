"""Deterministic navigation preconditions shared by menus and execution.

These checks authorize no evidence and consume no read/model budget. Source
verification and state ownership remain the reader/transaction's responsibility.
"""
from . import unit_reading as ur, law_candidates as lc, unit_relations as rel
from .errors import ContractError, BudgetExhausted

NAVIGATION = frozenset(('READ_ARTICLES','READ_PARENT','READ_SCOPE','VIEW_SAVED_SOURCE',
    'RESEARCH','SEARCH_BODY','SEARCH_STRUCTURE','OPEN_STRUCTURE','BROWSE_STRUCTURE',
    'NEXT_STRUCTURE','NEXT_LAWS','OPEN_LAW','NEXT_ARTICLES','NEXT_HITS',
    'FOLLOW_CONNECTION','RETURN_TO'))


def article_plan(s, identity):
    """Resolve an exact selected subtree; never substitute a smaller scope."""
    sid=identity['source_id'];src=s.tools.sources.get(sid)
    if src is None or src['document_id'] not in s.scope:
        return None, 'SOURCE_OUTSIDE_SCOPE'
    did=src['document_id']
    if identity.get('document_id',did)!=did:return None,'SOURCE_DOCUMENT_MISMATCH'
    hit=rel.hit_for(s,sid,identity.get('unit_id'));uid=hit['unit_id']
    if uid!='None':
        if (did,uid) not in s.matcher.units:return None,'STRUCTURE_NOT_AVAILABLE'
        wanted=ur.blocks(s,did,uid,'subtree')
        if not wanted:return None,'NO_ORIGINAL_IN_SELECTED_SCOPE'
        bound={str(b['block_id']) for b in src['blocks']}
        if not set(wanted)<=bound:return None,'SUBTREE_CROSSES_SOURCE_BOUNDARY'
        if not ur.blocks(s,did,uid,'exact'):
            if not any(s.store.source(did,b)['text'] for b in wanted):
                return None,'NO_ORIGINAL_IN_SELECTED_SCOPE'
        if identity.get('unit_id') is not None or not ur.blocks(s,did,uid,'exact'):
            hit=lc.structure_hit(s,sid,uid)
        offer=next((o for o in ur.offers(s,hit) if o['extent']=='subtree' and str(o['unit_id'])==uid),None)
    else:
        offer=next((o for o in ur.offers(s,hit) if o['extent']=='exact'),None)
    if offer is None or not offer['block_ids'] or not offer['chars']:
        return None,'NO_ORIGINAL_IN_SELECTED_SCOPE'
    return (hit,offer),None


def read_cost(s, hit, offer, evidence):
    """Predict the existing reader's character and segment pagination exactly."""
    from .evidence_inventory import intervals
    known={}
    for e in evidence:
        if e['source_id']==hit['source_id']:
            for bid,ranges in intervals(e['spans']).items():known.setdefault(bid,[]).extend(ranges)
    missing=0;lengths=[]
    for bid in offer['block_ids']:
        size=len(s.store.source(hit['document_id'],bid)['text']);end=0
        for lo,hi in sorted(known.get(str(bid),[])):
            length=max(0,min(lo,size)-end)
            if length:lengths.append(length)
            missing+=length;end=max(end,min(hi,size))
        length=max(0,size-end)
        if length:lengths.append(length)
        missing+=length
    calls=0;index=0;offset=0
    while index<len(lengths):
        calls+=1;remaining=s.profile['max_read_chars'];rows=0
        while index<len(lengths) and remaining and rows<s.profile['page_size']:
            taken=min(remaining,lengths[index]-offset);remaining-=taken;offset+=taken;rows+=1
            if offset==lengths[index]:index+=1;offset=0
    return missing,calls


def sequence_cost(s, plans, evidence):
    known=list(evidence);chars=calls=0
    for hit,offer in plans:
        added,count=read_cost(s,hit,offer,known);chars+=added;calls+=count
        # Planning only: these spans never leave this local calculation and
        # cannot enter the evidence repository or count as verified originals.
        known.append({'source_id':hit['source_id'],'spans':[
            {'block_id':str(b),'start_cp':0,'end_cp':len(s.store.source(hit['document_id'],b)['text'])}
            for b in offer['block_ids']]})
    return chars,calls


def budget_reason(s, added, calls, state):
    current=getattr(s,'_unit_read_state',{})
    if max(state.get('chars',0),current.get('chars',0))+added>ur.POLICY['initial_chars']:return 'READ_CHARACTER_LIMIT'
    if calls:
        if max(state.get('count',0),current.get('count',0))+calls>ur.POLICY['read_actions']:return 'READ_ACTION_LIMIT'
        budget=s.repo.budget()
        if budget['tool_used']+calls>budget['tool_limit']:return 'TOOL_ACTION_LIMIT'
    return None


def context_plans(s,hit,offer):
    """Mirror mandatory ancestor introductions, within this canonical source."""
    uid=offer['unit_id'];result=[];seen=set()
    if uid is None or str(uid)==str(hit['article_unit_id']):return result
    current=s.matcher.units[(hit['document_id'],str(uid))].get('parent')
    while current is not None:
        if current in seen:raise ContractError('context parent cycle')
        seen.add(current);h=rel.hit_for(s,hit['source_id'],current)
        own=next((o for o in ur.offers(s,h) if o['extent']=='exact'),None)
        if own:result.append((h,own))
        if str(current)==str(hit['article_unit_id']):break
        current=s.matcher.units[(hit['document_id'],str(current))].get('parent')
    return result


def read_reason(s, hit, offer, state, *, evidence=None):
    if not offer['block_ids'] or not offer['chars']:return 'NO_ORIGINAL_IN_SELECTED_SCOPE'
    plans=[(hit,offer),*context_plans(s,hit,offer)]
    return budget_reason(s,*sequence_cost(s,plans,s.repo.evidence() if evidence is None else evidence),state)


def article_sequence(s,plan):
    hit,offer=plan
    own=next((o for o in ur.offers(s,hit) if o['extent']=='exact'),None)
    if own is None:raise ContractError('resolved article has no owning original')
    return [(hit,own),(hit,offer),*context_plans(s,hit,offer)]


def navigation_reason(inv, action, data=None, *, evidence=None):
    kind=action['action'];ident=action['identity'];p=inv.p;s=inv.s
    if kind not in NAVIGATION:return 'UNREGISTERED_ACTION'
    did=ident.get('document_id');uid=ident.get('unit_id')
    if ident.get('source_id') is not None:
        source=s.tools.sources.get(ident['source_id'])
        if not source or source['document_id'] not in s.scope:return 'SOURCE_OUTSIDE_SCOPE'
        if did is not None and did!=source['document_id']:return 'SOURCE_DOCUMENT_MISMATCH'
    if did is not None and did not in s.scope:return 'DOCUMENT_OUTSIDE_SCOPE'
    if uid is not None and did is not None and (did,str(uid)) not in s.matcher.units:
        return 'STRUCTURE_NOT_AVAILABLE'
    if inv.recovery_blocked(action):return 'STRUCTURE_RECOVERY_REQUIRED'
    if kind=='RESEARCH' and inv.search_rounds_used()>=inv.policy['search_rounds']:return 'SEARCH_ROUND_LIMIT'
    if kind=='SEARCH_STRUCTURE' and len(p['structure_search_history'])>=inv.policy['search_rounds']:return 'STRUCTURE_SEARCH_LIMIT'
    if kind=='SEARCH_BODY':
        if not inv.policy['structure_first']:return 'SCOPED_SEARCH_DISABLED'
        if len(p.get('body_search_history',[]))>=inv.policy['search_rounds']:return 'BODY_SEARCH_LIMIT'
    if kind=='READ_ARTICLES':
        plan,reason=article_plan(s,ident)
        return reason or budget_reason(s,*sequence_cost(s,article_sequence(s,plan),s.repo.evidence() if evidence is None else evidence),p['read_state'])
    if kind in ('READ_PARENT','READ_SCOPE','VIEW_SAVED_SOURCE'):
        gid=ident['branch_id'];group=p['groups'].get(gid)
        if group is None:return 'BRANCH_NOT_AVAILABLE'
        if group['hit']['document_id'] not in s.scope:return 'DOCUMENT_OUTSIDE_SCOPE'
        if kind=='VIEW_SAVED_SOURCE':
            if gid not in p['selected'] or not group['page_plan']:return 'SAVED_ORIGINAL_NOT_AVAILABLE'
            return None
        if kind=='READ_PARENT' and ident.get('continuation'):
            acknowledged=max([group['delivery']]+[page['page'] for page in (data or {}).get('sources',[]) if page['branch_id']==gid])
            if gid not in p['selected'] or ident['page']!=acknowledged or ident['page']>=len(group['page_plan']):
                return 'STALE_READ_CONTINUATION'
            return None
        opts=ur.offers(s,group['hit']);wanted=group['offer'] if kind=='READ_PARENT' else next((o for o in opts if o['id']==ident['scope']),None)
        if wanted is None or wanted not in opts:return 'READ_SCOPE_NOT_AVAILABLE'
        return read_reason(s,group['hit'],wanted,p['read_state'],evidence=evidence)
    if kind=='NEXT_LAWS':
        if inv.policy['structure_first'] and not inv.policy['selectable_search']:return 'GLOBAL_SEARCH_DISABLED'
        if not ident.get('cursor') or ident['cursor']!=p['law_page']['next_cursor']:return 'STALE_LAW_CURSOR'
    if kind=='NEXT_ARTICLES':
        page=p['article_pages'].get(did)
        if not page or not ident.get('cursor') or ident['cursor']!=page['next_cursor']:return 'STALE_ARTICLE_CURSOR'
        if inv.policy['structure_first'] and (did not in p['fulltext_scopes'] or p['fulltext_scopes'][did]!=uid):return 'STALE_SEARCH_SCOPE'
    if kind=='NEXT_HITS':
        sid=ident['source_id'];src=s.tools.sources.get(sid);page=p['hit_pages'].get(sid)
        if not src or src['document_id'] not in s.scope:return 'SOURCE_OUTSIDE_SCOPE'
        if not page or not ident.get('cursor') or ident['cursor']!=page['next_cursor']:return 'STALE_HIT_CURSOR'
    if kind=='NEXT_STRUCTURE':
        page=p['structure_page']
        if page['next_offset'] is None or any(ident.get(k)!=page.get(k) for k in ('document_id','queries','structure_filter')) or ident.get('offset')!=page['next_offset']:
            return 'STALE_STRUCTURE_PAGE'
    if kind=='RETURN_TO':
        from . import investigation_chain as trail
        if ident['frame_id'] not in trail.state(p)['frames']:return 'RETURN_POINT_NOT_AVAILABLE'
    if kind=='FOLLOW_CONNECTION':
        if not inv.read_records():return 'NO_READ_ANCHOR'
    return None


def prune_handles(data, blocked):
    """Remove dangling executable links, leaving immutable history untouched."""
    if isinstance(data,dict):
        for key,value in list(data.items()):
            if key in ('investigation_chain','recent_rejections','already_presented_reads'):continue
            if isinstance(value,str) and value in blocked and (key.endswith('action') or key=='action_id'):
                data[key]=None
            elif isinstance(value,list) and (key.endswith('actions') or key=='action_ids'):
                data[key]=[row for row in value if not (isinstance(row,str) and row in blocked)]
                for row in data[key]:prune_handles(row,blocked)
            elif isinstance(value,(dict,list)):prune_handles(value,blocked)
    elif isinstance(data,list):
        for row in data:prune_handles(row,blocked)


def filter_navigation(inv, data, actions):
    evidence=inv.s.repo.evidence();blocked={}
    for target,action in list(actions.items()):
        reason=navigation_reason(inv,action,data,evidence=evidence)
        if reason:blocked[target]=reason;del actions[target]
    if blocked:
        prune_handles(data,set(blocked))
        inv.s.repo.event('TOOL_MENU_FILTERED',{'stage':'SELECT','state_version':inv.p.get('state_version'),
            'blocked':blocked,'remaining':sorted(actions)})
    data['actions']=[row for row in data.get('actions',[]) if row['id'] in actions]
    # Close the batch cardinality as well: every offered combination fits the
    # remaining budget even without assuming overlap between selected articles.
    costs=[sequence_cost(inv.s,article_sequence(inv.s,article_plan(inv.s,a['identity'])[0]),evidence)
        for a in actions.values() if a['action']=='READ_ARTICLES']
    limit=0
    for count in range(1,min(8,len(costs))+1):
        chars=sum(sorted((c[0] for c in costs),reverse=True)[:count])
        calls=sum(sorted((c[1] for c in costs),reverse=True)[:count])
        if budget_reason(inv.s,chars,calls,inv.p['read_state']):break
        limit=count
    data['read_batch_limit']=limit
    return blocked


def require_navigation(inv, decision, data, actions):
    plans=[]
    for target in decision.get('targets',[]):
        if target not in actions:raise ContractError('tool is not offered')
        reason=navigation_reason(inv,actions[target],data)
        if reason:
            error=BudgetExhausted if reason in ('READ_CHARACTER_LIMIT','READ_ACTION_LIMIT','TOOL_ACTION_LIMIT') else ContractError
            raise error('tool not available in current state: '+reason)
    if decision.get('next_action')=='READ_ARTICLES':
        for target in decision.get('targets',[]):plans.extend(article_sequence(inv.s,article_plan(inv.s,actions[target]['identity'])[0]))
        reason=budget_reason(inv.s,*sequence_cost(inv.s,plans,inv.s.repo.evidence()),inv.p['read_state'])
        if reason:raise BudgetExhausted('selected read batch unavailable: '+reason)
