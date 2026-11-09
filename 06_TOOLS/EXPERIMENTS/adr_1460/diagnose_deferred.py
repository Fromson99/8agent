"""Why units stayed DEFERRED in ADR-1460 run-001 (saved records only, no model call)."""
from common import *
from collections import Counter
import gzip, re
GENERAL = ('제3-42조', '제3-43조', '제3-44조', '제3-64조')


def views():
    out = []
    names = sorted(p for p in (ART / 'run-001/canonical').glob('*.json.gz') if not p.name.endswith('-output.json.gz'))
    for p in names:
        value = json.loads(gzip.decompress(p.read_bytes()))
        view = value.get('view') or {}
        if view.get('source_stage') != 'workflow-unit_compare':
            continue
        o = p.with_name(p.name.replace('.json.gz', '-output.json.gz'))
        output = json.loads(gzip.decompress(o.read_bytes())) if o.exists() else None
        out.append((view, output))
    return out


def kind(reason):
    r = reason or ''
    if re.search(r'모범규준|자율|권고|업계', r): return 'self_regulatory_no_legal_counterpart'
    if re.search(r'다른 업종|종합금융|증권금융|신탁|집합투자기구|적용 대상이 다', r): return 'different_business_or_scope'
    if re.search(r'일반적|포괄|추상|구체적(인)? (기준|절차|내용)(을|이)? (정하|규정하)지', r): return 'external_only_general'
    if re.search(r'없|찾을 수 없|포함되어 있지 않|확인되지 않|대응하는', r): return 'no_matching_provision_shown'
    return 'other'


rows, liquidity = [], Counter()
for view, output in views():
    if not output: continue
    ext = [s for s in view['sources'] if s.get('side') == 'external']
    heads = [(s.get('found_for'), s['metadata']['document_name'], s['metadata'].get('heading', '')) for s in ext]
    v = output.get('verdict')
    row = {'label': view['unit']['label'], 'verdict': v, 'reason': output.get('reason'), 'kind': kind(output.get('reason')) if v == 'DEFERRED' else None,
           'own': [d[:6] + ' ' + h for f, d, h in heads if f == 'this_unit'][:8], 'nearby_count': sum(f == 'nearby_unit' for f, _, _ in heads),
           'general_risk_presented': any(d == '금융투자업규정' and h.startswith(GENERAL) for _, d, h in heads)}
    rows.append(row)
print('compare calls', len(rows), Counter(r['verdict'] for r in rows))
print('deferred reason kinds', Counter(r['kind'] for r in rows if r['verdict'] == 'DEFERRED'))
print('general risk article presented in', sum(r['general_risk_presented'] for r in rows), 'of', len(rows))
put(ART / 'deferred-diagnosis.json', rows)
for r in [r for r in rows if r['verdict'] == 'DEFERRED'][:10]:
    print('##', r['label'], '|', r['kind']); print('  ', (r['reason'] or '')[:220]); print('   own:', r['own'][:5], 'nearby', r['nearby_count'])
