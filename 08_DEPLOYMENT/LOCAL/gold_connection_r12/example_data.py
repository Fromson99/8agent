"""Small synthetic data only. No source corpus copying or embedding API calls."""
import hashlib
import json


def make_example():
    from semantic_runtime.oracle_dp_io import canonical, digest, KEYS
    from semantic_runtime.oracle_query_catalog import record
    texts = [('public', '1', '이사회 승인 절차를 확인한다.'),
             ('public', '2', '이사회 승인 기록을 보관한다.'),
             ('private', '1', '이사회 승인 내부 문서이다.')]
    source_manifest = {'generation_id': 'r12-synthetic-only', 'store_sha256': digest('synthetic-store'),
                       'scope': {'document_version_ids': ['public', 'private']}}
    fts_manifest = {'schema_version': 'semantic-unit-fulltext-v1', 'index_sha256': digest('synthetic-fts')}
    fts_hash = digest(fts_manifest)
    source_manifest['fulltext'] = {'path': 'fulltext', 'manifest_sha256': fts_hash}
    manifest_text = canonical(source_manifest)
    version = hashlib.sha256(manifest_text.encode()).hexdigest()
    source_release = {'schema_version': 'oracle-rag-release-v1', 'status': 'COMPLETE',
                      'dataset_version': version, 'source_manifest': source_manifest,
                      'source_manifest_text': manifest_text}
    source_id = digest(source_release)
    sources = {name: [] for name in ('document', 'source_unit', 'block_payload')}
    for did in ('public', 'private'):
        sources['document'].append({'DATASET_VERSION': version, 'DOCUMENT_ID': did,
            'NAME': '가상 예시 문서 '+did, 'SOURCE_ARTIFACT_SHA256': digest(did), 'SOURCE_JSON': canonical({'synthetic': True})})
        sources['source_unit'].append({'DATASET_VERSION': version, 'DOCUMENT_ID': did, 'UNIT_ID': 'article-1',
                                      'PARENT_ID': None, 'SOURCE_JSON': canonical({'title': '가상 제1조'})})
    for did, bid, text in texts:
        sources['block_payload'].append({'DATASET_VERSION': version, 'DOCUMENT_ID': did, 'BLOCK_ID': bid,
            'UNIT_ID': 'article-1', 'TEXT': text, 'SOURCE_ARTIFACT_SHA256': digest(did),
            'SOURCE_JSON': canonical({'block_id': bid, 'synthetic': True}), 'JSON_TEXT_ELIDED': 1})
    records = []
    for kind, rows in sources.items():
        for row in rows:
            key = [row[c] for c in KEYS[kind]]
            lookup = digest([kind, key])
            records.append(record('source.integrity', {'source_kind': kind, 'source_key': key, 'source_sha256': digest(row)},
                                  key=lookup, document_id=row['DOCUMENT_ID'], lookup_id=lookup))
    prefix = 'asset_'+digest('fulltext/units.sqlite')[:12]+'.'
    kinds = {name: prefix+name for name in ('unit', 'unit_fts_posting', 'unit_fts_length', 'unit_fts_stats')}
    for did, bid, text in texts:
        key, sid = did+':'+bid, did+':article-1'
        body = {'key': key, 'document_id': did, 'source_id': sid, 'text': text, 'synthetic': True}
        records.append(record(kinds['unit'], {'key': key, 'json': canonical(body)}, key=key, document_id=did, lookup_id=key))
        records.append(record(kinds['unit_fts_length'], {'source_id': sid, 'length': 5}, key=key,
                              document_id=did, lookup_id=key))
        for position, token in enumerate(('이사회', '승인')):
            records.append(record(kinds['unit_fts_posting'], {'positions': [position]}, key=[key, token],
                                  document_id=did, lookup_id=token, owner_id=key, target_id='body'))
    records.append(record(kinds['unit_fts_stats'], {'documents': 3, 'tokens': 15}, key='stats', lookup_id='stats'))
    query_manifest = {'schema_version': 'oracle-query-release-v1', 'status': 'COMPLETE', 'source_release_id': source_id,
        'dataset_version': version, 'source_manifest': source_manifest,
        'tables': {kind: {} for kind in ['source.integrity', *kinds.values()]},
        'metadata': {'fulltext/manifest.json': {'sha256': fts_hash, 'value': fts_manifest}}}
    query_id = digest(query_manifest)
    profile = {'model': 'SYNTHETIC_NO_EMBEDDING_MODEL', 'revision': 'fixture-v1', 'dimensions': 4,
               'metric': 'COSINE', 'normalization': 'l2'}
    vector_manifest = {'schema_version': 'gold-vector-manifest-preview-v1', 'query_id': query_id,
        'source_release_id': source_id, 'dataset_version': version, 'documents': ['public', 'private'],
        'profile': profile, 'segment_profile': {'synthetic': True}}
    pub = digest(vector_manifest)
    items = []
    for did, bid, text in texts:
        meta = {'document_id': did, 'source_id': did+':article-1', 'unit_id': 'article-1', 'block_id': bid,
                'start': 0, 'end': len(text), 'source_sha256': digest(did),
                'block_sha256': hashlib.sha256(text.encode()).hexdigest(),
                'input_sha256': hashlib.sha256(text.encode()).hexdigest()}
        items.append({'pub': pub, 'id': digest([pub, did, bid]), 'meta': meta,
                      'vector': [1., 0., 0., 0.] if bid == '1' else [0., 1., 0., 0.]})
    envelope = {'manifest': vector_manifest, 'completion': {'status': 'READY', 'count': len(items),
                'chain': digest(sorted((i['id'], digest(i['meta'])) for i in items)),
                'profile_sha256': digest(profile), 'registered_at': '2026-10-29T00:00:00Z'}}
    ontology = {'schema_version': 'r12-synthetic-ontology-only', 'synthetic': True,
                'note': '저장과 원문 연결 확인용이며 승인된 법률 지식이 아님'}
    return {'sources': sources, 'source_release': source_release, 'source_id': source_id, 'version': version,
            'records': records, 'query_manifest': query_manifest, 'query_id': query_id,
            'vector': {'pub': pub, 'items': items, 'envelope': envelope}, 'ontology': ontology}


def load_example(connection, config, example):
    """One small transaction; use only an empty throwaway example schema."""
    from semantic_runtime.oracle_dp_io import canonical, digest
    from gold_connection import READ_COLUMNS, GoldError
    import oracledb
    total = 0
    with connection.cursor() as cursor:
        for t in config.model['tables']:
            cursor.execute('SELECT COUNT(*) FROM '+config.table(t['suffix']))
            if cursor.fetchone()[0]:
                raise GoldError('EXAMPLE_REQUIRES_EMPTY_TABLES')

        def insert(suffix, values):
            nonlocal total
            columns = list(values)
            definitions = {c['name']: c for t in config.model['tables'] if t['suffix'] == suffix for c in t['columns']}
            params = {'b'+str(i): values[c] for i, c in enumerate(columns)}
            sizes = {}
            for i, c in enumerate(columns):
                v, typ = values[c], definitions[c]['type']
                if isinstance(v, str) and typ.startswith(('VARCHAR2', 'CHAR')):
                    import re
                    if len(v.encode()) > int(re.search(r'\((\d+)', typ)[1]):
                        raise GoldError('GOLD_VALUE_TOO_LONG: '+c)
                if typ == 'CLOB' or typ.startswith('VECTOR'):
                    sizes['b'+str(i)] = oracledb.DB_TYPE_CLOB
            cursor.setinputsizes(**sizes)
            expressions = ['TO_VECTOR(:b'+str(i)+')' if definitions[c]['type'].startswith('VECTOR') else ':b'+str(i)
                           for i, c in enumerate(columns)]
            cursor.execute('INSERT INTO '+config.table(suffix)+' ('+','.join(columns)+') VALUES ('+
                           ','.join(expressions)+')', params)
            total += 1

        for kind, rows in example['sources'].items():
            suffix, mapping = READ_COLUMNS[kind]
            for row in rows:
                values = {mapping[k]: ('Y' if v == 1 else 'N' if v == 0 else None) if k == 'JSON_TEXT_ELIDED' else v
                          for k, v in row.items()}
                insert(suffix, values)
        insert('SRC_POST', {'DOC_POST_HASH_VALU': example['source_id'], 'MNFST_HASH_VALU': example['version'],
                           'DOC_POST_IFMN_CTNT': canonical(example['source_release'])})
        for r in example['records']:
            insert('SRCH_ROW', dict(zip(READ_COLUMNS['query_row'][1].values(),
                [example['query_id'], r['kind'], r['row_id'], r['document_id'], r['lookup_id'],
                 r['owner_id'], r['target_id'], r['sha256'], canonical(r['value'])])))
        insert('SRCH_POST', {'RFRN_POST_HASH_VALU': example['query_id'],
                             'RFRN_POST_IFMN_CTNT': canonical(example['query_manifest'])})
        insert('SRCH_CHNL', {'RFRN_CHNL_NAME': 'demo', 'RFRN_POST_HASH_VALU': example['query_id'], 'CHAN_NO': 1})
        ont = digest(example['ontology'])
        insert('ONTL_POST', {'ONTL_POST_ID': ont, 'CNCP_GROP_ID': 'demo-ontology', 'WORK_VER_NO': 1,
                            'POST_CTNT_HASH_VALU': ont, 'POST_KNWL_CTNT': canonical(example['ontology'])})
        insert('ONTL_HEAD', {'CNCP_GROP_ID': 'demo-ontology', 'ONTL_POST_ID': ont, 'CHAN_NO': 1})
        insert('ONTL_ANC', {'ONTL_POST_ID': ont, 'DOC_LCT_HASH_VALU': digest(['public', 'article-1']),
                           'DOC_ID': 'public', 'DOC_HASH_VALU': digest('public'), 'STRC_UNIT_ID': 'article-1'})
        vector = example['vector']
        for item in vector['items']:
            insert('VCTR_ITEM', {'VCTR_POST_ID': item['pub'], 'VCTR_SEG_ID': item['id'],
                                 'DOC_ID': item['meta']['document_id'], 'SRC_UNIT_ID': item['meta']['source_id'],
                                 'VCTR_META_CTNT': canonical(item['meta']), 'EMBD_VCTR_VALU': json.dumps(item['vector'])})
        # Demonstrate a partial second publication: items alone are not selected.
        insert('VCTR_ITEM', {'VCTR_POST_ID': digest('unfinished'), 'VCTR_SEG_ID': digest('unfinished-item'),
                             'DOC_ID': 'public', 'SRC_UNIT_ID': 'unsealed',
                             'VCTR_META_CTNT': canonical({'synthetic': True}), 'EMBD_VCTR_VALU': '[1,0,0,0]'})
        cursor.execute('SELECT COUNT(*) FROM '+config.table('VCTR_ITEM')+' WHERE VCTR_POST_ID=:p', p=vector['pub'])
        if cursor.fetchone()[0] != vector['envelope']['completion']['count']:
            raise GoldError('GOLD_VECTOR_COUNT')
        insert('VCTR_POST', {'VCTR_POST_ID': vector['pub'], 'VCTR_POST_IFMN_CTNT': canonical(vector['envelope'])})
    connection.commit()
    return total
