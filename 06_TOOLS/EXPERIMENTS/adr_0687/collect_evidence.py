"""Read-only source audit evidence; never invokes a product or judge model."""
from pathlib import Path
import datetime
import gzip
import hashlib
import json
import sqlite3
import sys
import urllib.request

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0687-risk-cm-recorded-answer-source-review'
OUT = ADR / 'artifacts/evidence'
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / '02_BACKEND'))
from lawrag.core.hwp5_md import _extract


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def put(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


frozen = json.loads((ADR / 'artifacts/design/frozen.json').read_text())
for path, expected in frozen['inputs'].items():
    assert sha((ROOT / path).read_bytes()) == expected, path
store = ROOT / frozen['product_generation']['data_path'] / 'store.sqlite'
db = sqlite3.connect(store.resolve().as_uri() + '?mode=ro', uri=True)
db.row_factory = sqlite3.Row
originals = []
for key, doc, unit in [
    ('general-provision', 'c9b5b42627710637', '523'),
    ('special-provision', 'c9b5b42627710637', '788'),
    ('rp', 'c9b5b42627710637', '2623'),
    ('rp-decree', '2a410c9dfc65dac1', '3393'),
    ('pf-body', '5c292593a5e4e4e4', '508'),
]:
    row = db.execute('SELECT json FROM source_unit WHERE document_id=? AND unit_id=?', (doc, unit)).fetchone()
    meta = json.loads(row['json'])
    lo, hi = meta['span']
    blocks = [dict(r) for r in db.execute(
        'SELECT block_id,text,source_artifact_sha256 FROM source_block WHERE document_id=? '
        'AND CAST(block_id AS INTEGER)>=? AND CAST(block_id AS INTEGER)<? ORDER BY CAST(block_id AS INTEGER)',
        (doc, lo, hi))]
    originals.append({'id': key, 'document_id': doc, 'article_unit_id': unit,
                      'unit_json_sha256': sha(row['json'].encode()), 'unit': meta, 'blocks': blocks})
pf_units = [json.loads(r[0]) for r in db.execute('SELECT json FROM source_unit WHERE document_id=?', ('5c292593a5e4e4e4',))]
pf_annexes = [u for u in pf_units if u.get('coordinate_scope') == 'annex' and
              any(n in json.dumps(u, ensure_ascii=False) for n in ('17-1', '17-2'))]
db.close()
put(OUT / 'selected-generation-originals.json', {'store_path': str(store.relative_to(ROOT)),
    'originals': originals, 'risk_document_17_annex_unit_count': len(pf_annexes),
    'absence_scope': 'Only the selected risk document units; not a claim that the whole corpus lacks the attachments.'})


def fetch(key, url):
    target = OUT / (key + '.html.gz')
    if target.exists():
        raw = gzip.decompress(target.read_bytes())
        info = {'id': key, 'url': url, 'raw_sha256': sha(raw), 'raw_bytes': len(raw),
                'path': str(target.relative_to(ROOT)), 'sha256': sha(target.read_bytes()),
                'provenance': 'Successful exact fetch from collection attempt 001; resumed without refetch or replacement.'}
        return info, BeautifulSoup(raw, 'html.parser').get_text('\n', strip=True)
    with urllib.request.urlopen(url, timeout=35) as response:
        raw = response.read()
        info = {'id': key, 'url': url, 'final_url': response.url,
                'content_type': response.headers.get('Content-Type'), 'raw_sha256': sha(raw),
                'raw_bytes': len(raw), 'fetched_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    target.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
    assert sha(gzip.decompress(target.read_bytes())) == info['raw_sha256']
    info.update(path=str(target.relative_to(ROOT)), sha256=sha(target.read_bytes()))
    text = BeautifulSoup(raw, 'html.parser').get_text('\n', strip=True)
    return info, text


web = []
for key, url, pairs in [
    ('finance-current', 'https://www.law.go.kr/LSW/admRulLsInfoR.do?admRulSeq=2100000285020&chrClsCd=010201',
     [('제3-8조(', '제3-9조('), ('제3-24조의4(', '제7절'), ('제5-18조(', '제5-19조(')]),
    ('finance-company-filing', 'https://kind.krx.co.kr/external/2026/05/15/002321/20260515005203/11013.htm',
     [('24. 대손준비금', '(1) 당분기')]),
]:
    info, text = fetch(key, url)
    info['extracts'] = []
    for start, end in pairs:
        a = text.find(start)
        b = text.find(end, a + len(start)) if end and a >= 0 else -1
        info['extracts'].append({'start': start, 'found': a >= 0,
            'text': text[a:b if b >= 0 else a+1600] if a >= 0 else ''})
    web.append(info)

attachments = []
for name, seq in [('annex-17-1-2025', 25756), ('annex-17-2-2025', 25757)]:
    url = f'https://law.kofia.or.kr/download.do?gubun=102&seq={seq}'
    attachments.append({'id': name, 'url': url,
        'history_source': 'https://law.kofia.or.kr/service/law/lawFullScreenContent.do?historySeq=1682&seq=155',
        'downloaded': False, 'limitation': 'Official link verified by web reading; binary content unavailable through web tool. Shell KOFIA TLS timed out; no applicable-version full attachment verification claimed.'})

raw_existing = []
folder = ROOT / '01_DATA/RAW/kofia/금융투자회사의 리스크관리 모범규준/별표서식'
for path in sorted(folder.glob('*')):
    if ('17-1' in path.name or '17-2' in path.name) and path.is_file():
        raw_existing.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(path.read_bytes()),
                             'bytes': path.stat().st_size,
                             'scope': 'Existing RAW evidence only; no serving registration or product modification.'})
put(OUT / 'primary-source-index.json', {'web': web, 'attachments': attachments, 'existing_raw': raw_existing,
    'kofia_web_reading': {'path': str((OUT / 'web-tool-readings.json').relative_to(ROOT)),
                         'sha256': sha((OUT / 'web-tool-readings.json').read_bytes())},
    'version_notes': [
        'Financial investment regulation official shell: effective 2026-09-15, notice 2026-38 dated 2026-09-09.',
        'KOFIA July 9, 2026 published revision states effective 2027-01-01; do not apply its new capital-ratio examples as current.',
        'The three Article 6-15 body propositions match the 2025 history and selected inference generation.',
        'Old attachments are checked separately to avoid silently using future-effective changes.']})
print(json.dumps({'immutable_inputs_verified': len(frozen['inputs']), 'original_articles': len(originals),
                  'web_sources': len(web), 'official_attachment_links_only': len(attachments),
                  'selected_risk_17_annex_units': len(pf_annexes), 'new_model_calls': 0}))
