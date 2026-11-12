"""Field 2026-11-11: the startup metadata preload failed with QUERY_RESPONSE_SIZE.

It asked 3,000 rows per round trip whatever the row size, so a page of about 2.7 KB rows went over the
8 MB response limit. Real QuerySQL (the limit itself) and Records.page; only the ORDS endpoint is a fake.
"""
import json
import time

import pytest

from semantic_runtime import oracle_metadata_preload as preload
from semantic_runtime.oracle_dp_io import DPError, digest
from semantic_runtime.oracle_query import MAX_PAGE, MAX_RESPONSE_BYTES, QuerySQL, canonical
from semantic_runtime.oracle_query_catalog import Records


KIND = 'native.source'


def row(index, chars):
    body = json.dumps({'id': index, 'title': '조문', 'text': '가' * chars}, ensure_ascii=False)
    return {'ROW_ID': f'{index:064x}', 'DOCUMENT_ID': 'd1', 'LOOKUP_ID': f'l{index}', 'OWNER_ID': None,
            'TARGET_ID': None, 'VALUE': body, 'N': len(body.encode('utf-16-le')) // 2}


class Ords:
    SQL_PATH = '/sql'

    def __init__(self, rows):
        self.rows, self.limits, self.sizes = rows, [], []

    def request(self, method, path, json):
        binds = {b['name']: b['value'] for b in json.get('binds', [])}
        after = binds.get('after')
        found = [r for r in self.rows if after is None or r['ROW_ID'] > after][:json['limit']]
        item = {'resultSet': {'items': [dict(r) for r in found], 'hasMore': False, 'offset': 0}}
        self.limits.append(json['limit'])
        self.sizes.append(len(canonical(item).encode()))
        return {'items': [item]}


def records(rows, name):
    client = Ords(rows)
    sql = QuerySQL(client, binding='test', deadline=time.monotonic() + 60, max_calls=1000)
    manifest = {'name': name, 'tables': {KIND: {}}}
    return Records(sql, digest(manifest), manifest), client


def test_rows_near_the_field_size_load_within_the_response_limit():
    rows = [row(i, 2400) for i in range(4000)]
    reader, client = records(rows, 'uniform')
    report = preload.load(reader)
    assert report['kinds'][KIND]['state'] == 'READY' and report['kinds'][KIND]['rows'] == 4000
    assert client.limits[0] == MAX_PAGE and max(client.limits) > MAX_PAGE
    assert max(client.sizes) <= MAX_RESPONSE_BYTES


def test_larger_rows_after_small_ones_are_read_again_at_the_small_page():
    rows = [row(i, 100) for i in range(300)] + [row(i, 6000) for i in range(300, 3600)]
    reader, client = records(rows, 'growing')
    report = preload.load(reader)
    assert report['kinds'][KIND]['state'] == 'READY' and report['kinds'][KIND]['rows'] == 3600
    assert max(client.sizes) > MAX_RESPONSE_BYTES, 'the case must really hit the limit once'
    index = client.sizes.index(max(client.sizes))
    assert client.limits[index + 1] == MAX_PAGE


def test_every_row_is_held_once_and_answered_in_order_from_memory():
    rows = [row(i, 2400) for i in range(3500)]
    reader, _ = records(rows, 'complete')
    preload.load(reader)
    index = preload.REGISTRY.get(reader.release_id, None, KIND)
    assert index.ids == [r['ROW_ID'] for r in rows]


def test_other_read_failures_are_not_retried():
    reader, client = records([row(i, 10) for i in range(10)], 'failing')

    def fail(*args, **kwargs):
        raise DPError('READ_FAILED: ReadTimeout')
    client.request = fail
    with pytest.raises(DPError, match='READ_FAILED'):
        preload.load(reader)
