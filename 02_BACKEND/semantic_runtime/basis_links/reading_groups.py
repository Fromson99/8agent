"""Size-bounded reading groups over one complete document's stored structure.

A group is only a reading window: which rows belong to one comparison unit is
decided later from the original text.  The stored block owner decides where a
block belongs; unit names and numbering families are never interpreted, so
article-style and outline-style documents are grouped by the same rule.
"""
import json
from .contracts import digest, require

POLICY = 'reading-groups-v1'
LIMITS = {'max_chars': 8000, 'max_rows': 30, 'max_spine_chars': 2000}
UNSTRUCTURED = '구조 미분류 본문'
ROLE_NOTE = {'lead': ' (머리 문장)', 'between': ' (중간 문장)', 'tail': ' (꼬리 문장)'}


def _label(uid, value):
    surface, title = (value.get('surface') or '').strip(), (value.get('title') or '').strip()
    if surface and title and not title.startswith(surface):
        return surface + ' ' + title
    return title or surface or str(uid)


def _load(store, did):
    units = {}
    for row in store.db.execute('SELECT unit_id,parent_id,json FROM source_unit WHERE document_id=?', (did,)):
        uid = str(row['unit_id'])
        units[uid] = {'parent': str(row['parent_id']) if row['parent_id'] is not None else None,
                      'label': _label(uid, json.loads(row['json'])), 'children': [], 'blocks': []}
    for uid, unit in units.items():
        seen, current = set(), uid
        while units[current]['parent'] is not None:
            require(current not in seen and units[current]['parent'] in units,
                    'BASIS_STRUCTURE', '구조 상위 항목이 없거나 순환합니다.', 409)
            seen.add(current)
            current = units[current]['parent']
        if unit['parent'] is not None:
            units[unit['parent']]['children'].append(uid)
    blocks = []
    for row in store.db.execute(
            'SELECT block_id,unit_id,length(text) AS chars FROM source_block '
            'WHERE document_id=? AND length(text)>0 ORDER BY CAST(block_id AS INTEGER)', (did,)):
        owner = str(row['unit_id']) if row['unit_id'] is not None else None
        require(owner is None or owner in units, 'BASIS_STRUCTURE', '원문 문단의 구조 소유자가 없습니다.', 409)
        blocks.append({'block_id': str(row['block_id']), 'chars': row['chars'], 'owner': owner})
    return units, blocks


def _path(units, uid):
    out = []
    while uid is not None:
        out.append(uid)
        uid = units[uid]['parent']
    return out[::-1]


def build(store, did, *, max_chars=None, max_rows=None, max_spine_chars=None):
    """Every text block of ``did`` exactly once, in rows, in bounded groups."""
    limits = {'max_chars': LIMITS['max_chars'] if max_chars is None else max_chars,
              'max_rows': LIMITS['max_rows'] if max_rows is None else max_rows,
              'max_spine_chars': LIMITS['max_spine_chars'] if max_spine_chars is None else max_spine_chars}
    require(all(type(v) is int for v in limits.values()) and limits['max_chars'] > 0 and limits['max_rows'] > 0
            and limits['max_spine_chars'] >= 0, 'BASIS_GROUP_LIMIT', '묶음 한도가 잘못되었습니다.')
    store.check_unchanged()
    units, blocks = _load(store, did)
    # Position in the ordered text; (position, direct child or None) per subtree.
    order = {b['block_id']: position for position, b in enumerate(blocks)}
    require(len(order) == len(blocks), 'BASIS_STRUCTURE', '원문 문단 식별자가 중복되었습니다.', 409)
    members = {None: []}
    for position, block in enumerate(blocks):
        chain = _path(units, block['owner'])
        members[None].append((position, chain[0] if chain else None))
        for depth, uid in enumerate(chain):
            members.setdefault(uid, []).append((position, chain[depth + 1] if depth + 1 < len(chain) else None))

    def segment(position, start=0, end=None):
        block = blocks[position]
        return {'block_id': block['block_id'], 'start_cp': start, 'end_cp': block['chars'] if end is None else end}

    def row(uid, positions, role, segments=None, part=None):
        segments = segments or [segment(p) for p in positions]
        chain = _path(units, uid)
        return {'row_id': digest([POLICY, did, uid, segments]), 'unit_id': uid,
                'label': (units[uid]['label'] if uid is not None else UNSTRUCTURED) + ROLE_NOTE.get(role, ''),
                'path': [units[a]['label'] for a in chain[:-1]], 'depth': len(chain), 'role': role,
                'segments': segments, 'chars': sum(s['end_cp'] - s['start_cp'] for s in segments), 'part': part,
                '_positions': list(positions)}

    own_rows = {}

    def runs(uid):
        """Own text of a unit: maximal runs not interrupted by a child's text."""
        if uid not in own_rows:
            tagged = members.get(uid, [])
            child_positions = [p for p, child in tagged if child is not None]
            result, current = [], []
            for position, child in tagged + [(None, 'END')]:
                if child is None:
                    current.append(position)
                    continue
                if current:
                    role = ('own' if uid is None or not child_positions else 'lead' if current[-1] < child_positions[0]
                            else 'tail' if current[0] > child_positions[-1] else 'between')
                    result.append(row(uid, current, role))
                    current = []
            own_rows[uid] = result
        return own_rows[uid]

    def subtree_rows(uid):
        found = list(runs(uid))
        for child in units[uid]['children']:
            found.extend(subtree_rows(child))
        return sorted(found, key=lambda r: r['_positions'][0])

    def pieces(uid):
        children = units[uid]['children'] if uid is not None else [u for u, v in units.items() if v['parent'] is None]
        found = [{'unit': None, 'rows': [r]} for r in runs(uid)]
        for child in children:
            rows = subtree_rows(child)
            if rows:
                found.append({'unit': child, 'rows': rows})
        for piece in found:
            piece['chars'] = sum(r['chars'] for r in piece['rows'])
        return sorted(found, key=lambda p: p['rows'][0]['_positions'][0])

    def parts(whole):
        """One row longer than the limit: whole blocks first, then code points."""
        chunks, current, size = [], [], 0
        for position in whole['_positions']:
            chars = blocks[position]['chars']
            if chars > limits['max_chars']:
                if current:
                    chunks.append(current)
                    current, size = [], 0
                chunks.extend([(position, a, min(a + limits['max_chars'], chars))]
                              for a in range(0, chars, limits['max_chars']))
                continue
            if current and size + chars > limits['max_chars']:
                chunks.append(current)
                current, size = [], 0
            current.append((position, 0, chars))
            size += chars
        if current:
            chunks.append(current)
        return [row(whole['unit_id'], [p for p, _, _ in chunk], whole['role'],
                    [segment(p, a, z) for p, a, z in chunk], {'index': index + 1, 'count': len(chunks)})
                for index, chunk in enumerate(chunks)]

    groups = []

    def spine(chain, rows):
        inside = {p for r in rows for p in r['_positions']}
        first = min(inside)
        entries = []
        for uid in chain:
            outside = [r for r in runs(uid) if not inside.intersection(r['_positions'])]
            entries.append({'unit_id': uid, 'label': units[uid]['label'], 'rows': [
                {'row_id': r['row_id'], 'role': r['role'], 'segments': r['segments'], 'chars': r['chars'],
                 'position': 'before' if r['_positions'][0] < first else 'after'} for r in outside]})
        omitted = []
        for keep in (lambda r: r['role'] == 'lead', lambda r: False):
            if sum(r['chars'] for e in entries for r in e['rows']) <= limits['max_spine_chars']:
                break
            for entry in entries:
                omitted.extend(r['row_id'] for r in entry['rows'] if not keep(r))
                entry['rows'] = [r for r in entry['rows'] if keep(r)]
        return entries, omitted

    def emit(selected, chain):
        rows = [r for piece in selected for r in piece['rows']]
        segments = sorted((s for r in rows for s in r['segments']),
                          key=lambda s: (order[s['block_id']], s['start_cp']))
        names = [units[p['unit']]['label'] if p['unit'] is not None else p['rows'][0]['label'] for p in selected]
        title = names[0] if len(names) == 1 else names[0] + ' ~ ' + names[-1]
        if rows[0]['part']:
            title += ' (%d/%d)' % (rows[0]['part']['index'], rows[0]['part']['count'])
        context, omitted = spine(chain, rows)
        whole = selected[0]['unit'] if len(selected) == 1 else None
        groups.append({'group_id': digest([POLICY, did, segments]), 'title': title,
                       'path': [units[a]['label'] for a in chain],
                       'node': {'document_id': did, 'unit_id': whole, 'source_id': None,
                                'read_segments': segments, 'read_label': title},
                       'rows': [{k: v for k, v in r.items() if k != '_positions'} for r in rows],
                       'spine': context, 'spine_omitted': omitted,
                       'chars': sum(r['chars'] for r in rows), 'scope_policy': POLICY})

    def pack(uid, chain):
        current, chars, count = [], 0, 0
        for piece in pieces(uid):
            if piece['chars'] > limits['max_chars'] or len(piece['rows']) > limits['max_rows']:
                if current:
                    emit(current, chain)
                    current, chars, count = [], 0, 0
                if piece['unit'] is not None:
                    pack(piece['unit'], chain + [piece['unit']])
                else:
                    for part in parts(piece['rows'][0]):
                        emit([{'unit': None, 'rows': [part]}], chain)
                continue
            if current and (chars + piece['chars'] > limits['max_chars']
                            or count + len(piece['rows']) > limits['max_rows']):
                emit(current, chain)
                current, chars, count = [], 0, 0
            current.append(piece)
            chars += piece['chars']
            count += len(piece['rows'])
        if current:
            emit(current, chain)

    pack(None, [])
    groups.sort(key=lambda g: (order[g['node']['read_segments'][0]['block_id']], g['node']['read_segments'][0]['start_cp']))
    for index, group in enumerate(groups):
        group['index'] = index
    # No text may disappear or be assigned twice, whatever the stored tree looks like.
    covered = {}
    for group in groups:
        for item in group['rows']:
            for part in item['segments']:
                covered.setdefault(part['block_id'], []).append((part['start_cp'], part['end_cp']))
    require(set(covered) == {b['block_id'] for b in blocks}, 'BASIS_COVERAGE', '전체 원문 범위가 일치하지 않습니다.', 409)
    for block in blocks:
        end = 0
        for start, stop in sorted(covered[block['block_id']]):
            require(start == end and stop > start, 'BASIS_COVERAGE', '원문 문단이 누락되거나 중복되었습니다.', 409)
            end = stop
        require(end == block['chars'], 'BASIS_COVERAGE', '원문 문단이 누락되었습니다.', 409)
    store.check_unchanged()
    return {'schema_version': POLICY, 'document_id': did, 'limits': limits, 'groups': groups,
            'totals': {'blocks': len(blocks), 'chars': sum(b['chars'] for b in blocks), 'groups': len(groups),
                       'rows': sum(len(g['rows']) for g in groups)}}
