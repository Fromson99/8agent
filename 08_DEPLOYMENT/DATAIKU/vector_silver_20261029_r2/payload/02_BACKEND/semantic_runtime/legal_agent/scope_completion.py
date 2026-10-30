"""A literal source-discovery floor, independent of a model's sufficiency claim.

Uses the existing generation's title index and current search scope. It is not a
semantic relevance classifier: original acquisition still requires legal review.
"""
from copy import deepcopy
from ..contracts import digest
from ..navigation_match import norm
from . import query_scope as qs
from .errors import ContractError, ProposalError

VERSION = 'request-heading-original-v1'

def enabled(inv):
    from .source_goal_control import enabled as goals_enabled
    return inv.policy.get('scope_completion', False) and goals_enabled(inv)

def discover(inv, data, st):
    if not enabled(inv): return
    issues = data.get('issues', [])
    request = data.get('current_request', inv.question)
    binding = digest([VERSION, inv.p['binding'], request, issues, sorted(inv.s.scope), qs.active(inv.s)])
    if st.get('scope_discovery'):
        if st['scope_discovery']['binding'] != binding:
            raise ContractError('scope discovery binding changed')
        return
    from .structure_query import coordinate_index
    from .source_goal_control import commit, refresh
    matcher = inv.s.matcher
    goals = deepcopy(st.get('source_goals', [])); overflow = []; discoveries = []
    for issue in issues:
        # Only actual user text supplies the lexical clue. Model summaries cannot
        # manufacture a required original. Matching a whole title is not a number rule.
        text = issue.get('request_quote') or issue.get('question', '')
        if not text or text not in request: continue
        for hit in matcher.structures.match(text):
            if len(norm(hit['text'])) < 4: continue
            for value in hit['values']:
                if value['kind'] != 'TITLE': continue
                did, uid = value['document_id'], str(value['unit_id'])
                if not qs.direct(inv.s, did, uid): continue
                try:
                    qs.check_selection_exclusions(matcher, [{'document_id':did,'unit_id':uid}], (qs.active(inv.s) or {}).get('selections', []))
                except qs.UnresolvedScope: continue
                node = matcher.units.get((did, uid), {})
                coordinate = matcher.stored_coordinates.get((did, uid))
                if (not coordinate or coordinate.unit != '조' or coordinate.chain
                        or node.get('coordinate_scope') != 'body'
                        or node.get('coordinate_binding', {}).get('mode') == 'unresolved'): continue
                surface = coordinate.canonical_surface()
                ident = digest([issue['id'], did, surface, 'body'])
                witness = {'kind':VERSION,'unit_id':uid,'heading':node.get('title',''),
                           'request_quote':hit['text'],'start':hit['start'],'end':hit['end']}
                if any(d['identity']==ident for d in discoveries): continue
                sources = matcher._unit_sources(did, uid)
                unique = coordinate_index(matcher).get((did, surface)) == [uid]
                bound = bool(sources) and all(matcher.sources[s]['document_id']==did for s in sources)
                goal = {'goal_id':'SG'+str(len(goals)+1),'identity':ident,'issue_id':issue['id'],
                        'document_id':did,'document_name':matcher.documents[did],
                        'coordinate':surface,'coordinate_scope':'body',
                        'reason':'질문과 직접 일치한 저장 표제의 원문을 확인: '+hit['text'],
                        'status':'REQUIRED' if unique and bound else 'BLOCKED',
                        'routes':[] if unique and bound else ['LOOKUP','READ'], 'arrivals':[],
                        'origin_heading':witness}
                if not unique or not bound: goal['route_failure']='AMBIGUOUS_OR_MISSING_BOUND_ORIGINAL'
                existing = next((g for g in goals if g['identity']==ident), None)
                if existing:
                    existing['origin_heading']=witness
                    if existing['status']=='EXCLUDED':
                        existing['prior_exclusion']=existing.pop('exclusion',{})
                        existing['status']='REQUIRED'
                elif len(goals)<16: goals.append(goal)
                else:
                    goal['goal_id']='SCOPE-'+ident[:16];goal['status']='BLOCKED';goal['route_failure']='SOURCE_GOAL_LIMIT'
                    overflow.append(goal)
                discoveries.append({'identity':ident,'document_id':did,'coordinate':surface,'witness':witness})
    refresh(inv,goals)
    st.update(source_goals=goals,scope_discovery={'version':VERSION,'binding':binding,'discoveries':discoveries,'overflow':overflow})
    commit(inv,st)
    inv.s.repo.event('SCOPE_SOURCE_DISCOVERY',{'binding':binding,'discoveries':discoveries,
        'overflow_count':len(overflow),'legal_judgment_adopted':False,'new_model_calls':0})

def before_handoff(inv):
    """Seed before all early handoffs, as well as before ordinary model selection."""
    if not enabled(inv): return
    from .source_goal_control import state
    data={'current_request':inv.record.get('current_request',inv.question),'issues':deepcopy(inv.p.get('issues',[]))}
    discover(inv,data,state(inv,data))

def validate_exclusion(inv, data, goal, row):
    if not goal.get('origin_heading'): return
    from .source_goal_control import refresh
    verified=deepcopy(goal)
    if verified['status']=='EXCLUDED': verified['status']='REQUIRED'
    refresh(inv,[verified])
    if verified['status']!='ACQUIRED':
        from .output_contract import OutputContractError, issue
        problem=issue('DISCOVERED_ORIGINAL_NOT_READ','/source_goal_exclusions',expected='Read the discovered target original first; then review its applicability. Keep it unresolved if unavailable.')
        problem.update(goal_id=goal['goal_id'],message='A reason or another original cannot exclude an unread exact heading matched to the user request.')
        raise OutputContractError('discovered source cannot be excluded before its original is verified',[problem],category='DECISION_CONFLICT')
