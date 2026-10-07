"""Group the base dictionary into label cards, everyday aliases and hierarchy families.

Read-only over the pinned dictionary and the legal-relations DRAFT. Nothing is approved:
a card is a display grouping of entries that share a surface key (homonyms stay listed
by source ID), everyday terms hang under the legal terms the MOLEG relation points to
(only 동의 makes an alias; other codes stay as related everyday words), and a family is
one top term of the MOLEG hierarchy edges (140304, normalized parent -> child) with the
terms at most FAMILY_DEPTH levels below it. MOLEG hierarchy is not transitive in meaning
(담보 > 저당권 > 공장재단 > 건물 > ... > 대구광역시), so deeper chains are not followed.

usage: group_terms.py --output DIR
"""
import argparse, collections, json, sqlite3, unicodedata
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / '00_SYSTEM/WORKSPACE.json').is_file())
DICT = ROOT / '01_DATA/LEXICON/glossary-v1/boundary-20260914-v3/dictionary.sqlite'
GRAPH = ROOT / '01_DATA/LEXICON/glossary-v1/legal-relations-20260915-v1/graph.json'
SOURCE = {'legal_terms': '법제처 법령용어', 'knowledge_terms': '법제처 지식 법령용어',
          'everyday_terms': '법제처 일상용어', 'econedu': '경제배움e', 'nts': '국세청',
          'corpus_definition': '문서 정의조항'}
FAMILY_DEPTH = 2
CODE = {'140301': '동의', '140302': '반의', '140303': '상위', '140304': '하위', '140305': '연관'}


def load():
    db = sqlite3.connect(f'file:{DICT}?mode=ro', uri=True)
    entries = {}
    for eid, src, label, key, dfn, prov in db.execute(
            'select id, source, label, key, definition, provenance from entry'):
        kind = json.loads(prov).get('entity_type') if src == 'moleg' else src
        entries[eid] = dict(label=label, key=key, kind=kind, definition=dfn or '')
    for eid, text in db.execute(
            "select d.entry_id, r.text from definition_candidate d join definition_record r on r.id = d.definition_id "
            "where d.match_kind = 'SOURCE_ID' and r.content_type = 'EXPLANATION'"):
        if not entries[eid]['definition']:
            entries[eid]['definition'] = text
    occ = dict(db.execute('select key, count(distinct document_id) from occurrence group by key'))
    official = db.execute('select source_id, target_id, code from official_relation').fetchall()
    return entries, occ, official


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', required=True)
    out = Path(ap.parse_args().output)
    out.mkdir(parents=True, exist_ok=False)
    entries, occ, official = load()
    graph = json.loads(GRAPH.read_text())
    # The DRAFT graph also holds legal IDs reached only from everyday terms; give them cards too.
    for n in graph['nodes']:
        if n['id'] not in entries:
            k = ''.join(unicodedata.normalize('NFKC', n['label']).split())
            entries[n['id']] = dict(label=n['label'], key=k, kind='knowledge_terms', definition='')

    # 1. cards: one per surface key; everyday-only keys are handled as aliases below.
    cards = collections.defaultdict(lambda: dict(label=None, ids=[], kinds=collections.Counter(),
                                                 definitions=[], aliases=set(), everyday=set(), synonyms=set(),
                                                 antonyms=set(), related=set(), parents=set(), children=set()))
    for eid, e in entries.items():
        c = cards[e['key']]
        if c['label'] is None or e['kind'] != 'everyday_terms':
            c['label'] = c['label'] if c['label'] and c['kinds'] else e['label']
        c['ids'].append(eid)
        c['kinds'][e['kind']] += 1
        if e['definition'] and (SOURCE[e['kind']], e['definition']) not in c['definitions']:
            c['definitions'].append((SOURCE[e['kind']], e['definition']))

    # 2. everyday words: MOLEG legal -> everyday relations, attached to the legal card.
    key = {eid: e['key'] for eid, e in entries.items()}
    alias_of = collections.defaultdict(set)
    for s, t, code in official:
        if entries[t]['kind'] == 'everyday_terms' and key[t] != key[s]:
            cards[key[s]]['aliases' if CODE[code] == '동의' else 'everyday'].add(entries[t]['label'])
            alias_of[key[t]].add(key[s])

    # 3. legal-to-legal edges from the DRAFT graph, lifted to cards.
    parents = collections.defaultdict(set)
    children = collections.defaultdict(set)
    for e in graph['edges']:
        a, b = key[e['source_id']], key[e['target_id']]
        if a == b:
            continue
        kind = CODE[e['code']]
        if kind == '하위':
            children[a].add(b); parents[b].add(a)
        elif kind == '동의':
            cards[a]['synonyms'].add(b); cards[b]['synonyms'].add(a)
        elif kind == '반의':
            cards[a]['antonyms'].add(b); cards[b]['antonyms'].add(a)
        else:
            cards[a]['related'].add(b); cards[b]['related'].add(a)

    # Everyday-only cards that became aliases are folded away.
    def is_alias_only(k):
        c = cards[k]
        return set(c['kinds']) == {'everyday_terms'} and k in alias_of
    visible = [k for k in cards if not is_alias_only(k)]

    # 4. families: one top term and everything below it. Multi-parent terms sit in every family
    # that reaches them; joining those families would weld unrelated trees into one component.
    def descendants(k):
        seen, frontier = {k}, {k}
        for _ in range(FAMILY_DEPTH):
            frontier = set().union(*(children[x] for x in frontier)) - seen
            seen |= frontier
        return seen
    families = [dict(name=cards[r]['label'], roots=[r], members=descendants(r))
                for r in set(children) - set(parents)]
    families.sort(key=lambda f: (-len(f['members']), f['name']))
    family_of = collections.defaultdict(list)
    for i, f in enumerate(families):
        for m in f['members']:
            family_of[m].append(i)

    label = lambda k: cards[k]['label']
    def tree_lines(k, depth, path):
        c = cards[k]
        multi = ' (상위 %d개)' % len(parents[k]) if len(parents[k]) > 1 else ''
        yield depth, k, multi
        if depth == FAMILY_DEPTH:
            return
        for ch in sorted(children[k], key=label):
            if ch not in path:
                yield from tree_lines(ch, depth + 1, path | {ch})

    # outputs
    rows = []
    for k in visible:
        c = cards[k]
        kinds = [SOURCE[x] for x in SOURCE if c['kinds'][x]]
        kind = ('법제처 법령·지식용어' if c['kinds']['knowledge_terms'] or c['kinds']['legal_terms'] else
                '문서 정의어' if c['kinds']['corpus_definition'] else
                '국세청·경제배움e 용어' if c['kinds']['econedu'] or c['kinds']['nts'] else '법제처 일상용어(미연결)')
        fams = family_of.get(k, [])
        rows.append(dict(key=k, label=c['label'], type=kind,
                         term_class='본문용어' if occ.get(k) else '참고용어', sources=kinds, ids=len(c['ids']),
                         documents=occ.get(k, 0),
                         family=[families[i]['name'] for i in fams],
                         parents=sorted(map(label, parents[k])), children=sorted(map(label, children[k])),
                         synonyms=sorted(map(label, c['synonyms'])), antonyms=sorted(map(label, c['antonyms'])),
                         related=len(c['related']), aliases=sorted(c['aliases']),
                         everyday=sorted(c['everyday']),
                         definitions=c['definitions']))
    (out / 'cards.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    with open(out / 'families.md', 'w') as f:
        for i, fam in enumerate(families):
            f.write(f'\n## {i + 1}. {fam["name"]} — {len(fam["members"])}개\n\n')
            for r in fam['roots']:
                for depth, k, multi in tree_lines(r, 0, {r}):
                    f.write('  ' * depth + f'- {label(k)}{multi}\n')
    summary = dict(
        entries=len(entries), cards=len(cards), visible_cards=len(visible),
        everyday_folded=len(cards) - len(visible),
        card_types=collections.Counter(r['type'] for r in rows),
        term_classes=collections.Counter(r['term_class'] for r in rows),
        multi_source_cards=sum(len(r['sources']) > 1 for r in rows),
        homonym_cards=sum(r['ids'] > len(r['sources']) for r in rows),
        in_family=sum(bool(r['family']) for r in rows), families=len(families),
        multi_family=sum(len(r['family']) > 1 for r in rows),
        family_size=collections.Counter(min(len(f['members']), 50) // 10 * 10 if len(f['members']) >= 10
                                        else len(f['members']) for f in families),
        with_synonym=sum(bool(r['synonyms']) for r in rows), with_alias=sum(bool(r['aliases']) for r in rows), with_everyday=sum(bool(r['everyday']) for r in rows),
        top_families=[(f['name'], len(f['members'])) for f in families[:30]])
    write_xlsx(out / 'grouping.xlsx', rows, families, tree_lines, label, occ, cards)
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=dict))
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=dict))


def write_xlsx(path, rows, families, tree_lines, label, occ, cards):
    from openpyxl import Workbook
    wb = Workbook(write_only=True)
    ws = wb.create_sheet('개념가족')
    ws.append(['가족 번호', '가족(최상위 용어)', '가족 크기', '단계', '용어', '트리 표시', '상위 개수', '본문 출현 문서 수', '출처'])
    for i, fam in enumerate(families, 1):
        for r in fam['roots']:
            for depth, k, multi in tree_lines(r, 0, {r}):
                srcs = ', '.join(SOURCE[x] for x in SOURCE if cards[k]['kinds'][x])
                ws.append([i, fam['name'], len(fam['members']), depth, label(k), '    ' * depth + label(k),
                           multi.strip(' ()'), occ.get(k, 0), srcs])
    ws = wb.create_sheet('표제어 카드')
    ws.append(['표제어', '본문용어/참고용어', '출처 유형', '출처', '원천 ID 수', '본문 출현 문서 수', '소속 가족', '상위어', '하위어',
               '동의어(법제처 지식용어)', '반의어', '연관어 수', '법제처 일상용어 별칭(동의)', '관련 법제처 일상용어', '정의 출처', '정의'])
    for r in sorted(rows, key=lambda r: (-r['documents'], r['label'])):
        d = r['definitions'][0] if r['definitions'] else ('', '')
        j = lambda xs, n=30: ', '.join(xs[:n]) + (f' 외 {len(xs) - n}' if len(xs) > n else '')
        ws.append([r['label'], r['term_class'], r['type'], ', '.join(r['sources']), r['ids'], r['documents'], j(r['family']),
                   j(r['parents']), j(r['children']), j(r['synonyms']), j(r['antonyms']), r['related'],
                   j(r['aliases']), j(r['everyday']), d[0], d[1][:300]])
    wb.save(path)


if __name__ == '__main__':
    main()
