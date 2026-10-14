"""Bounded v4 projections; exact E receipts remain compatible with the source ledger."""
import json
from ..contracts import digest
from .repository import encoded
from .errors import BudgetExhausted


def span_choices(e, maximum):
    result=[]
    for p in e['spans']:
        for start in range(p['start_cp'],p['end_cp'],maximum):
            end=min(start+maximum,p['end_cp'])
            value={'evidence_id':e['evidence_id'],'block_id':p['block_id'],'start_cp':start,'end_cp':end,
                'block_hash':p['block_hash']}
            result.append({'span_id':'SP'+digest(value)[:28],**value})
    return result


def menu(s,n):
    source=[]
    for ident in n['source_evidence']:
        e=s.work.evidence(ident)
        source.append({'name':e['metadata']['document_name'],**s.sources.location(ident)})
    labels={k:n[k] for k in ('term','label','neighbour_term','neighbour_label','term_label','anchor_term','subject','via_concept','neighbour_concept','predicate_label') if k in n}
    if n.get('anchor_term') in s.sources.tools.terms:
        labels['anchor_term_label']=s.sources.tools.terms[n['anchor_term']]['label']
    if n.get('subject') in s.sources.tools.terms:
        labels['subject_label']=s.sources.tools.terms[n['subject']]['label']
    for key in ('via_concept','neighbour_concept'):
        if isinstance(labels.get(key),dict):
            c=labels[key];labels[key]={k:c[k] for k in ('id','label','labels','name','source') if k in c}
    return {'relation_id':n['relation_id'],'semantic_hash':n.get('semantic_hash',n['notice_hash']),
        'family':n['family'],'predicate':n['predicate'],'direction':n['direction'],
        'source_label':source or labels,'source_coordinate':source,
        'witness_excerpt':[{'block_id':p['block_id'],'start_cp':p['start_cp'],
                            'text':p.get('text','')[:180]} for p in n['witness_spans'][:2]],
        'target_labels':[{'name':t['document_name'],'coordinate':t.get('coordinate'),
                          'title':t.get('title'),'target':t['target']} for t in n['targets'][:4]],
        'concept_labels':labels,'target_kind':'CONCEPT' if n.get('neighbour_concept') or n.get('via_concept') else 'SOURCE',
        'resolution':n['resolution'],'scope_status':n['scope_status'],
        'authority_status':'APPROVED' if n.get('canonical_approval') else 'UNAPPROVED',
        'coverage_status':'PARTIAL' if len(n['targets'])>4 else 'MENU_ONLY',
        'remaining_target_count':max(0,len(n['targets'])-4),
        'presentation_status':'MENU_ONLY','guidance':n.get('guidance',''),
        'priority_reasons':['DIRECT_SOURCE_CONNECTION'] if source else ['LEXICAL_HINT'],
        'detail_action':{'tool':'inspect_relation','args':{'relation_id':n['relation_id']}}}


def detail_pages(notice,limit):
    """Lossless JSON slices of a canonical fact; fragments never certify full review."""
    raw=encoded(notice)
    if len(raw)<=limit:return [notice]
    return [{'relation_id':notice['relation_id'],'detail_hash':notice['notice_hash'],
        'detail_format':'CANONICAL_JSON_FRAGMENT','start_cp':start,'end_cp':min(start+limit,len(raw)),
        'total_chars':len(raw),'fragment':raw[start:start+limit]}
        for start in range(0,len(raw),limit)]


def build(s,phase):
    final=phase=='select_sources'; name='SourceSelectionDecision' if final else 'TurnDecision'
    obs=list(reversed(s.work.observations(s.profile['max_tool_actions'])))
    focus=next((o for o in obs if o.get('actor')=='MODEL'),None)
    evidence=list(reversed(s.work.evidence()))
    if final:
        shown={r[0] for r in s.work.db.execute("SELECT DISTINCT p.evidence_id FROM presentation p JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED'")}
        evidence=[e for e in evidence if e['evidence_id'] in shown]
    preferred=(focus or {}).get('evidence_ids',[])
    evidence.sort(key=lambda e:e['evidence_id'] not in preferred)
    exact=[{'evidence':e['evidence_id'],'text':e['text'],'spans':e['spans'],'text_hash':e['text_hash'],
            'source_id':e['source_id'],'document_name':e['metadata']['document_name'],**s.sources.location(e['evidence_id'])} for e in evidence]
    notices=s.work.notices()
    sections={'exact_evidence':exact,'relation_menu':[menu(s,n) for n in notices],
              'relation_notices':[],'last_action_results':[]}
    if focus and focus['tool']=='inspect_relation':
        sections['relation_notices']=[p for n in focus['items'] for p in detail_pages(n,max(256,s.profile['max_context_chars']//8))]
    # Preserve names and concept label text. Drop only source copies already carried by exact_evidence.
    if not final:
        for o in obs[:2]:
            shell={k:v for k,v in o.items() if k in ('observation_id','tool','status','next_cursor','action','evidence_ids','server_reason','view_section')}
            items=[] if o.get('view_section') or o['tool'] in ('read','inspect_relation') else o['items']
            for i in range(0,max(1,len(items)),4):
                sections['last_action_results'].append({**shell,'items':items[i:i+4],'item_offset':i,'item_total':len(items)})
        if focus and focus.get('view_section') in sections:
            section=focus['view_section']; remaining=[]
            if focus.get('next_cursor'):
                _,pos=s.sources.source.cursor_position({'tool':'view_page','args':{'section':section,'cursor':focus['next_cursor']}})
                remaining=pos['items']
            sections[section]=focus['items']+remaining
    body={'original_question':s.context.request['question'],'question_pieces':s.context.pieces,
        'goal_id':s.goal_id,'question_revision':1,'corpus_root':s.sources.root,
        'mode':'RECOVER' if final else 'READ_FOCUS' if preferred else 'EXPLORE',
        'limits':{k:s.profile[k] for k in ('max_core_sources','max_supplemental_sources','max_source_excerpt_chars')},
        'budgets':s.work.budget(),'errors':s.errors[-2:],'selection_state':s.selection_summary(),
        'continuations':[], 'selectable_spans':[], **{k:[] for k in sections}}
    # Reserve cursor envelope before filling; actual tokens are fixed-size opaque identifiers.
    body['continuations']=[{'section':k,'remaining':len(v),'action':{'tool':'view_page','args':{'section':k,'cursor':'P'+'0'*28}}} for k,v in sections.items() if v and not final]
    def fits():
        return len(encoded(body))+512<=s.profile['max_context_chars']
    if not fits(): raise BudgetExhausted('v4 question and protocol exceed wire budget')
    omitted={}
    order=list(sections)
    if focus and focus.get('view_section') in sections:
        order.remove(focus['view_section']); order.insert(0,focus['view_section'])
    elif not preferred and not final:
        order.remove('last_action_results'); order.insert(0,'last_action_results')
    for section in order:
        omitted[section]=[]
        cap=s.profile['source_page_size'] if section=='exact_evidence' else s.profile['relation_page_size']
        for item in sections[section]:
            choices=span_choices(s.work.evidence(item['evidence']),s.profile['max_source_excerpt_chars']) if section=='exact_evidence' else []
            if len(body[section])>=cap: omitted[section].append(item); continue
            body[section].append(item); body['selectable_spans'].extend(choices)
            if not fits():
                body[section].pop()
                if choices: del body['selectable_spans'][-len(choices):]
                omitted[section].append(item)
    body['continuations']=[{'section':k,'remaining':len(v),'action':{'tool':'view_page',
        'args':{'section':k,'cursor':s.sources.page_token(k,v)}}} for k,v in omitted.items() if v and not final]
    body['omitted_counts']={k:len(v) for k,v in omitted.items()}
    body['offered_handles']=sorted({s.sources.root}|s.offered_handles(body))
    body['relation_details']=[n for n in body['relation_notices'] if n.get('detail_format')]
    body['relation_notices']=[n for n in body['relation_notices'] if not n.get('detail_format')]
    if not fits(): raise BudgetExhausted('v4 presentation metadata exceeds wire budget')
    return s.work.save_view(phase,body,[e['evidence'] for e in body['exact_evidence']])
