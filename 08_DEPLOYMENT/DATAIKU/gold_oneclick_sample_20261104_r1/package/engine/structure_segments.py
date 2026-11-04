"""Structure-first, lossless inputs; oversized leaves keep contiguous coordinates."""
import hashlib
import json
import re
from gold_io import Stop, canonical, digest

POLICY = {'version': 'stored-structure-context-v2', 'max_input_chars': 8000,
          'short_source': 'whole',
          'long_source': 'stored_children_sentences_clauses_words_contiguous_spans',
          'context': 'bounded_ancestor_text_with_full_source_links', 'overflow': 'FAIL'}


def text_of(parts):
    return '\n'.join(p['text'] for p in parts)


def units_for(store, did, ids):
    result = {}
    wanted = set(ids)
    while wanted:
        fetched = {}
        ordered = sorted(wanted)
        for offset in range(0, len(ordered), 200):
            group = ordered[offset:offset+200]
            rows = store.execute('SELECT unit_id,parent_id,json FROM source_unit WHERE document_id=? '
                                 'AND unit_id IN ('+','.join('?' for _ in group)+')', (did, *group))
            for uid, parent, raw in rows:
                uid = str(uid); parent = str(parent) if parent is not None else None
                unit = json.loads(raw)
                if ('id' in unit and str(unit['id']) != uid) or ('parent' in unit and (str(unit['parent']) if unit['parent'] is not None else None) != parent):
                    raise Stop('VECTOR_STRUCTURE_ID_OR_PARENT_MISMATCH:'+did+':'+uid)
                fetched[uid] = dict(unit, parent=parent)
        if set(fetched) != wanted:
            raise Stop('VECTOR_STRUCTURE_UNIT_MISSING:'+did)
        result.update(fetched)
        wanted = {u['parent'] for u in fetched.values() if u['parent'] is not None and u['parent'] not in result}
    for uid in result:
        seen = set(); current = uid
        while current is not None:
            if current in seen:
                raise Stop('VECTOR_STRUCTURE_CYCLE:'+did)
            seen.add(current); current = result[current]['parent']
    return result


def title(unit):
    return ' '.join(dict.fromkeys(str(unit.get(k) or '') for k in ('surface', 'title'))).strip()


def sentence_parts(part):
    """Partition at complete sentences/lines only, retaining every character."""
    body = part['text']; start = 0
    # A numeric decimal or a Korean legal reference is not a sentence ending.
    for match in re.finditer(r'(?:[.!?。！？](?:[\"\'”’」』)]*)(?=\s|$)|\n+)', body):
        end = match.end()
        if end > start:
            yield dict(part, start=part['start']+start, end=part['start']+end, text=body[start:end])
            start = end
    if start < len(body):
        yield dict(part, start=part['start']+start, end=part['end'], text=body[start:])


def bounded_parts(part, limit):
    """Keep every code point; prefer clause/word boundaries within long sentences."""
    if limit < 1:
        raise Stop('VECTOR_NO_BODY_CAPACITY')
    body = part['text']; start = 0
    while len(body)-start > limit:
        end = start+limit
        window = body[start:end]
        # Avoid a tiny leading fragment when a later word boundary is available.
        clauses = list(re.finditer(r'[,;:，；、]\s*|[\t\n]+', window))
        words = list(re.finditer(r'\s+', window))
        boundary = next((m.end() for matches in (clauses, words)
                         for m in reversed(matches) if m.end() >= limit//2), None)
        if boundary is not None:
            end = start+boundary; mode = 'clause_or_word'
        else:
            mode = 'contiguous_text'
        yield dict(part, start=part['start']+start, end=part['start']+end,
                   text=body[start:end], split_boundary=mode)
        start = end
    if start < len(body) or not body:
        yield dict(part, start=part['start']+start, end=part['end'],
                   text=body[start:], split_boundary='continuation_tail')


def source_segments(store, source, version, migration, policy=None):
    policy = POLICY if policy is None else policy
    maximum = policy['max_input_chars']
    did, sid = source['document_id'], source['id']
    root = str(source['unit_id']) if source['unit_id'] is not None else '@source'
    bids = [str(b['block_id']) for b in source['blocks']]
    if len(bids) != len(set(bids)):
        raise Stop('VECTOR_SOURCE_BLOCK_DUPLICATE:'+sid)
    parts = []
    from semantic_runtime.oracle_dp_io import COLUMNS
    for offset in range(0, len(bids), 100):
        group = bids[offset:offset+100]
        rows = store.execute('SELECT * FROM block_payload WHERE document_id=? AND block_id IN ('+
                             ','.join('?' for _ in group)+')', (did, *group)).fetchall()
        records = {str(r['block_id']): r for r in rows}
        if set(records) != set(group):
            raise Stop('VECTOR_SOURCE_BLOCK_MISSING:'+sid)
        for bid in group:
            record = records[bid]
            row = {c: version if c == 'DATASET_VERSION' else record['json' if c == 'SOURCE_JSON' else c.lower()]
                   for c in COLUMNS['block_payload']}
            migration.validate_row('block_payload', row)
            body = row['TEXT']; uid = str(record['unit_id']) if record['unit_id'] is not None else root
            parts.append({'block_id': bid, 'unit_id': uid, 'start': 0, 'end': len(body), 'text': body,
                          'block_sha256': hashlib.sha256(body.encode()).hexdigest()})
    if not any(p['text'].strip() for p in parts):
        return []
    if root == '@source':
        if any(p['unit_id'] != root for p in parts):
            raise Stop('VECTOR_UNSTRUCTURED_SOURCE_HAS_STRUCTURED_BLOCKS:'+sid)
        units = {root: {'id': None, 'parent': None, 'title': source.get('heading',''),
                        'authority': 'navigation_source_without_structural_unit'}}
    else:
        units = units_for(store, did, {root} | {p['unit_id'] for p in parts})
    paths = {}
    for uid in units:
        chain = []; current = uid
        while current is not None:
            chain.append(current); current = units[current]['parent']
        paths[uid] = list(reversed(chain))
    for p in parts:
        if root not in paths[p['unit_id']]:
            raise Stop('VECTOR_BLOCK_OUTSIDE_SOURCE_STRUCTURE:'+sid+':'+p['block_id'])
    own = {uid: [] for uid in units}
    for p in parts:
        own[p['unit_id']].append(p)
    source_hash = digest(source)
    output = []
    prefixes = {}

    def refs(values):
        return [dict({k: p[k] for k in ('block_id','start','end','block_sha256')},
                     unit_id=None if p['unit_id']=='@source' else p['unit_id']) for p in values]

    def prefix(uid):
        if uid in prefixes:
            return prefixes[uid]
        chain = paths[uid]
        labels = [str(source.get('document_name') or did)] + [title(units[u]) for u in chain]
        all_context = [p for u in chain[:-1] for p in own[u]]
        full_heading = ' / '.join(x for x in labels if x)
        heading_limit = min(1024, maximum//4)
        if len(full_heading) <= heading_limit:
            heading = full_heading
        else:
            # Keep whole labels where possible. Full labels remain in metadata.
            selected = []; used = 0
            for label in reversed([x for x in labels if x]):
                if used+len(label)+3 <= heading_limit:
                    selected.insert(0,label); used += len(label)+3
            heading = ' / '.join(selected) or '원문 '+digest([did,uid])[:12]
        context = []; size = 0; context_limit = maximum//3
        if len(text_of(all_context)) <= context_limit:
            context = all_context
        else:
            # Whole sentences only in the optional repeated context. Every
            # ancestor body is also indexed in its own source-body segments.
            for part in all_context:
                for atom in sentence_parts(part):
                    if size+len(atom['text'])+1 <= context_limit:
                        context.append(atom); size += len(atom['text'])+1
        value = heading+'\n'+(text_of(context)+'\n' if context else '')
        info = {'context_mode': 'FULL' if refs(context)==refs(all_context) else 'LINKED_REMAINDER',
                'context_scope_units': [u for u in chain[:-1] if own[u]],
                'context_full_sha256': digest(refs(all_context)),
                'context_blocks_total': len(all_context),
                'heading_mode': 'FULL' if heading==full_heading else 'FULL_PATH_IN_METADATA'}
        if heading != full_heading:
            info['full_structure_heading'] = full_heading
        prefixes[uid] = (value,context,info)
        return prefixes[uid]

    def fits(uid, group):
        return len(prefix(uid)[0])+len(text_of(group)) <= maximum

    def emit(uid, group, extent):
        if not group:
            return
        lead, context, info = prefix(uid)
        body = text_of(group); text = lead+body
        if len(text) > maximum:
            raise Stop('VECTOR_SEGMENT_CAPACITY_VIOLATION:'+sid+':'+uid+
                       ':chars='+str(len(text))+':limit='+str(maximum))
        meta = {'document_id': did, 'source_id': sid, 'unit_id': None if uid=='@source' else uid,
                'source_unit_id':source['unit_id'],
                'extent': extent, 'source_sha256': source_hash, 'structure_sha256': digest(units[uid]),
                'structure_path': [u for u in paths[uid] if u!='@source'],
                'structure_status':'UNSTRUCTURED' if uid=='@source' else 'STORED',
                'body_spans': refs(group), 'context_spans': refs(context),
                'input_sha256': hashlib.sha256(text.encode()).hexdigest(), 'segment_policy': policy['version'],
                'split_boundaries': sorted({p['split_boundary'] for p in group if 'split_boundary' in p}),
                **info}
        output.append({'id': digest([version, meta]), 'meta': meta, 'text': text})

    def leaf(uid, group):
        if fits(uid, group):
            emit(uid, group, 'unit_own'); return
        atoms = []
        capacity = maximum-len(prefix(uid)[0])
        for part in group:
            for atom in sentence_parts(part):
                atoms.extend(bounded_parts(atom,capacity) if len(atom['text'])>capacity else [atom])
        batch = []
        for atom in atoms:
            if batch and not fits(uid, batch+[atom]):
                emit(uid, batch, 'sentences'); batch = []
            batch.append(atom)
        emit(uid, batch, 'sentences')

    def split(uid, group):
        if fits(uid, group):
            emit(uid, group, 'source' if uid == root else 'unit_subtree'); return
        # Preserve source block order, grouping only consecutive same-child spans.
        runs = []
        for part in group:
            path = paths[part['unit_id']]
            position = path.index(uid)
            child = path[position+1] if position+1 < len(path) else None
            if runs and runs[-1][0] == child:
                runs[-1][1].append(part)
            else:
                runs.append((child, [part]))
        for child, subset in runs:
            if child is None:
                leaf(uid, subset)
            else:
                split(child, subset)
    split(root, parts)
    # Stable sequence links allow audit/reassembly without mixing sources.
    for index,item in enumerate(output):
        item['meta'].update(source_segment_index=index, source_segment_count=len(output))
        item['id'] = digest([version,item['meta']])
    return output


def segments(store, navigation, version, migration, cursor=None, plan=None):
    after = cursor['source_id'] if cursor else None
    inclusive = bool(cursor)
    while True:
        where = (' WHERE id '+('>=' if inclusive else '>')+' ?') if after is not None else ''
        rows = navigation.execute('SELECT id,json FROM source'+where+' ORDER BY id LIMIT 16',
                                  (after,) if after is not None else ()).fetchall()
        if not rows:
            if inclusive: raise Stop('VECTOR_RESUME_SOURCE_MISSING')
            return
        if inclusive and rows[0][0] != after:
            raise Stop('VECTOR_RESUME_SOURCE_MISSING')
        for sid, raw in rows:
            source = json.loads(raw)
            if source['id'] != sid: raise Stop('VECTOR_SOURCE_ID_MISMATCH')
            items = source_segments(store, source, version, migration)
            if plan is not None:
                expected = plan.execute('SELECT n,sha FROM source WHERE id=?',(sid,)).fetchone()
                if expected is None or tuple(expected) != (len(items),digest([p['id'] for p in items])):
                    raise Stop('VECTOR_PLAN_CONTENT_CHANGED:'+sid)
            start = cursor['next_segment'] if cursor and cursor['source_id'] == sid else 0
            if start > len(items): raise Stop('VECTOR_RESUME_SEGMENT_MISSING')
            for index in range(start, len(items)):
                yield dict(items[index], cursor={'source_id': sid, 'next_segment': index+1})
        after = rows[-1][0]; inclusive = False
