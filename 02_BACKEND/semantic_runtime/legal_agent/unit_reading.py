"""Closed structural READ offers shared by bounded and durable legal_agent.

Each hit has an exact own-block read, its own subtree, and ancestor subtrees up
to the canonical article. A paragraph subtree includes every item beneath it.
"""
from collections import defaultdict
from copy import deepcopy
import json
import time
from ..contracts import digest
from ..unit_fulltext import ArticleProjection
from .errors import ContractError, BudgetExhausted
from .. import query_latency as latency

POLICY = {'initial_units':512,'initial_chars':1600000,'read_actions':1024,
          'preview_chars':400,'context_chars':80000,'choices':16,'review_choices':8,
          'batch_groups':12,'group_chars':12000,'group_units':32,'candidate_batches':8,
          'review_rounds':8}


def discover(recall, original):
    matcher = recall.s.matcher
    index = getattr(matcher,'unit_fulltext',None)
    if index is None: raise ContractError('unit-first recall requires an explicitly bound unit index')
    proxy = ArticleProjection(index,matcher.unit_fulltext_db)
    previous = matcher.fulltext
    matcher.fulltext = proxy
    recall.s.batch_reference_navigation = True
    try: selected, record = original()
    finally: matcher.fulltext = previous
    # Retain multiple independently matched units; never a lexical choose-one.
    hits = {}; paths = defaultdict(list)
    for call in proxy.calls:
        for rank, hit in enumerate(call['hits'],1):
            if hit['source_id'] in selected:
                hits.setdefault(hit['key'],hit)
                paths[hit['key']].append({'terms':call['terms'],'unit_rank':rank})
    record['unit_hits'] = [{**h,'match_paths':paths[k]} for k,h in hits.items()]
    record['unit_index_sha256'] = index.manifest['index_sha256']
    record['unit_index_counts'] = index.manifest['counts']
    return selected,record


def blocks(s,did,uid,extent):
    unit = s.matcher.units[(did,str(uid))]
    if extent=='exact':
        return [str(r[0]) for r in s.store.db.execute('SELECT block_id FROM source_block WHERE document_id=? AND unit_id=? ORDER BY CAST(block_id AS INTEGER)',(did,uid))]
    lo,hi = unit['span']
    return [str(r[0]) for r in s.store.db.execute('SELECT block_id FROM source_block WHERE document_id=? AND CAST(block_id AS INTEGER)>=? AND CAST(block_id AS INTEGER)<? ORDER BY CAST(block_id AS INTEGER)',(did,lo,hi))]


def block_lengths(s, did, ids):
    """Request-owned metadata; changed store or permission binding cannot hit."""
    s.store.check_unchanged()
    binding = (s.store, getattr(s.store, '_binding_state', None), frozenset(s.scope))
    if getattr(s, '_unit_block_chars_binding', None) != binding:
        s._unit_block_chars = {}
        s._unit_block_chars_binding = binding
    cache = s._unit_block_chars
    wanted = list(dict.fromkeys(str(b) for b in ids))
    missing = [b for b in wanted if (did,b) not in cache]
    if missing:
        if hasattr(s.store, 'source_lengths'):
            lengths = s.store.source_lengths(did, missing)
        else:
            # Adapters without an exact metadata contract keep their full checks.
            lengths = {b:len(s.store.source(did,b)['text']) for b in missing}
        s.store.check_unchanged()
        if set(lengths) != set(missing):raise ContractError('source length batch is incomplete')
        cache.update({(did,b):n for b,n in lengths.items()})
    return {b:cache[(did,b)] for b in wanted}


def block_chars(s, did, ids):
    lengths = block_lengths(s, did, ids)
    return sum(lengths[str(b)] for b in ids)


def exact_offer(s, hit):
    """Size an unselected hit without walking any ancestor subtree."""
    ids = blocks(s, hit['document_id'], str(hit['unit_id']), 'exact')
    return {'extent': 'exact', 'block_ids': ids,
            'chars': block_chars(s, hit['document_id'], ids)}


def offer_plan(s,hit):
    cache = getattr(s, '_unit_offer_plans', None)
    if cache is None: cache = s._unit_offer_plans = {}
    key = digest(hit)
    if key not in cache: cache[key] = _offer_plan(s, hit)
    from .query_scope import filter_offers
    offers,blocked=deepcopy(cache[key])
    return filter_offers(s,hit,offers,blocked)


def _offer_plan(s,hit):
    if hit.get('source_partition') is not None:
        return [partition_offer(s,hit)],[]
    if hit.get('matched_hits'):
        child_plans = [offer_plan(s, h) for h in hit['matched_hits']]
        owned = set()
        for child, _ in child_plans:
            own = next(o for o in child if o['extent']=='exact')
            owned.update(own['block_ids'])
        # Add introductions on the matched paths, never sibling subtrees.
        did = hit['document_id']; root = str(hit['article_unit_id'])
        article = {str(b['block_id']) for b in s.tools.sources[hit['source_id']]['blocks']}
        for h in hit['matched_hits']:
            current = str(h['unit_id']); seen = set()
            while current is not None:
                if current in seen: raise ContractError('group parent cycle')
                seen.add(current)
                owned.update(set(blocks(s,did,current,'exact')) & article)
                if current == root: break
                current = s.matcher.units[(did,current)].get('parent')
        ids = sorted(owned,key=int)
        grouped = {'id':'matched:'+digest(ids)[:16], 'unit_id':root,'extent':'exact',
            'reader_target':'blocks','label':' / '.join(unit_label(s,h) for h in hit['matched_hits']),
            'block_ids':ids,'block_count':len(ids),
            'chars':block_chars(s,did,ids),
            'description':'검색된 같은 조의 항·호·목과 상위 조건 본문 묶음; 다른 형제 제외',
            'article_complete':set(ids)==article}
        distinct = {o['id']:o for child,_ in child_plans for o in child}
        return [grouped,*distinct.values()], [b for _,blocked in child_plans for b in blocked]
    did,uid,root = hit['document_id'],str(hit['unit_id']),str(hit['article_unit_id'])
    if did not in s.scope or hit['source_id'] not in s.tools.sources:
        raise ContractError('unit hit outside current scope')
    article_blocks = {str(b['block_id']) for b in s.tools.sources[hit['source_id']]['blocks']}
    if root=='None' and uid=='None':
        # Block-only source groups have no invented structural parent. The P
        # reader addresses this immutable source's own blocks directly.
        ids=[str(b['block_id']) for b in s.tools.sources[hit['source_id']]['blocks']]
        return ([{'id':'exact:source','unit_id':None,'extent':'exact',
            'reader_target':'source','label':'구조 마디 없는 원문 블록',
            'block_ids':ids,'block_count':len(ids),
            'chars':block_chars(s,did,ids),
            'description':'이 원문 블록만; 구조 확장 없음','article_complete':True}],[])
    out=[]; blocked=[]; seen=set(); current=uid
    while current is not None:
        if current in seen: raise ContractError('unit parent cycle')
        seen.add(current)
        u=s.matcher.units[(did,current)]
        for extent in (('exact','subtree') if current==uid else ('subtree',)):
            ids=blocks(s,did,current,extent)
            outside=set(ids)-article_blocks
            if outside:
                if extent=='exact':raise ContractError('own unit blocks escape canonical source')
                # Navigation assigns independent source IDs to chapter/section
                # headings. Their stored subtree can contain several articles.
                # Withhold that expansion; never clip it or fail an exact hit.
                blocked.append({'unit_id':current,'extent':extent,
                    'reason':'subtree_crosses_canonical_source_boundary',
                    'outside_block_ids':sorted(outside,key=int)})
                continue
            if not ids: continue
            out.append({'id':extent+':'+current,'unit_id':current,'extent':extent,
                'label':u.get('surface') or u.get('title') or current,
                'block_ids':ids,'block_count':len(ids),
                'chars':block_chars(s,did,ids),
                'description':'해당 단위 본문만' if extent=='exact' else '이 단위와 그 아래 모든 항·호·목',
                'article_complete':current==root and extent=='subtree'})
        if current==root: break
        current=u.get('parent')
    if root not in seen: raise ContractError('hit is not a descendant of its article')
    return out,blocked


def partition_offer(s, hit):
    """Read one complete canonical group of a verified whole structural union.

    A group is never described as completion of the containing coordinate. The
    gap inventory retains all expected blocks and READ_ARTICLES keeps each
    group's own completion receipt and the unchanged shared budget.
    """
    from . import structure_query as sq
    from .repository import text_hash
    did=hit['document_id']; sid=hit['source_id']; binding=hit['source_partition']
    if did not in s.scope or set(binding)!={'scope_unit_id'}:
        raise ContractError('source partition scope mismatch')
    scope_uid=binding['scope_unit_id']
    if scope_uid is not None and (did,str(scope_uid)) not in s.matcher.units:
        raise ContractError('source partition structure missing')
    ids=sq.non_body_sources(s.matcher,did,scope_uid)
    if not ids or sid not in ids:
        raise ContractError('source partition identity missing or ambiguous')
    wanted=(blocks(s,did,str(scope_uid),'subtree') if scope_uid is not None else
            [str(r[0]) for r in s.store.db.execute('SELECT block_id FROM source_block WHERE document_id=? ORDER BY CAST(block_id AS INTEGER)',(did,))])
    original={str(b['block_id']):b for b in s.store.sources(did,wanted)}
    covered=set(); groups={}
    for ident in ids:
        source=s.tools.sources.get(ident)
        if not source or source['document_id']!=did:
            raise ContractError('source partition outside document')
        own=[str(b['block_id']) for b in source['blocks']]
        if not own or len(own)!=len(set(own)) or covered.intersection(own) or set(own)-original.keys():
            raise ContractError('source partition overlap or escaped original')
        if (str(source['unit_id'])!=str(s.matcher.sources[ident]['unit_id']) or
                source.get('text_sha256')!=text_hash('\n'.join(b['text'] for b in source['blocks'])) or
                any(original[str(b['block_id'])]['text']!=b['text'] or
                    original[str(b['block_id'])]['source_artifact_sha256']!=source['source_artifact_sha256']
                    for b in source['blocks'])):
            raise ContractError('source partition original/hash mismatch')
        covered.update(own); groups[ident]=own
    if not wanted or covered!=set(wanted):
        raise ContractError('source partition union is incomplete')
    source=s.tools.sources[sid]
    if str(hit['unit_id'])!=str(source['unit_id']) or str(hit['article_unit_id'])!=str(source['unit_id']):
        raise ContractError('source partition root mismatch')
    own=groups[sid]
    return {'id':'exact:partition:'+digest(binding),'unit_id':str(source['unit_id']) if source['unit_id'] is not None else None,
            'extent':'exact','reader_target':'source_partition','label':source.get('heading') or '연결 원문 그룹',
            'block_ids':own,'block_count':len(own),'chars':sum(len(original[b]['text']) for b in own),
            'description':'선택한 구조를 구성하는 원문 그룹 전체; 다른 그룹의 확보 상태는 별도',
            'article_complete':True,'source_partition':dict(binding),'coordinate_complete':len(ids)==1}


def offers(s,hit):
    return offer_plan(s,hit)[0]


def reassemble(evidence):
    per_block=defaultdict(list)
    for e in evidence:
        for span in e['spans']: per_block[str(span['block_id'])].append(span)
    result=[]
    for bid in sorted(per_block,key=lambda x:(int(x) if x.isdigit() else 0,x)):
        text=''
        for p in sorted(per_block[bid],key=lambda p:(p['start_cp'],p['end_cp'])):
            a,z=p['start_cp'],p['end_cp']
            if len(p['text'])!=z-a or a>len(text): raise ContractError('unit evidence gap')
            n=max(0,min(len(text),z)-a)
            if text[a:a+n]!=p['text'][:n]: raise ContractError('unit evidence overlap conflict')
            text+=p['text'][n:]
        result.append(text)
    return '\n'.join(result)


def read_state(s, supplied=None):
    """One ledger owns the read budget and action sequence across re-entry."""
    state = getattr(s, '_unit_read_state', None)
    if state is None:
        state = s._unit_read_state = {'count': 0, 'chars': 0, 'sequence': 0}
        tables = {r[0] for r in s.repo.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        table = 'action_context' if 'action_context' in tables else 'action_receipt'
        if table in tables:
            ids = [r[0] for r in s.repo.db.execute('SELECT action_id FROM '+table+" WHERE action_id LIKE 'unit-read-%'")]
            numbers = [int(i.rsplit('-', 1)[1]) for i in ids if i.rsplit('-', 1)[1].isdigit()]
            state['sequence'] = max(numbers, default=0)
            state['count'] = len(ids)
    if supplied is not None:
        for key in ('count', 'chars', 'sequence'):
            state[key] = max(state[key], supplied.get(key, 0))
        supplied.update(state)
        return supplied
    return dict(state)


def activity_context(s, hit, offer):
    locations = ([unit_label(s, h) for h in hit['matched_hits']]
                 if offer.get('reader_target') == 'blocks' and hit.get('matched_hits')
                 else [unit_label(s, {**hit, 'unit_id': offer['unit_id']})
                       if offer['unit_id'] is not None else offer['label']])
    return {'document_id': hit['document_id'], 'document_name': hit['document_name'],
        'location': locations[0], 'locations': list(dict.fromkeys(locations)),
        'extent': offer['extent'], 'block_count': offer['block_count'], 'chars': offer['chars']}


def failed_read(s,error,ids,target,cursor,action_state):
    """Keep earlier committed pages separate from the failed page's outcome."""
    error.read_progress={'completed_receipt_refs':list(dict.fromkeys(ids)),
        'remaining_target':{'target':target,'cursor':cursor},'read_state':dict(action_state)}
    try:
        s.repo.event('UNIT_READ_FAILED',error.read_progress)
    except Exception as storage_error:
        from .tool_outcome import exception_outcome
        from .errors import ToolExecutionError
        outcome=exception_outcome(storage_error,action={'tool':'read','args':{'target':target,'cursor':cursor}},
            binding_hash=s.context.binding_hash,execution='UNKNOWN',effects='UNKNOWN')
        raise ToolExecutionError('read progress could not be saved',outcome=outcome) from error


@latency.timed('law.read.original')
def read(s,hit,offer,*,action_state):
    current={x['id']:x for x in offers(s,hit)}
    if offer['id'] not in current or current[offer['id']]!=offer:
        raise ContractError('unoffered or stale READ extent')
    read_state(s, action_state)
    activity = activity_context(s, hit, offer)
    s.repo.event('UNIT_READ_STARTED', activity)
    from .source_recall import spans_complete
    from .repository import text_hash
    wanted = set(offer['block_ids']); existing=[]
    for e in s.repo.evidence():
        if e['source_id'] != hit['source_id']: continue
        spans = [p for p in e['spans'] if str(p['block_id']) in wanted]
        if not spans: continue
        s.source.verify(e)
        if len(spans) != len(e['spans']):
            e = {**e, 'spans': spans, 'text_hash': text_hash('\n'.join(p['text'] for p in spans))}
            e['evidence_id'] = 'E'+digest({k:v for k,v in e.items() if k!='evidence_id'})[:28]
            s.repo.record_observation({'tool':'unit_evidence_projection','args':{'source_id':hit['source_id'],'scope':offer['id']}},
                {'status':'REUSED'}, [e], verify=s.source.verify)
        existing.append(e)
    source = {'id': hit['source_id'], 'blocks': s.store.sources(hit['document_id'], offer['block_ids'])}
    segments=[];known_ranges=defaultdict(list)
    for e in existing:
        for p in e['spans']:known_ranges[str(p['block_id'])].append((p['start_cp'],p['end_cp']))
    for raw in source['blocks']:
        bid=str(raw['block_id']); end=0
        ranges=sorted(known_ranges[bid])
        for lo,hi in ranges:
            if lo>end: segments.append({'block_id':bid,'start_cp':end,'end_cp':lo})
            end=max(end,hi)
        if end<len(raw['text']):segments.append({'block_id':bid,'start_cp':end,'end_cp':len(raw['text'])})
    new_chars=sum(p['end_cp']-p['start_cp'] for p in segments)
    if action_state['chars']+new_chars>POLICY['initial_chars']:
        raise BudgetExhausted('unit read character budget')
    ids=[e['evidence_id'] for e in existing]; receipts=[]
    if segments:
        target=s.handle('P',{'document_id':hit['document_id'],'unit_id':None,'source_id':hit['source_id'],
            'block_ids':list(dict.fromkeys(p['block_id'] for p in segments)),
            'read_segments':segments,'read_label':offer['label']})
        cursor=None
        while True:
            s.context.remaining()
            if action_state['count']>=POLICY['read_actions']:raise BudgetExhausted('unit read action budget')
            action={'tool':'read','args':{'target':target,'extent':offer['extent'],'cursor':cursor},
                'reason':'선택 범위에서 아직 확보하지 않은 원문 구간 확인','question_refs':[],
                'expected_information':'선택 범위의 원문·조건·예외; 기존 검증 구간은 재사용'}
            action_state['sequence']+=1
            s._unit_read_state.update(action_state)
            action_id='unit-read-'+str(action_state['sequence'])
            reserved_before=s.repo.budget()['tool_used']
            try:
                result=s.execute(action,action_id,actor='SYSTEM_POLICY')
            except Exception as error:
                # Reservations remain spent even if no result reaches this
                # caller. Completed earlier pages already have their receipts.
                action_state['count']+=max(0,s.repo.budget()['tool_used']-reserved_before)
                s._unit_read_state.update(action_state)
                failed_read(s,error,ids,target,cursor,action_state)
                raise
            action_state['count']+=1;action_state['chars']+=result.get('budget',{}).get('new_read_chars',0)
            s._unit_read_state.update(action_state)
            receipts.append({'source_id':hit['source_id'],'action':action,'result':result})
            if result['status'] in ('ERROR','NOT_EXECUTED','DENIED','UNKNOWN'):
                from .tool_outcome import normalize_result
                from .errors import ToolExecutionError
                outcome=normalize_result(result,action=action,binding_hash=s.context.binding_hash,action_id=action_id)
                error=ToolExecutionError('unit READ failed: '+str(outcome.cause_code),outcome=outcome)
                failed_read(s,error,ids,target,cursor,action_state)
                raise error
            ids.extend(i['evidence'] for i in result.get('items',[]) if i.get('evidence'))
            checkpoint=getattr(s,'_unit_read_checkpoint',None)
            if checkpoint:checkpoint([s.repo.evidence(eid) for eid in result.get('evidence_ids',[])],dict(action_state))
            cursor=result.get('next_cursor')
            if not cursor:break
    es=[s.repo.evidence(eid) for eid in dict.fromkeys(ids)]
    actual={str(p['block_id']) for e in es for p in e['spans']}
    if actual-wanted or any(e['source_id']!=hit['source_id'] for e in es):raise ContractError('unit READ escaped requested blocks')
    for e in es:s.source.verify(e)
    complete=spans_complete(source,es) and (not segments or result.get('coverage',{}).get('complete') is True)
    s.repo.event('UNIT_READ_FINISHED',{**activity,'complete':complete,'reused':not segments,'new_chars':new_chars})
    if not segments:s.repo.event('UNIT_READ_REUSED',{'source_id':hit['source_id'],'scope':offer['id'],'evidence_ids':ids})
    return {'key':hit['key'],'source_id':hit['source_id'],'document_id':hit['document_id'],
        'unit_id':hit['unit_id'],'article_unit_id':hit['article_unit_id'],'offer':offer,
        'complete':complete,'text':reassemble(es),'evidence_ids':[e['evidence_id'] for e in es],
        'evidence':es,'actions':receipts,'document_name':hit['document_name'],'heading':hit['heading']}


def unit_label(s, hit):
    uid = str(hit['unit_id']); parts = []; seen = set()
    while uid != 'None':
        if uid in seen: raise ContractError('unit label parent cycle')
        seen.add(uid)
        u = s.matcher.units[(hit['document_id'],uid)]
        parts.append(u.get('surface') or u.get('title') or uid)
        if uid == str(hit['article_unit_id']) or u.get('parent') is None: break
        uid = str(u['parent'])
    return ' '.join(reversed(parts)) or hit.get('heading','원문 블록')


def group_hits(s, queue):
    grouped = defaultdict(list)
    for h in queue: grouped[h['source_id']].append(h)
    result = []
    for sid, hits in grouped.items():
        chunk = []; chars = 0
        def flush():
            if len(chunk)==1: result.append(chunk[0])
            elif chunk:
                first=chunk[0]
                result.append({**first,'key':sid+'#matched:'+digest([h['key'] for h in chunk])[:16],
                    'unit_id':first['article_unit_id'],'matched_hits':list(chunk),
                    'match_paths':[p for h in chunk for p in h.get('match_paths',[])]})
        for h in hits:
            own=exact_offer(s,h)
            if chunk and (chars+own['chars']>POLICY['group_chars'] or len(chunk)>=POLICY['group_units']):
                flush();chunk=[];chars=0
            chunk.append(h);chars+=own['chars']
        flush()
    buckets = defaultdict(list)
    for h in result: buckets[h['source_id']].append(h)
    return [bucket[i] for i in range(max((len(v) for v in buckets.values()),default=0))
            for bucket in buckets.values() if i<len(bucket)]


def acquire_batch(s, hits, state):
    reads=[]
    unique={(h['key'],h.get('requested_unit_id')):h for h in hits}
    for h in unique.values():
        s.context.remaining()
        opts,blocked=offer_plan(s,h);own=next((o for o in opts if o['extent']=='exact'),None)
        if own is None:raise ContractError('hit has no own original blocks')
        r=read(s,h,own,action_state=state)
        reads.append({**r,'hit':h,'offers':opts,'unavailable_read_options':blocked})
    return reads


def prepare(recall):
    from .source_recall import spans_complete, evidence_packets
    s=recall.s; selected,discovery=recall.discover()
    by_source=defaultdict(list)
    for h in discovery.get('unit_hits',[]): by_source[h['source_id']].append(h)
    if discovery.get('discovery_mode')=='structure':
        for pair in discovery.get('structure_query',{}).get('pairs',[]):
            did,uid=pair['document_id'],str(pair['unit_id'])
            for sid in s.matcher._unit_sources(did,uid):
                if sid in selected and blocks(s,did,uid,'exact'):
                    src=s.tools.sources[sid]
                    by_source[sid].append({'key':sid+'#unit:'+uid,'source_id':sid,'document_id':did,'unit_id':uid,'article_unit_id':str(src['unit_id']),'document_name':src['document_name'],'heading':src.get('heading',''),'entry_reason':'exact_structural_coordinate','match_paths':[]})
    queue=[]; deferred=[]
    from ..fulltext import question_terms
    terms = set(question_terms(s.context.request['question']))
    for query in getattr(s, 'recall_query_plan', {}).get('queries', []):
        terms.update(question_terms(query))
    # Fair first unit per article, then all remaining matched units up to budget.
    for sid in selected:
        if not by_source[sid]:
            source=s.tools.sources[sid]; did=source['document_id'];root=str(source['unit_id'])
            candidates=[]
            for raw in s.store.sources(did, [b['block_id'] for b in source['blocks']]):
                uid=str(raw.get('unit_id') or root)
                # Compatibility with article-only FTS: preserve every matching
                # owning unit, without reading an entire annex just to preview it.
                if discovery.get('discovery_mode') != 'structure' and not any(t in raw['text'] for t in terms):
                    continue
                key=sid+'#unit:'+uid
                if key not in {x['key'] for x in candidates}:
                    candidates.append({'key':key,'source_id':sid,'document_id':did,'unit_id':uid,
                        'article_unit_id':root,'document_name':source['document_name'],'heading':source.get('heading',''),
                        'match_paths':[],'entry_reason':'reference_or_structure_entry_no_lexical_hit'})
            if not candidates:
                candidates=[{'key':sid+'#unit:'+root,'source_id':sid,'document_id':did,
                    'unit_id':root,'article_unit_id':root,'document_name':source['document_name'],
                    'heading':source.get('heading',''),'match_paths':[],
                    'entry_reason':'structure_or_title_entry_no_body_match'}]
            by_source[sid]=candidates
    queue=[by_source[sid][0] for sid in selected if by_source[sid]]
    queue += [h for sid in selected for h in by_source[sid][1:]]
    queue=group_hits(s,queue)
    deferred=[h['key'] for h in queue[POLICY['initial_units']:]]
    queue=queue[:POLICY['initial_units']]
    pending=queue[POLICY['batch_groups']:]
    state=read_state(s)
    reads=acquire_batch(s,queue[:POLICY['batch_groups']],state)
    evidence=s.repo.evidence()
    complete=[sid for sid in selected if spans_complete(s.tools.sources[sid],evidence)]
    eligible=list(dict.fromkeys(r['source_id'] for r in reads if r['complete']))
    record={**discovery,'unit_read_contract':'unit-read-v1','unit_reads':reads,
        'acquisition_mode':'progressive-grouped-v1','pending_unit_hits':pending,
        'candidate_group_count':len(queue),'candidate_unit_count':sum(len(h.get('matched_hits',[h])) for h in queue),
        'selected_for_read':selected,'read_complete':complete,'read_partial':[sid for sid in selected if sid not in complete],
        'selection_complete':eligible,'prepared_complete':eligible,'selection_evidence_ids':list(dict.fromkeys(e for r in reads if r['complete'] for e in r['evidence_ids'])),
        'source_chars':state['chars'],'read_state':dict(state),'actions':[a for r in reads for a in r['actions']],
        'packets':evidence_packets(s.context.request['question'],evidence,50000),
        'limits':[{'kind':'initial_unit_limit','unread_units':deferred}] if deferred else [],
        'actual_model_presented':[],'seconds':time.monotonic()-recall.start}
    s.repo.event('UNIT_SOURCE_RECALL_FINISHED',{'units':len(reads),'selection_complete':eligible,
        'article_read_complete':complete,'deferred':deferred,'index_sha256':discovery.get('unit_index_sha256')})
    return record


def ensure_context(s, selected, state):
    """Read ancestor introductions/attached provisos, never unrelated siblings."""
    from .unit_relations import hit_for
    existing = defaultdict(set)
    for r in selected.values():
        existing[r['source_id']].update(str(p['block_id']) for e in r['evidence'] for p in e['spans'])
    for r in list(selected.values()):
        uid = r['offer']['unit_id']
        if uid is None or str(uid) == str(r['article_unit_id']): continue
        current = s.matcher.units[(r['document_id'], str(uid))].get('parent')
        seen = set()
        while current is not None:
            if current in seen: raise ContractError('context parent cycle')
            seen.add(current)
            h = hit_for(s, r['source_id'], current)
            from . import query_scope as qs
            if qs.active(s) and r.get('complete'):
                child_blocks=set(map(str,r['offer']['block_ids']))
                if child_blocks <= qs.permitted_blocks(s,r['source_id']):
                    own_ids=set(blocks(s,r['document_id'],str(current),'exact')) & {str(b['block_id']) for b in s.tools.sources[r['source_id']]['blocks']}
                    qs.grant(s,r['source_id'],own_ids,witness={'kind':'STRUCTURAL_ANCESTOR',
                        'acquired_unit_id':uid,'parent_unit_id':current,'evidence_ids':r['evidence_ids']})
            candidates, _ = offer_plan(s, h)
            own = next((o for o in candidates if o['extent'] == 'exact'), None)
            if own and not set(own['block_ids']) <= existing[r['source_id']]:
                context = read(s, h, own, action_state=state)
                if not context['complete']: raise ContractError('governing context not fully read')
                selected['CONTEXT:' + h['key']] = context
                existing[r['source_id']].update(own['block_ids'])
            if str(current) == str(r['article_unit_id']): break
            current = s.matcher.units[(r['document_id'], str(current))].get('parent')


def original_map(reads):
    groups=defaultdict(list)
    for r in reads:
        if r['complete']:groups[r['source_id']].append(r)
    result={}
    for sid,rs in groups.items():
        evidence={e['evidence_id']:e for r in rs for e in r['evidence']}
        result[sid]={'source_id':sid,'document_id':rs[0]['document_id'],'unit_id':rs[0]['article_unit_id'],
            'document_name':rs[0]['document_name'],'heading':rs[0]['heading'],'text':reassemble(evidence.values()),
            'evidence_ids':list(evidence),'read_scopes':[r['offer'] for r in rs],
            'article_complete':any(r['offer']['article_complete'] for r in rs)}
    return result


def selected_originals(parts):
    """New SELECT scopes replace initial READ previews; old routes stay readable."""
    return parts.get('SELECT',{}).get('payload',{}).get('selected_originals',parts['READ']['payload']['originals'])
