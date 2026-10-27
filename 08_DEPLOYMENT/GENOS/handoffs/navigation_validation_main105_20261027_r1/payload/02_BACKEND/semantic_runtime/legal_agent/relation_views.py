"""Budgeted projections with durable, request-bound continuation snapshots."""
from collections import Counter
from .repository import encoded
from .errors import BudgetExhausted


def menu_card(n):
    return {k:n[k] for k in ('relation_id','anchor','family','predicate','direction',
        'resolution','completion_required','scope_status')} | {
        'targets':[{'target':t['target'],'document_name':t['document_name'],
                    'coordinate':t.get('coordinate'),'title':t.get('title')} for t in n['targets']],
        'target_count':len(n['targets']), 'unresolved':n.get('unresolved',False),
        'notice_presented':False,
        'inspect_action':{'tool':'inspect_relation','args':{'relation_id':n['relation_id']}}}


def build_view(s, phase, required, extra):
    required=list(dict.fromkeys(required))
    if phase!='investigate':
        for h in s.work.heads('relation_assessment',current=True):
            a=h['payload']
            if set(a['source_evidence']) & set(required):
                required=list(dict.fromkeys(required+a['source_evidence']+a['target_evidence']))
    observations=list(reversed(s.work.observations(s.profile['max_tool_actions'])))
    recent=observations[:8]
    focus=next((o for o in observations if o.get('actor') in ('MODEL','REVIEWER')),None)
    preferred=list(dict.fromkeys(required+[e for o in observations for e in o.get('evidence_ids',[])]))
    exact=[]
    for ident in preferred:
        e=s.work.evidence(ident)
        exact.append({'evidence':ident,'text':e['text'],'spans':e['spans'],'text_hash':e['text_hash'],
            'source_id':e['source_id'],'document_name':e['metadata'].get('document_name'),
            'role':e['role'],'temporal_status':e['temporal_status'],**s.sources.location(ident)})
    notices=s.work.notices()
    mandatory={n['relation_id'] for n in notices if phase!='investigate' and n['completion_required']
               and set(n['source_evidence']) & set(required)}
    focused={n['relation_id'] for n in (focus or {}).get('items',[]) if isinstance(n,dict) and n.get('notice_hash')}
    many=len(notices)>s.profile['relation_page_size']
    full=[n for n in notices if not many or n['relation_id'] in mandatory|focused]
    full.sort(key=lambda n:(n['relation_id'] not in mandatory,n['relation_id'] not in focused))
    sections={'exact_evidence':exact, 'relation_notices':full,
        'relation_menu':[menu_card(n) for n in notices] if many else [],
        'last_action_results':[], 'relation_assessments':s.work.heads('relation_assessment',current=True),
        'assessments':s.work.heads('assessment',current=True),'questions':s.work.heads('intent',current=True),
        'coverage':[{k:v for k,v in row.items() if k!='assessments'} |
                    {'assessment_count':len(row['assessments'])} for row in s.work.coverage()]}
    preview_left=s.profile['max_preview_chars']
    def trim(v):
        nonlocal preview_left
        if isinstance(v,list): return [trim(x) for x in v]
        if not isinstance(v,dict): return v
        out={k:trim(x) for k,x in v.items() if k not in ('text','spans','metadata_json','preview_spans')}
        if 'preview_spans' in v:
            chars=sum(len(p['text']) for p in v['preview_spans'])
            if chars<=preview_left:
                out['preview_spans']=v['preview_spans']; preview_left-=chars
            else: out.update(preview_spans=[],suppressed_reason='VIEW_PREVIEW_BUDGET')
        return out
    # Model-requested results outrank policy traces. Each item can be paged independently.
    ordered=sorted(recent,key=lambda o:o.get('actor')=='SYSTEM_POLICY')
    for o in ordered:
        shell={k:v for k,v in o.items() if k in ('observation_id','tool','status','action','next_cursor',
            'evidence_ids','actor','server_reason','view_section','scan_anchor','scan_family','scan_status')}
        items=[] if o.get('view_section') else [trim(x) for x in o['items'] if not x.get('relation_id')]
        chunks=[items[i:i+4] for i in range(0,len(items),4)] or [[]]
        for i,chunk in enumerate(chunks):
            sections['last_action_results'].append({**shell,'items':chunk,'item_offset':i*4,
                'item_total':len(items),'result_complete':len(chunks)==1,
                **({'search_receipt':o['search_receipt']} if i==0 and o.get('search_receipt') else {})})
    focused_section=(focus or {}).get('view_section')
    if focused_section:
        remaining=[]
        if focus.get('next_cursor'):
            _,position=s.sources.source.cursor_position({'tool':'view_page','args':{
                'section':focused_section,'cursor':focus['next_cursor']}})
            remaining=position['items']
        # Continue the immutable suffix, never reinsert the earlier pages ahead of it.
        sections[focused_section]=focus['items']+remaining
    # Reserve all navigation before filling payloads: omission metadata cannot overflow later.
    continuations=[{'section':k,'remaining':len(v),'action':{'tool':'view_page',
        'args':{'section':k,'cursor':'P'+'0'*28}}} for k,v in sections.items() if v]
    body={'original_question':s.context.request['question'],'question_pieces':s.context.pieces,
        'corpus_root':s.sources.root,'tool_capabilities':s.sources.capabilities,
        **{k:[] for k in sections}, 'continuations':continuations,
        'relation_counts':dict(Counter(n['family'] for n in notices)),
        'relation_selection_required':many, 'omitted_evidence':[], 'omitted_relations':[],
        'omitted_action_results':[{'observation_id':o['observation_id'],'tool':o['tool'],
            'status':o['status']} for o in recent],
        'budgets':s.work.budget(),'errors':[{**e,'message':e['message'][:2000]} for e in s.errors[-2:]],**(extra or {})}
    name={'investigate':'TurnDecision','compose':'Draft','review':'ReviewDecision','rebuttal':'Rebuttal'}[phase]
    def fits():
        return len(encoded(body))+256<=s.profile['max_context_chars']
    if not fits(): raise BudgetExhausted('question and protocol exceed input budget before source presentation')
    def add(section,item):
        body[section].append(item)
        if fits(): return True
        body[section].pop(); return False
    # Required joint review sources are indivisible exact receipts, never shortened in place.
    for item in exact:
        if item['evidence'] in required and not add('exact_evidence',item):
            raise BudgetExhausted('joint source/target evidence does not fit view; narrow or defer this claim')
    for n in full:
        if n['relation_id'] in mandatory:
            if not add('relation_notices',n): raise BudgetExhausted('required relation review does not fit view; defer this claim')
    order=list(sections)
    if focused_section:
        order.remove(focused_section);order.insert(0,focused_section)
    elif focus and focus['tool'] not in ('read','inspect_relation'):
        order.remove('last_action_results');order.insert(0,'last_action_results')
    omitted={}
    for section in order:
        omitted[section]=[]
        for item in sections[section]:
            if item in body[section]: continue
            if section=='relation_menu' and len(body[section])>=s.profile['relation_page_size']:
                omitted[section].append(item); continue
            if not add(section,item): omitted[section].append(item)
    body['continuations']=[{**c,'remaining':len(omitted[c['section']]),'action':{'tool':'view_page',
        'args':{'section':c['section'],'cursor':s.sources.page_token(c['section'],omitted[c['section']])}}}
        for c in continuations if omitted[c['section']]]
    missing={o['observation_id'] for o in omitted['last_action_results']}
    body['omitted_action_results']=[o for o in body['omitted_action_results'] if o['observation_id'] in missing]
    # State flags can be computed only after the exact evidence page is finalized.
    shown=[e['evidence'] for e in body['exact_evidence']]
    for i,n in enumerate(body['relation_notices']):
        decorated={**n,**s.relation_state(n,shown)}
        body['relation_notices'][i]=decorated
        if not fits(): body['relation_notices'][i]=n
    if not fits(): raise BudgetExhausted('view envelope exceeds input budget')
    return s.work.save_view(phase,body,shown)
