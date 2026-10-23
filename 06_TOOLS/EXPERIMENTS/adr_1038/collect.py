"""Pinned public acquisition for ADR1038. Credentials never enter receipts."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import requests

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / '02_BACKEND'))
from lawrag.sources.lawgo import parse_body_meta
from lawrag.platform.paths import root_path

ADR = root_path('experiments', 'ADR', 'ADR-1038-law-version-incremental-audit')
RAW = root_path('data', 'RAW', 'external', 'version-audits', 'adr-1038')
VERSIONS = [('254785', '20230914'), ('257829', '20240703'), ('277253', '20260102')]

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def save(path, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    if path.exists() and path.read_bytes() != raw:
        raise ValueError('immutable artifact conflict: ' + path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(raw)

def main():
    from dotenv import dotenv_values
    oc = os.getenv('LAW_OC') or dotenv_values(ROOT / '.env').get('LAW_OC') or 'test'
    rows = []
    for mst, effective in VERSIONS:
        path = RAW / f'law-012338-{mst}-{effective}.xml'
        receipt = path.with_suffix('.receipt.json')
        if receipt.exists():
            item = json.loads(receipt.read_text())
            if sha(path.read_bytes()) != item['sha256']:
                raise ValueError('saved input drift')
            rows.append(item)
            continue
        params = {'target': 'eflaw', 'MST': mst, 'efYd': effective, 'type': 'XML'}
        response = requests.get('https://www.law.go.kr/DRF/lawService.do',
                                params={'OC': oc, **params}, timeout=(10, 40))
        raw = response.content
        if path.exists() and path.read_bytes() != raw:
            raise ValueError('body conflict; existing raw preserved')
        path.write_bytes(raw)
        item = {'path': str(path.relative_to(ROOT)), 'sha256': sha(raw),
                'bytes': len(raw), 'http_status': response.status_code,
                'retrieved_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                'endpoint': 'https://www.law.go.kr/DRF/lawService.do', 'params': params,
                'access': 'public', 'data_kind': 'real', 'credential_recorded': False}
        if response.status_code != 200:
            save(receipt, {**item, 'status': 'FAILED_HTTP'})
            raise RuntimeError('body download failed; raw response preserved')
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
            raise ValueError('XML external entities forbidden')
        root = ET.fromstring(raw)
        meta = parse_body_meta(raw.decode('utf-8'))
        if root.tag != '법령' or meta['doc_id'] != '012338' or meta['enforce'] != effective:
            save(receipt, {**item, 'status': 'FAILED_VERSION', 'metadata': meta})
            raise ValueError('actual body identity mismatch')
        item.update(metadata=meta, status='VERIFIED_BODY', requested_serial=mst)
        save(receipt, item)
        rows.append(item)
        print(mst, effective, len(raw), sha(raw), flush=True)
    save(ADR / 'artifacts/dataset.json', {'schema_version': 'law-version-audit-input-v1',
         'law_id': '012338', 'versions': rows, 'selection': 'Three latest effective versions of exact law ID from captured eflaw history; two adjacent transitions.',
         'production_catalog_registered': False, 'source_set': 'Explicit isolated audit only; no active input selection.'})

if __name__ == '__main__':
    main()
