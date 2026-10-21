"""Parent scopes for a complete document, merged by original block overlap."""
import json
from .contracts import digest, require

POLICY = 'parent-overlap-v1'


def inventory(store, did):
    store.check_unchanged()
    units = {}
    for row in store.db.execute(
            'SELECT unit_id,parent_id,json FROM source_unit WHERE document_id=?', (did,)):
        value = json.loads(row['json'])
        lo, hi = value['span']
        require(type(lo) is int and type(hi) is int and lo < hi,
                'BASIS_STRUCTURE', '구조 원문 범위가 잘못되었습니다.', 409)
        units[str(row['unit_id'])] = {
            'id': str(row['unit_id']),
            'parent': str(row['parent_id']) if row['parent_id'] is not None else None,
            'lo': lo, 'hi': hi, 'title': value.get('title') or value.get('surface') or str(row['unit_id'])}
    parents = {u['parent'] for u in units.values() if u['parent'] is not None}
    for unit in units.values():
        seen = set()
        current = unit
        while current['parent'] is not None:
            require(current['id'] not in seen and current['parent'] in units,
                    'BASIS_STRUCTURE', '구조 상위 항목이 없거나 순환합니다.', 409)
            seen.add(current['id'])
            parent = units[current['parent']]
            require(parent['lo'] <= current['lo'] and parent['hi'] >= current['hi'],
                    'BASIS_STRUCTURE', '상위 구조의 범위가 하위를 포함하지 않습니다.', 409)
            current = parent
    # Smallest stored structural nodes, then exactly one level up.
    scopes = {u['parent'] or u['id'] for u in units.values() if u['id'] not in parents}
    ranges = sorted((dict(units[uid]) for uid in scopes), key=lambda x: (x['lo'], -x['hi'], x['id']))
    merged = []
    for item in ranges:
        if merged and item['lo'] < merged[-1]['hi']:
            previous = merged[-1]
            previous['hi'] = max(previous['hi'], item['hi'])
            previous['members'].append(item['id'])
            # Crossing ranges have no single real parent. Keep exact spans.
            if previous['id'] is None or not (units[previous['id']]['lo'] <= item['lo'] and units[previous['id']]['hi'] >= item['hi']):
                previous['id'] = None
        else:
            merged.append({**item, 'members': [item['id']]})
    blocks = [{'block_id': str(r['block_id']), 'start_cp': 0, 'end_cp': r['chars'],
               'owner': str(r['unit_id']) if r['unit_id'] is not None else None}
              for r in store.db.execute(
                  'SELECT block_id,unit_id,length(text) AS chars FROM source_block '
                  'WHERE document_id=? AND length(text)>0 ORDER BY CAST(block_id AS INTEGER)', (did,))]
    groups = []
    covered = set()
    for scope in merged:
        selected = [b for b in blocks if scope['lo'] <= int(b['block_id']) < scope['hi']]
        if not selected:
            continue
        covered.update(b['block_id'] for b in selected)
        groups.append((scope['id'], scope['title'], selected, scope['members']))
    # Preambles, unclassified text and unattached annexes must not disappear.
    for block in blocks:
        if block['block_id'] not in covered:
            owner = block['owner']
            title = units.get(owner, {}).get('title', '구조 미분류 본문')
            groups.append((owner, title, [block], [owner] if owner else []))
    result = []
    for uid, title, selected, members in groups:
        spans = [{k: b[k] for k in ('block_id', 'start_cp', 'end_cp')} for b in selected]
        node = {'document_id': did, 'unit_id': uid, 'source_id': None,
                'read_segments': spans, 'read_label': title}
        result.append({'inventory_id': digest([POLICY, node]), 'title': title, 'node': node,
                       'scope_policy': POLICY, 'merged_units': members,
                       'chars': sum(b['end_cp'] for b in selected)})
    result.sort(key=lambda g: int(g['node']['read_segments'][0]['block_id']))
    require(len({b['block_id'] for g in result for b in g['node']['read_segments']}) == len(blocks),
            'BASIS_COVERAGE', '전체 내규 원문 범위가 일치하지 않습니다.', 409)
    store.check_unchanged()
    return result
