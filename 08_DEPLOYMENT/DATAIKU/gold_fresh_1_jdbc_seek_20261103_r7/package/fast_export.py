"""Same search-row payloads; no redundant source rolling-chain verification."""
import json
from lawrag.pipeline.oracle_query_publish import _column_shapes
from semantic_runtime.oracle_query_catalog import record
from semantic_runtime.oracle_dp_io import digest

def source_records(path, source_release):
    """Publish row digests, not a duplicate source body, for selective verification."""
    from lawrag.pipeline.oracle_migration import source_open, source_batch
    from semantic_runtime.oracle_dp_io import KEYS, TABLES
    version = source_release['dataset_version']
    db = source_open(path)
    try:
        for kind in TABLES:
            cursor, count = None, 0
            columns={'DATASET_VERSION':None,'DOCUMENT_ID':'document_id','UNIT_ID':'unit_id','PARENT_ID':'parent_id',
                     'NAME':'name','SOURCE_ARTIFACT_SHA256':'source_artifact_sha256','SOURCE_JSON':'json',
                     'BLOCK_ID':'block_id','TEXT':'text','JSON_TEXT_ELIDED':None}
            from semantic_runtime.oracle_dp_io import COLUMNS
            shape={'table':'source_block' if kind=='block_payload' else kind,
                   'columns':{columns[c]:{'type':'null','max_bytes':0,'has_null':False,'has_empty':False}
                              for c in COLUMNS[kind] if columns[c]},
                   'primary_key':[columns[c] for c in KEYS[kind] if columns[c]],'rows':0}
            while batch := source_batch(db, kind, version, cursor):
                for row in batch:
                    logical={columns[c]:v for c,v in row.items() if columns[c]}
                    if kind=='block_payload' and row['JSON_TEXT_ELIDED']:
                        body=json.loads(logical['json']);body['text']=row['TEXT']
                        logical['json']=json.dumps(body,ensure_ascii=False,separators=(',',':'))
                    _column_shapes(shape,logical)
                    if kind=='block_payload':
                        from semantic_runtime.folder_navigation import normalized
                        yield record('native.block_literal',{'text':normalized(row['TEXT'] or '')},
                                     key=[row['DOCUMENT_ID'],row['BLOCK_ID']],document_id=row['DOCUMENT_ID'],owner_id=str(row['BLOCK_ID']))
                    key = [row[c] for c in KEYS[kind]]
                    value = {'source_kind': kind, 'source_key': key, 'source_sha256': digest(row)}
                    yield record('source.integrity', value, key=[kind,key],
                                 document_id=row['DOCUMENT_ID'], lookup_id=digest([kind,key]), owner_id=kind)
                count += len(batch)
                cursor = [batch[-1][c] for c in KEYS[kind] if c != 'DATASET_VERSION']
            shape['rows']=count
            yield record('source.schema',shape,key=kind,lookup_id=shape['table'],owner_id=kind)
    finally:
        db.close()

def projected_rows(path,relative,source,*,mode,excluded_tables=(),resume=None):
    from itertools import islice
    from reduced_export import asset_rows,ResumeRow
    phase=resume.get('phase') if resume else None
    if phase not in (None,'asset','source','native'):raise ValueError('QUERY_PRODUCER_CURSOR_PHASE')
    if phase!='native':
        if relative=='store.sqlite':
            if phase not in (None,'source'):raise ValueError('QUERY_PRODUCER_CURSOR_ASSET')
            offset=resume['offset'] if resume else 0
            for n,row in enumerate(islice(source_records(path,source),offset,None),start=offset+1):
                yield ResumeRow(row,{'phase':'source','offset':n})
        else:
            if phase not in (None,'asset'):raise ValueError('QUERY_PRODUCER_CURSOR_SOURCE')
            yield from asset_rows(path,relative,excluded_tables=excluded_tables,resume=resume)
    from lawrag.pipeline.oracle_query_navigation_publish import records
    offset=resume['offset'] if phase=='native' else 0
    for n,row in enumerate(islice(records(path,relative,source),offset,None),start=offset+1):
        yield ResumeRow(row,{'phase':'native','offset':n})
