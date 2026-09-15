"""Collect public glossary originals into RAW; never promote meanings or releases.

Called by pipeline.py glossary collect-external. Cached responses are hash verified
and retained across retries. Source-specific definitions remain separate.
"""
from __future__ import annotations
import fcntl
import hashlib
import io
import json
import logging
import math
from pathlib import Path
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from lawrag.platform.paths import data_path
from lawrag.sources.common import HttpClient, make_session, CrawlAborted

VERSION = 'public-glossary-collection-v1'
BOK = 'https://www.bok.or.kr/portal/bbs/B0000249/view.do?menuNo=200765&nttId=10096081'
ECON = 'https://econedu.go.kr/user/playEcon/currEconTermDoc/menu/list'
NTS = 'https://taxlaw.nts.go.kr/st/USESTJ001M.do'
KOFIA = 'https://www.kofia.or.kr/brd/m_117/view.do?seq=11'
KRX = 'https://open.krx.co.kr/contents/OPN/01/01030500/OPN01030500.jsp'

def now():
    return datetime.now(timezone.utc).isoformat()

def sha(b):
    return hashlib.sha256(b).hexdigest()

def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)

class Collector:
    def __init__(self, snapshot):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', snapshot):
            raise ValueError('Invalid snapshot')
        self.raw = data_path('RAW', 'glossaries', snapshot)
        self.structured = data_path('STRUCTURE', 'glossaries', snapshot)
        self.logs = data_path('LOGS', 'glossaries', snapshot)
        self.logs.mkdir(parents=True, exist_ok=True)
        self.receipt_path = self.logs / 'collection.json'
        self.receipt = json.loads(self.receipt_path.read_text()) if self.receipt_path.exists() else {
            'schema_version': VERSION, 'snapshot': snapshot, 'started_at': now(),
            'access': 'public', 'stage': 'RAW/DRAFT', 'sources': {},
            'semantic_review_complete': False, 'runtime_promoted': False,
        }
        if self.receipt['schema_version'] != VERSION:
            raise ValueError('Collector version changed; use a new snapshot')
        logger = logging.getLogger('collect.public-glossaries')
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            logger.addHandler(logging.FileHandler(self.logs / 'http.log', encoding='utf-8'))
        self.client = HttpClient(make_session(), logger, timeout=25)

    def record(self, source, **fields):
        self.receipt['sources'].setdefault(source, {}).update(fields)
        self.receipt['updated_at'] = now()
        atomic(self.receipt_path, self.receipt)
        print(json.dumps({'source': source, **fields}, ensure_ascii=False), flush=True)

    def fetch(self, source, name, url, *, method='GET', data=None):
        path = self.raw / source / name
        meta = path.with_suffix(path.suffix + '.receipt.json')
        request = {'method': method, 'url': url, 'data': data}
        if path.exists() and meta.exists():
            rec = json.loads(meta.read_text())
            body = path.read_bytes()
            if rec['request'] != request or rec['sha256'] != sha(body):
                raise ValueError(f'Cached source conflict: {path}')
            return body
        response = self.client.request(method, url, **({'data': data} if data is not None else {}))
        response.raise_for_status()
        if not response.content:
            raise ValueError(f'Empty response: {url}')
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + '.tmp')
        tmp.write_bytes(response.content)
        tmp.replace(path)
        atomic(meta, {'request': request, 'retrieved_at': now(), 'sha256': sha(response.content),
                      'bytes': len(response.content), 'status': response.status_code,
                      'content_type': response.headers.get('Content-Type'),
                      'content_disposition': response.headers.get('Content-Disposition')})
        return response.content

    def soup(self, source, name, url):
        return BeautifulSoup(self.fetch(source, name, url).decode('utf-8'), 'html.parser')

    def entries(self, source, rows):
        if not rows or len({r['id'] for r in rows}) != len(rows):
            raise ValueError('Missing rows or duplicate source identities')
        if any(not r['term'] or not r['definition'] for r in rows):
            raise ValueError('Missing term or definition')
        path = self.structured / source / 'entries.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        body = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows).encode()
        tmp = path.with_suffix('.tmp'); tmp.write_bytes(body); tmp.replace(path)
        return {'entries': len(rows), 'entries_path': str(path), 'entries_sha256': sha(body)}

    def pdf(self, source, page, selector):
        import fitz
        soup = self.soup(source, 'landing.html', page)
        anchor = selector(soup)
        url = urljoin(page, anchor['href'])
        body = self.fetch(source, 'dictionary.pdf', url)
        if not body.startswith(b'%PDF'):
            raise ValueError('PDF download returned a non-PDF response')
        with fitz.open(stream=body, filetype='pdf') as doc:
            if doc.needs_pass: raise ValueError('Encrypted PDF')
            pages = len(doc)
            text_pages = sum(bool(p.get_text().strip()) for p in doc)
        self.record(source, status='collected', source_url=page, artifact_url=url,
                    format='pdf', pages=pages, text_pages=text_pages,
                    structured_entries=0, structuring_required=True,
                    historical_archive=(source == 'kofia'))

    def bok(self):
        self.pdf('bok', BOK, lambda s: next(a for a in s.select('a[href]') if '800선.pdf' in a.get_text()))

    def kofia(self):
        self.pdf('kofia', KOFIA, lambda s: next(a for a in s.select('a[href]') if 'down.do' in a['href']))

    def econedu(self):
        import openpyxl
        soup = self.soup('econedu', 'landing.html', ECON)
        fields = {i['name']: i.get('value', '') for i in soup.select('#form1 input[name]')}
        expected = int(fields['listCount'])
        url = 'https://econedu.go.kr/user/playEcon/currEconTermDoc/listExcel'
        body = self.fetch('econedu', 'dictionary.xlsx', url, method='POST', data=fields)
        workbook = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
        try:
            values = list(workbook.active.values)
        finally:
            workbook.close()
        if tuple(values[0]) != ('순번', '주제', '용어', '설명'):
            raise ValueError('Unexpected spreadsheet columns')
        rows = [{'id': f'econedu:{self.receipt["snapshot"]}:row:{i}', 'source': 'econedu',
                 'source_url': ECON, 'source_locator': {'sheet': 'Sheet1', 'row': i},
                 'source_id': None, 'source_sequence': v[0], 'category': v[1],
                 'term': v[2], 'definition': v[3], 'definition_kind': 'dictionary_explanation',
                 'review_status': 'unreviewed', 'source_sha256': sha(body)}
                for i, v in enumerate(values[1:], 2) if any(x is not None for x in v)]
        if len(rows) != expected:
            raise ValueError(f'List/export count mismatch: {expected}/{len(rows)}')
        self.record('econedu', status='collected', source_url=ECON, expected=expected,
                    license_notice='공공누리 출처표시+변경금지; 원문 설명 보존', **self.entries('econedu', rows))

    def nts(self):
        self.fetch('nts', 'landing.html', NTS)
        def action(name, action_id, params):
            body = self.fetch('nts', name, 'https://taxlaw.nts.go.kr/action.do', method='POST',
                              data={'actionId': action_id, 'paramData': json.dumps(params, ensure_ascii=False)})
            payload = json.loads(body)
            if payload.get('status') != 'SUCCESS':
                raise ValueError(f'NTS application error: {payload.get("status")}')
            return payload['data'][action_id], sha(body)
        catalog = []; expected = None; page = 1
        while True:
            d, _ = action(f'list/{page:04d}.json', 'ASISTJ001MR01',
                         {'searchNtstTrgyDictCntn': '', 'pageIndex': page, 'recordCountPerPage': 100})
            if expected is None: expected = int(d['recordCount'])
            if expected != int(d['recordCount']) or int(d['pageIndex']) != page:
                raise ValueError('NTS pagination changed')
            batch = d['trgyDictInqrDVOList']
            if len(batch) != min(100, expected - len(catalog)):
                raise ValueError('NTS page length mismatch')
            catalog.extend(batch)
            if len(catalog) == expected: break
            page += 1
        ids = [r['ntstTrgyDictBrkdId'] for r in catalog]
        if len(set(ids)) != expected: raise ValueError('Duplicate NTS IDs')
        self.record('nts', status='collecting_details', source_url=NTS, expected=expected, catalog_entries=len(catalog))
        rows = []
        for index, item in enumerate(catalog, 1):
            ident = item['ntstTrgyDictBrkdId']
            if not re.fullmatch(r'\d+', ident): raise ValueError('Invalid NTS ID')
            d, fingerprint = action(f'detail/{ident}.json', 'ASISTJ002MR01',
                                    {'ntstTrgyDictBrkdId': ident, 'pageForm': 'P'})
            full = d['trgyDictInqrDVO']
            if full['ntstTrgyDictBrkdId'] != ident or full['ntstTrgyDictCntn'] != item['ntstTrgyDictCntn']:
                raise ValueError('NTS detail identity mismatch')
            if not full['ntstTrgyDictEpnCntn']: raise ValueError('Missing NTS full definition')
            rows.append({'id': 'nts:' + ident, 'source': 'nts', 'source_id': ident,
                         'source_url': 'https://taxlaw.nts.go.kr/st/USESTJ002P.do?ntstTrgyDictBrkdId=' + ident,
                         'term': full['ntstTrgyDictCntn'], 'english': full['ntstTrgyDictEnglCntn'],
                         'hanja': full['ntstTrgyDictChchCntn'], 'definition': full['ntstTrgyDictEpnCntn'],
                         'definition_kind': 'dictionary_explanation', 'review_status': 'unreviewed',
                         'source_sha256': fingerprint})
            if index % 25 == 0: self.record('nts', details_complete=index)
        self.record('nts', status='collected', details_complete=len(rows), **self.entries('nts', rows))

    def krx(self):
        # Actual item endpoint must be verified before claiming the menu is a dictionary payload.
        self.fetch('krx', 'landing.html', KRX)
        self.record('krx', status='needs_item_endpoint', source_url=KRX, entries=0)

    def run(self, sources):
        with (self.logs / 'collector.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for source in sources:
                self.record(source, status='running')
                try:
                    getattr(self, source)()
                except CrawlAborted:
                    self.record(source, status='blocked', error='HTTP client detected blocking; collection stopped')
                    raise
                except Exception as exc:
                    self.record(source, status='incomplete', error=f'{type(exc).__name__}: {exc}')
            complete = all(self.receipt['sources'][s]['status'] == 'collected' for s in sources)
            self.receipt['requested_sources'] = sources
            self.receipt['collection_complete'] = complete
            atomic(self.receipt_path, self.receipt)
            return self.receipt

def run(snapshot, sources=None):
    return Collector(snapshot).run(sources or ['bok', 'econedu', 'kofia', 'nts', 'krx'])
