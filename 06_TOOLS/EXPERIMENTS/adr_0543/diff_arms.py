"""ADR-0543/0544 S3-S7 judge: compare baseline and candidate reference rows (no model, no gold).

usage: diff_arms.py <baseline.sqlite> <candidate.sqlite> <candidate-repeat.sqlite> <base-integrity.txt> <out-dir>
Key = (source_id, block_id, mention_start, mention_end, origins, locator); duplicate keys compare as multisets.
"""
import collections
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

CM051_SOURCE = 'article:84b29933c65f93c686c2f2ea'
CM051_TARGET = 'article:f3fb98538a2c5134d0446a96'
SUFFIX = re.compile(r'(시행령|시행규칙)\s*$')
ARTICLE = re.compile(r'제\s*\d+(?:\s*-\s*\d+)*\s*조(?:\s*의\s*\d+)?')
DECLARED_INDEX = '92b972df068defd881baa38b4a66da36928d778a8c1614603d64e4d7427b0de8'


def nospace(t):
    return re.sub(r'[\s·ㆍ]+', '', t or '')


def load(path):
    db = sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True)
    rows = collections.defaultdict(list)
    for (payload,) in db.execute('SELECT json FROM reference'):
        r = json.loads(payload)
        key = (r['source_id'], str(r['block_id']), r['mention_start'], r['mention_end'],
               tuple(r.get('origins') or ()), r['locator'])
        rows[key].append(r)
    sources = {sid: json.loads(p) for sid, p in db.execute('SELECT id,json FROM source')}
    return rows, sources


def view(r):
    return (tuple(r['target_source_ids']), r['resolution'], r.get('document_name_hint'), r.get('document_hint_basis'))


def exact(r):
    return str(r['resolution']).startswith('EXACT')


def classify(b, c):
    if view(b) == view(c):
        return 'same'
    if (tuple(b['target_source_ids']), b['resolution']) != (tuple(c['target_source_ids']), c['resolution']):
        return 'target_or_resolution'
    if b.get('document_name_hint') != c.get('document_name_hint'):
        return 'hint'
    return 'basis_label_only'


def main(base_path, cand_path, repeat_path, integrity_path, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    base, sources = load(base_path)
    cand, _ = load(cand_path)
    only_base = sorted(set(base) - set(cand))
    only_cand = sorted(set(cand) - set(base))
    classes = collections.Counter()
    by_class_suffix = collections.Counter()
    changed, violations_s3, violations_s4, new_exact = [], [], [], []
    label_moves = collections.Counter()
    for key in sorted(set(base) & set(cand)):
        bs = sorted(base[key], key=lambda r: json.dumps(view(r), ensure_ascii=False))
        cs = sorted(cand[key], key=lambda r: json.dumps(view(r), ensure_ascii=False))
        if len(bs) != len(cs):
            classes['multiplicity_changed'] += 1
            violations_s3.append({'key': key, 'why': 'multiplicity', 'base': len(bs), 'cand': len(cs)})
            continue
        for b, c in zip(bs, cs):
            kind = classify(b, c)
            classes[kind] += 1
            in_suffix = bool(SUFFIX.search(b['source_text'][:b['mention_start']]))
            by_class_suffix[(kind, in_suffix)] += 1
            if kind == 'same':
                continue
            row = {'key': key, 'class': kind, 'suffix_class': in_suffix,
                   'prefix_tail': b['source_text'][max(0, b['mention_start'] - 40):b['mention_start']],
                   'mention': b.get('mention_text') or b['locator'],
                   'base': view(b), 'cand': view(c), 'base_reason': b.get('reason'), 'cand_reason': c.get('reason')}
            changed.append(row)
            if kind == 'basis_label_only':
                label_moves[(b.get('document_hint_basis'), c.get('document_hint_basis'))] += 1
                if not (b.get('document_hint_basis') == 'declared' and c.get('document_hint_basis') == 'convention'):
                    violations_s3.append({**row, 'why': 'label change other than declared->convention'})
            elif not in_suffix:
                violations_s3.append({**row, 'why': 'change outside suffix class'})
            if exact(b) and (not exact(c) or b['target_source_ids'] != c['target_source_ids']):
                violations_s4.append(row)
            if exact(c) and (not exact(b) or b['target_source_ids'] != c['target_source_ids']):
                new_exact.append((row, c))
    # S5 automatic coherence on every new EXACT row
    auto_fail = []
    for row, c in new_exact:
        hint = c.get('document_name_hint')
        for sid in c['target_source_ids']:
            s = sources[sid]
            title = s['document_name'].rsplit(' > ', 1)[-1].strip()
            heading_art = ARTICLE.match(s['heading'] or '')
            loc_art = ARTICLE.match(c['locator'] or '')
            ok_title = hint is not None and nospace(title) == nospace(hint)
            ok_art = bool(heading_art and loc_art and nospace(heading_art[0]) == nospace(loc_art[0]))
            if not (ok_title and ok_art):
                auto_fail.append({**row, 'target': sid, 'target_title': title, 'target_heading': s['heading'],
                                  'ok_title': ok_title, 'ok_article': ok_art})
    ordered = sorted(new_exact, key=lambda x: json.dumps(x[0]['key'], ensure_ascii=False))
    sample = random.Random(543).sample(ordered, min(40, len(ordered)))
    review = []
    for row, c in sample:
        text = next(r for r in cand[row['key']] if view(r) == row['cand'])['source_text']
        start = row['key'][2]
        review.append({'key': row['key'], 'citing_document': sources[row['key'][0]]['document_name'].rsplit(' > ', 1)[-1],
                       'context': text[max(0, start - 60):start + 30], 'hint': c.get('document_name_hint'),
                       'basis': c.get('document_hint_basis'),
                       'targets': [(sources[t]['document_name'].rsplit(' > ', 1)[-1], sources[t]['heading'])
                                   for t in c['target_source_ids']],
                       'agent_verdict': None})
    # S6
    cm051 = [r for rs in cand.values() for r in rs
             if r['source_id'] == CM051_SOURCE and '시행규칙' in r['source_text'][:r['mention_start']][-12:]]
    s6 = {'rows': [{'mention': r.get('mention_text'), 'targets': r['target_source_ids'], 'resolution': r['resolution'],
                    'hint': r.get('document_name_hint'), 'basis': r.get('document_hint_basis'),
                    'target_unit_path': r.get('target_unit_path')} for r in cm051]}
    s6['pass'] = any(r['target_source_ids'] == [CM051_TARGET] and r['resolution'] == 'EXACT_NAMED_DOCUMENT_ARTICLE'
                     for r in cm051)
    # S7
    receipts = {name: json.loads(Path(p).with_suffix('.receipt.json').read_text())
                for name, p in (('baseline', base_path), ('candidate', cand_path), ('repeat', repeat_path))}
    lines = dict(l.split()[:2] for l in Path(integrity_path).read_text().splitlines())
    s7 = {'base_sha_before': lines.get('base_sha_before'), 'base_sha_after': lines.get('base_sha_after'),
          'declared_index_sha256': DECLARED_INDEX,
          'candidate_content_sha256': receipts['candidate']['reference_content_sha256'],
          'repeat_content_sha256': receipts['repeat']['reference_content_sha256'],
          'model_calls': sum(r['model_calls'] for r in receipts.values())}
    s7['pass'] = (s7['base_sha_before'] == s7['base_sha_after'] == DECLARED_INDEX
                  and s7['candidate_content_sha256'] == s7['repeat_content_sha256'] and s7['model_calls'] == 0)
    # primary descriptive counts in suffix class
    suffix_flow = collections.Counter()
    for row in changed:
        if row['suffix_class']:
            b_ex = str(row['base'][1]).startswith('EXACT')
            c_ex = str(row['cand'][1]).startswith('EXACT')
            suffix_flow[('EXACT' if b_ex else 'UNRESOLVED') + '->' + ('EXACT' if c_ex else 'UNRESOLVED')] += 1
    summary = {
        'reference_keys': {'baseline': sum(map(len, base.values())), 'candidate': sum(map(len, cand.values())),
                           'only_baseline': len(only_base), 'only_candidate': len(only_cand)},
        'classes': dict(classes),
        'classes_by_suffix': {f'{k}|suffix={s}': v for (k, s), v in sorted(by_class_suffix.items())},
        'label_moves': {f'{a}->{b}': v for (a, b), v in label_moves.items()},
        'suffix_flow': dict(suffix_flow),
        'S3': {'violations': len(violations_s3) + len(only_base) + len(only_cand), 'pass': not violations_s3 and not only_base and not only_cand},
        'S4': {'violations': len(violations_s4), 'pass': not violations_s4},
        'S5_auto': {'new_exact': len(new_exact), 'auto_fail': len(auto_fail), 'pass': not auto_fail and bool(new_exact),
                    'sample_size': len(review), 'manual_review': 'pending'},
        'S6': s6, 'S7': s7, 'receipts': receipts}
    (out / 'diff-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    (out / 'diff-changed-rows.json').write_text(json.dumps(changed, ensure_ascii=False) + '\n')
    (out / 'diff-violations.json').write_text(json.dumps({'S3': violations_s3, 'S4': violations_s4, 'S5_auto_fail': auto_fail,
                                                         'only_baseline': only_base, 'only_candidate': only_cand},
                                                        ensure_ascii=False, indent=1) + '\n')
    (out / 's5-review-sample.json').write_text(json.dumps(review, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k != 'receipts'}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main(*sys.argv[1:6])
