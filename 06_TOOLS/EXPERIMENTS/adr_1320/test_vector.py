import copy
import json
import time
from types import SimpleNamespace as NS

import pytest

from semantic_runtime.oracle_development_mapping import DevelopmentMapping
from semantic_runtime.oracle_dp_io import digest
from semantic_runtime.oracle_query_vector import Retriever, PublishedEncoder
from semantic_runtime.initial_vector import VectorError, VectorUnavailable


PROFILE = {'model': 'mesh:synthetic', 'revision': 'immutable-test', 'dimensions': 3,
           'metric': 'COSINE', 'normalization': 'l2', 'transport': 'dataiku-llm-mesh'}


def fixture():
    mapping = DevelopmentMapping.load()
    manifest = {'profile': PROFILE, 'query_id': 'q', 'source_release_id': 's', 'dataset_version': 'v',
                'documents': ['public', 'private']}
    complete = {'status': 'READY', 'count': 2, 'profile_sha256': digest(PROFILE)}
    envelope = {'manifest': manifest, 'completion': complete}
    head = {'VCTR_POST_ID': digest(manifest), 'CHAN_NO': 1}
    calls = []
    def query(stmt, binds, *, limit):
        calls.append((stmt, binds))
        if 'LGL_G19_VCTR_HEAD_S_1' in stmt:
            return [head]
        if 'LGL_G19_VCTR_POST_S_1' in stmt:
            return [{'VCTR_POST_IFMN_CTNT': json.dumps(envelope)}]
        assert 'LGL_G19_VCTR_ITEM_S_1' in stmt
        return [{'DOC_ID': 'public', 'SOURCE_ID': 'article:1', 'DISTANCE': 0.0}]
    sql = NS(client=NS(schema_map=mapping), query=query, deadline=time.monotonic()+60)
    req = NS(sql=sql, release_id='q', sources=NS(allowed={'public'}),
             snapshot=NS(release_id='s', dataset_version='v'),
             records=NS(manifest={'source_manifest': {'scope': {'document_version_ids': ['public', 'private']}}}))
    encodes = []
    class Encoder:
        def __init__(self, config, *, deadline):
            assert config == PROFILE
            self.calls = 0
        def encode(self, texts):
            encodes.append(texts); self.calls += 1
            return [[2., 0., 0.]]
    return Retriever(req, encoder_factory=Encoder), envelope, head, calls, encodes


def test_real_physical_projection_scope_grouping_and_request_reuse():
    retriever, envelope, head, calls, encodes = fixture()
    result = retriever.search('이사회 승인', {'public'})
    assert result['rows'][0]['SOURCE_ID'] == 'article:1'
    assert result['embedding_calls'] == 1
    assert retriever.search('이사회 승인', {'public'}) == result
    assert len(encodes) == 1 and len(calls) == 3
    stmt, binds = calls[-1]
    assert 'BODY_UNIT_ID AS SRC_UNIT_ID' in stmt and 'EMBD_VCTR AS EMBD_VCTR_VALU' in stmt
    assert 'GROUP BY v.DOC_ID,v.SRC_UNIT_ID' in stmt
    assert json.loads(dict((k,v) for k,v,_ in binds)['docs']) == ['public']
    assert json.loads(dict((k,v) for k,v,_ in binds)['v']) == [1.,0.,0.]


def test_empty_scope_and_unauthorized_scope_do_not_encode_or_query():
    reader, _, _, calls, encodes = fixture()
    assert reader.search('승인', set())['rows'] == []
    assert reader.search('승인', {'public'}, [])['rows'] == []
    with pytest.raises(VectorError, match='cannot widen'):
        reader.search('승인', {'private'})
    assert not calls and not encodes


@pytest.mark.parametrize('kind', ['query', 'source', 'dataset', 'documents', 'duplicate', 'profile', 'count', 'ready', 'hash'])
def test_unsealed_or_mismatched_publication_never_calls_embedding(kind):
    reader, env, head, calls, encodes = fixture()
    if kind == 'query': env['manifest']['query_id'] = 'other'
    elif kind == 'source': env['manifest']['source_release_id'] = 'other'
    elif kind == 'dataset': env['manifest']['dataset_version'] = 'other'
    elif kind == 'documents': env['manifest']['documents'] = ['public']
    elif kind == 'duplicate': env['manifest']['documents'].append('public')
    elif kind == 'profile': env['completion']['profile_sha256'] = '0'*64
    elif kind == 'count': env['completion']['count'] = 0
    elif kind == 'ready': env['completion']['status'] = 'BUILDING'
    elif kind == 'hash': head['VCTR_POST_ID'] = '0'*64
    if kind != 'hash': head['VCTR_POST_ID'] = digest(env['manifest'])
    with pytest.raises(VectorError): reader.search('승인', {'public'})
    assert not encodes


def test_null_head_is_unavailable_and_source_filter_is_bound():
    reader, _, head, calls, encodes = fixture()
    head['VCTR_POST_ID'] = None
    with pytest.raises(VectorUnavailable, match='NOT_PUBLISHED'): reader.search('승인', {'public'})
    assert not encodes
    reader, _, _, calls, _ = fixture()
    reader.search('승인', {'public'}, ['article:1'])
    assert dict((k,v) for k,v,_ in calls[-1][1])['sources'] == '["article:1"]'


def environment():
    return {'GENOS_EMBED_PROFILE_SHA256': digest(PROFILE), 'GENOS_BASE_URL': 'https://genos.invalid',
            'GENOS_EMBED_SERVING_ID': '19', 'GENOS_EMBED_KEY': 'fixture-only',
            'GENOS_EMBED_MODEL': 'fixture-kure', 'GENOS_EMBED_TENANT_ID': 'fixture-tenant'}


def test_genos_gateway_prefix_tenant_dimension_and_no_retry():
    calls = []
    def post(url, **kw):
        calls.append((url,kw))
        return NS(status_code=200, json=lambda:{'data':[{'index':0,'embedding':[2.,0.,0.]}]})
    encoder = PublishedEncoder(PROFILE, env=environment(), post=post)
    assert encoder.encode(['승인']) == [[1.,0.,0.]]
    assert calls[0][0] == 'https://genos.invalid/api/gateway/rep/serving/19/embeddings'
    assert calls[0][1]['headers']['x-genos-user-id'] == 'fixture-tenant'
    assert calls[0][1]['allow_redirects'] is False
    assert encoder.calls == 1
    bad = PublishedEncoder(PROFILE, env=environment(), post=lambda *a,**k:NS(status_code=429))
    with pytest.raises(VectorUnavailable): bad.encode(['승인'])
    assert bad.calls == 1


@pytest.mark.parametrize('change', ['profile', 'key'])
def test_explicit_bad_pin_and_missing_credentials_fail(change):
    env = environment()
    env[{'profile':'GENOS_EMBED_PROFILE_SHA256','model':'GENOS_EMBED_MODEL','key':'GENOS_EMBED_KEY'}[change]] = 'wrong' if change=='profile' else ''
    with pytest.raises(VectorError): PublishedEncoder(PROFILE, env=env)


@pytest.mark.parametrize('rows', [[{'index':0,'embedding':[1.,0.]}],
    [{'index':0,'embedding':[0.,0.,0.]}], [{'index':0,'embedding':[float('nan'),0.,1.]}],
    [{'index':1,'embedding':[1.,0.,0.]}], []])
def test_bad_embedding_response_fails(rows):
    encoder = PublishedEncoder(PROFILE, env=environment(), post=lambda *a,**k:NS(status_code=200,json=lambda:{'data':rows}))
    with pytest.raises(VectorError): encoder.encode(['승인'])


def test_profile_change_invalidates_factory_environment(monkeypatch):
    from semantic_runtime.oracle_query_service import environment_binding
    before = environment_binding()
    monkeypatch.setenv('GENOS_EMBED_PROFILE_SHA256','a'*64)
    assert before != environment_binding()
