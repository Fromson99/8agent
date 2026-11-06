"""Bound ZIP parts -> precreated Gold -> query publication -> native vectors.

Only this module orchestrates the notebook run. Historical loader entry points and
their development-schema/checkpoint defaults are never invoked.
"""
from contextlib import ExitStack
import json
from pathlib import Path
import re
import time

from prod_config import ROOT, target
import run_full as base
from fast_insert import Contract as InsertContract
from fast_loader import Job as InsertJob, load_sources, load_query, ready, publish
from gold_io import Stop, canonical, digest, literal


class Contract(InsertContract):
    def bind_registration_time(self, db):
        table = self.tables['SRC_POST']
        column = table['columns']['RGSN_AITM']
        rows = db.query(
            'SELECT DATA_TYPE,NULLABLE,DATA_DEFAULT FROM ALL_TAB_COLUMNS WHERE OWNER='
            + literal(table['owner']) + ' AND TABLE_NAME=' + literal(table['name'])
            + ' AND COLUMN_NAME=' + literal(column['name']))
        field = self.table('SRC_POST') + '.' + column['name']
        if len(rows) != 1:
            raise Stop('REGISTRATION_TIME_METADATA_MISSING:' + field)
        row = rows[0]
        typ = row['DATA_TYPE']
        nullable = row['NULLABLE']
        default = (row['DATA_DEFAULT'] or '').strip().upper() or None
        if typ == 'TIMESTAMP(6) WITH TIME ZONE':
            supported = nullable == 'N' and default == 'SYSTIMESTAMP'
        else:
            supported = (re.fullmatch(r'TIMESTAMP\([0-9]\)', typ or '') and nullable in ('Y', 'N')
                         and default in (None, 'NULL', 'SYSTIMESTAMP', 'CURRENT_TIMESTAMP', 'LOCALTIMESTAMP'))
        if not supported:
            raise Stop('REGISTRATION_TIME_UNSUPPORTED:' + field + ' ' + canonical(row))
        column.update(type=typ, required=nullable == 'N', default=default)
        self.sha256 = digest(self.value)
        return dict(column)

    def generated_insert_columns(self, key):
        if key == 'SRC_POST':
            column = self.tables[key]['columns']['RGSN_AITM']
            if column['default'] in (None, 'NULL') and re.fullmatch(r'TIMESTAMP\([0-9]\)', column['type']):
                return {'RGSN_AITM': 'CAST(SYSTIMESTAMP AS ' + column['type'] + ')'}
        return {}

    def create(self, db, emit, *, allow_create=False):
        if allow_create:raise Stop('PRODUCTION_DDL_FORBIDDEN')
        return super().create(db,emit,allow_create=False)

    def batch(self, key, rows, **kwargs):
        rows = self.validate(key, rows)
        return super().batch(key, rows, **kwargs)


class Job(InsertJob):
    def __init__(self, db, contract, directory, binding, progress):
        self.db, self.contract, self.directory, self.progress = db, contract, directory, progress
        self.path = directory/'state.json'
        self.state = base.read(self.path) if self.path.exists() else {
            'binding': binding, 'status': 'NEW', 'source': {}, 'query': {},
            'publication': {}, 'pending': None, 'deadline': time.time()+7*86400}
        if self.state['binding'] != binding:
            raise Stop('FLOW_LOAD_BINDING_CHANGED')
        self.save()

    def guard(self):
        super().guard()
        if time.time() >= self.state['deadline']:
            raise Stop('FLOW_ORIGINAL_DEADLINE_EXPIRED')


def code_binding():
    value = base.read(ROOT/'FLOW_MANIFEST.json')
    for name, expected in value['files'].items():
        path = (ROOT/name).resolve(strict=True)
        if ROOT not in path.parents or base.file_hash(path) != expected:
            raise Stop('FLOW_PACKAGE_HASH_CHANGED')
    return digest(value)


def fixed(path, value):
    if path.exists():
        if base.read(path) != value:
            raise Stop('FLOW_SAVED_BINDING_CHANGED:'+path.name)
    else:
        base.atomic(path, value)
    return value


def connection(cfg):
    import dataiku
    from jdbc_transport import install
    install(base)
    return base.Database(dataiku.SQLExecutor2(connection=cfg['params']['ORACLE_CONNECTION']))


def database_identity(db, cfg, contract):
    rows = db.query("SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS LOGIN_USER, "
                    "SYS_CONTEXT('USERENV','DB_UNIQUE_NAME') AS DB_NAME, "
                    "SYS_CONTEXT('USERENV','SERVICE_NAME') AS SERVICE_NAME FROM DUAL")
    if len(rows) != 1 or rows[0]['LOGIN_USER'] != cfg['params']['EXPECTED_DB_USER']:
        raise Stop('FLOW_DATABASE_USER_MISMATCH')
    objects = base.object_binding(db, contract)
    return {'database': rows, 'objects': objects,
            'registration_time': contract.bind_registration_time(db)}


def parts(cfg):
    import dataiku
    from lawrag.pipeline.oracle_legacy_parts import inspect_parts
    from prod_storage import open_folder
    folder = open_folder(cfg,'input')
    names = folder.list_paths_in_partition()
    params = cfg['params']
    info = inspect_parts(folder.get_download_stream, names,
                         original_file=params.get('ORIGINAL_SHA_FILE', ''),
                         parts_file=params.get('PARTS_SHA_FILE', ''))
    if info['part_count'] != params['EXPECTED_PARTS'] or info['archive_name'] != params['EXPECTED_ARCHIVE']:
        raise Stop('FLOW_ARCHIVE_OR_PART_COUNT_MISMATCH')
    return folder, names, info


def input_binding(info):
    return {k: info[k] for k in ('archive_name', 'archive_sha256', 'parts', 'part_count')}


def restored(root):
    receipt = base.read(root/'restore.json')
    generation = Path(receipt['generation']).resolve(strict=True)
    if generation != (root/'restored/generation').resolve():
        raise Stop('FLOW_GENERATION_PATH')
    return generation


def prepared(root):
    from lawrag.pipeline.oracle_query_package import immutable_inputs
    result = base.read(root/'prepared.json')
    generation, _, _, files, _ = immutable_inputs(restored(root))
    if files != result['files']:
        raise Stop('FLOW_GENERATION_CHANGED')
    return generation, result


def prepare(root, contract, progress):
    from lawrag.pipeline import oracle_query_package as package, oracle_query_publish as publisher
    from fast_export import projected_rows
    from legacy_gold_mapping import mapped_query
    from lawrag.pipeline import oracle_migration as migration
    from semantic_runtime.oracle_dp_io import KEYS
    generation, manifest, items, files, selected = package.immutable_inputs(restored(root))
    if (root/'prepared.json').exists():
        _, result = prepared(root)
        return result
    source = package.offline_source(generation, manifest, items, selected,
                                    tick=lambda: base.resource_check(root))
    # Detect field widths before starting Oracle INSERTs.
    db = migration.source_open(generation/'store.sqlite')
    try:
        for kind, (key, _, _) in base.SOURCE_MAP.items():
            cursor = None
            while batch := migration.source_batch(db, kind, source['dataset_version'], cursor):
                contract.validate(key, [base.source_row(kind, r)[1] for r in batch])
                cursor = [batch[-1][c] for c in KEYS[kind] if c != 'DATASET_VERSION']
    finally:
        db.close()
    paths = {name: sha for name, sha in files.items() if name.endswith('.sqlite')}
    tables = {}
    for relative, expected in paths.items():
        path = generation/relative
        if relative != 'store.sqlite':
            tables.update(publisher.asset_schema(path, relative))
        count = 0
        for row in projected_rows(path, relative, source, mode='full'):
            contract.validate('SRCH_ROW', [mapped_query('0'*64, row)])
            state = tables.setdefault(row['kind'], {'asset': relative, 'rows': 0, 'chain': '0'*64})
            state['rows'] += 1
            state['chain'] = digest([state['chain'], row['row_id'], row['sha256']])
            publisher._column_shapes(state, row['value'])
            count += 1
            if count % 50000 == 0:
                base.resource_check(root)
                progress.emit('PREPARE_QUERY', asset=relative, rows=count)
        if base.file_hash(path) != expected:
            raise Stop('FLOW_PREPARE_INPUT_CHANGED')
    query = package.query_manifest(generation, source, paths, tables, items)
    # Identify the actual projection implementation, not an older publisher.
    query['gold_projection'] = {'version': 'gold-zip-flow-full-v1',
                                'sha256': base.file_hash(Path(__import__('fast_export').__file__))}
    result = {'files': files, 'source': source, 'query': query, 'paths': paths}
    fixed(root/'prepared.json', result)
    return result


def load_job(db, cfg, root, contract, progress, code):
    generation, data = prepared(root)
    identity = database_identity(db, cfg, contract)
    inspected = base.read(root/'inspect.json')
    if identity != inspected['target'] or inspected['contract'] != contract.sha256 or inspected['code'] != code:
        raise Stop('FLOW_DATABASE_OR_CODE_CHANGED')
    binding = {'code': code, 'contract': contract.sha256, **identity,
               'generation': str(generation), 'files': data['files'],
               'source_release': digest(data['source']), 'query_release': digest(data['query'])}
    work = root/'load'; work.mkdir(exist_ok=True)
    if not (work/'state.json').exists():
        # A new workspace cannot adopt an earlier job's rows or reset its budgets.
        checks=[(key,'MNFST_HASH_VALU',data['source']['dataset_version'])
                for key in ('DOC_VER','DOC_UNIT','DOC_BLK')]
        checks += [('SRC_POST','DOC_POST_HASH_VALU',digest(data['source'])),
                   ('SRCH_ROW','RFRN_POST_HASH_VALU',digest(data['query'])),
                   ('SRCH_POST','RFRN_POST_HASH_VALU',digest(data['query'])),
                   ('SRCH_CHNL','RFRN_CHNL_NAME','g19_'+digest(data['query'])[:24]),
                   ('VCTR_HEAD','RFRN_POST_HASH_VALU',digest(data['query']))]
        for key,field,value in checks:
            rows=db.query('SELECT COUNT(*) AS N FROM '+contract.table(key)+' WHERE '+
                          contract.col(key,field)+'='+literal(value)+' AND ROWNUM<=1')
            if rows != [{'N':0}]:
                raise Stop('EXISTING_RELEASE_REQUIRES_ORIGINAL_CHECKPOINT:'+contract.table(key))
    return Job(db, contract, work, binding, progress), generation, data


def vectors(db, cfg, root, contract, progress, code, parent, generation, data):
    import dataiku
    import vector_stage as vector
    from lawrag.pipeline import oracle_migration as migration
    from mesh_embedding import settings
    from structure_segments import POLICY
    from vector_plan import prepare as plan
    if parent.state.get('status') != 'SOURCE_QUERY_PUBLISHED' or not ready(parent, data['source'], data['query'], data['paths']):
        raise Stop('FLOW_PUBLISH_SOURCE_QUERY_FIRST')
    source, query = data['source'], data['query']
    config = settings({'LEGAL_EMBED_LLM_ID': cfg['params']['EMBED_MODEL'],
                       'LEGAL_EMBED_DIMENSIONS': cfg['params']['EMBED_DIMENSIONS']})
    nav = source['source_manifest']['navigation']['path']+'/navigation.sqlite'
    if nav not in data['files']:
        raise Stop('FLOW_NAVIGATION_NOT_BOUND')
    manifest = {'schema_version': 'gold-vector-manifest-preview-v1', 'query_id': digest(query),
                'source_release_id': digest(source), 'dataset_version': source['dataset_version'],
                'documents': sorted(source['source_manifest']['scope']['document_version_ids']),
                'profile': config, 'segment_profile': POLICY}
    binding = {'code': code, 'contract': contract.sha256, 'parent': digest(parent.state['binding']),
               'generation': str(generation), 'navigation_path': nav,
               'signatures': vector.signatures(generation, nav), 'manifest': manifest}
    work = root/'vectors'; work.mkdir(exist_ok=True)
    job = vector.VectorJob(db, contract, work, binding, progress)
    if job.state['status'] != vector.COMPLETE:
        with ExitStack() as stack:
            store = migration.source_open(generation/'store.sqlite'); stack.callback(store.close)
            navigation = migration.source_open(generation/nav); stack.callback(navigation.close)
            job.plan, meta = plan(job, store, navigation, source, migration)
            stack.callback(job.plan.close)
            job.total = meta['rows']; job.state['planned_total_rows'] = job.total; job.save()
            project = dataiku.api_client().get_project(cfg['project'])
            vector.build(job, store, navigation, source, query, config, project, migration)
    result = {'publication_id': job.state['publication_id'], 'rows': job.state['rows'],
              'profile': config, 'embedding_calls': job.state['embedding_calls'], 'activated': False}
    if cfg['params'].get('ACTIVATE_NEW_VECTOR_HEAD', True):
        # Immutable insert only for this new query. Never replace an existing head.
        row = {'RFRN_POST_HASH_VALU': digest(query), 'VCTR_POST_ID': result['publication_id'], 'CHAN_NO': 1}
        sql, binds = __import__('gold_io').Contract.batch(contract, 'VCTR_HEAD', [row])
        db.block(sql, binds, transaction_managed=True)
        result['activated'] = True
    fixed(root/'vector.json', result)
    return result


def report(db, cfg, root, contract, data):
    source, query = data['source'], data['query']
    vector = base.read(root/'vector.json')
    expected = {key: source['source_rows'][kind]['rows'] for kind, (key, _, _) in base.SOURCE_MAP.items()}
    expected['SRCH_ROW'] = sum(t['rows'] for t in query['tables'].values())
    expected['VCTR_ITEM'] = vector['rows']
    count = {}
    for key, n in expected.items():
        logical, value = ('MNFST_HASH_VALU', source['dataset_version']) if key.startswith('DOC_') else (
            ('RFRN_POST_HASH_VALU', digest(query)) if key == 'SRCH_ROW' else ('VCTR_POST_ID', vector['publication_id']))
        rows = db.query('SELECT COUNT(*) AS N FROM '+contract.table(key)+' WHERE '+contract.col(key, logical)+'='+literal(value))
        if rows != [{'N': n}]:
            raise Stop('FLOW_FINAL_ROW_COUNT:'+key)
        count[key] = n
    for key, logical, value, content, wanted in (
        ('SRC_POST','DOC_POST_HASH_VALU',digest(source),'DOC_POST_IFMN_CTNT',source),
        ('SRCH_POST','RFRN_POST_HASH_VALU',digest(query),'RFRN_POST_IFMN_CTNT',query)):
        rows = db.query('SELECT '+contract.col(key, content)+' AS BODY FROM '+contract.table(key)+' WHERE '+contract.col(key, logical)+'='+literal(value))
        if len(rows) != 1 or json.loads(rows[0]['BODY']) != wanted:
            raise Stop('FLOW_PUBLICATION_READBACK:'+key)
    if vector['activated']:
        rows = db.query('SELECT '+contract.col('VCTR_HEAD','VCTR_POST_ID')+' AS PUB,'+contract.col('VCTR_HEAD','CHAN_NO')+
                        ' AS REV FROM '+contract.table('VCTR_HEAD')+' WHERE '+contract.col('VCTR_HEAD','RFRN_POST_HASH_VALU')+'='+literal(digest(query)))
        if rows != [{'PUB': vector['publication_id'], 'REV': 1}]:
            raise Stop('FLOW_VECTOR_HEAD_READBACK')
    registration = base.read(ROOT/'registration_current.json')
    mapping = {k: registration[k] for k in ('schema_version', 'revision', 'variant')}
    mapping['owner'] = next(iter(contract.tables.values()))['owner']
    mapping['tables'] = {key: {k: t[k] for k in ('name','columns','primary_key','indexes')} for key, t in contract.tables.items()}
    if cfg['params']['TARGET_MODE'] == 'GOLD':
        fixed(root/'serving-mapping.json', mapping)
    fixed(root/'documents.json', sorted(source['source_manifest']['scope']['document_version_ids']))
    fixed(root/'embedding-profile.json', vector['profile'])
    value = {'status': 'GOLD_LOADED', 'counts': count, 'source_release_id': digest(source),
             'query_release_id': digest(query), 'channel': 'g19_'+digest(query)[:24], 'vector': vector,
             'full_values_verified': False, 'row_counts_and_publications_verified': True,
             'serving_mapping_sha256': base.file_hash(root/'serving-mapping.json') if cfg['params']['TARGET_MODE']=='GOLD' else None,
             'serving_switched': False, 'ontology_published': False}
    fixed(root/'report.json', value)
    return value


def execute(stage, cfg, root):
    root = Path(root).resolve(strict=True)
    if cfg['target'] != target(cfg['params']):
        raise Stop('FLOW_CONFIG_TARGET_CHANGED')
    code = code_binding()
    fixed(root/'contract.json', cfg['target'])
    contract = Contract(root/'contract.json')
    progress = base.Progress(); progress.thread.start()
    db = None
    try:
        if stage == 'inspect':
            _, _, info = parts(cfg)
            db = connection(cfg)
            identity = database_identity(db, cfg, contract)
            contract.create(db, progress.emit, allow_create=False)
            # Parse the real INSERT privilege without executing a write.
            writable={'DOC_VER','DOC_UNIT','DOC_BLK','SRCH_ROW','SRC_POST','SRCH_POST',
                      'SRCH_CHNL','VCTR_ITEM','VCTR_POST','VCTR_HEAD'}
            for key,t in contract.tables.items():
                db.query('SELECT 1 AS N FROM '+contract.table(key)+' WHERE 1=0')
                if key in writable:
                    cols=','.join(c['name'] for c in t['columns'].values())
                    db.block('BEGIN IF FALSE THEN INSERT INTO '+contract.table(key)+' ('+cols+
                             ') SELECT '+cols+' FROM '+contract.table(key)+' WHERE 1=0; END IF; END;')
            result = {'code': code, 'contract': contract.sha256, 'input': input_binding(info), 'target': identity}
            return fixed(root/'inspect.json', result)
        if stage == 'restore':
            from lawrag.pipeline import oracle_legacy_parts as legacy, oracle_existing_zip as archive
            folder, names, info = parts(cfg)
            inspected = base.read(root/'inspect.json')
            if inspected['input'] != input_binding(info) or inspected['code'] != code:
                raise Stop('FLOW_ARCHIVE_CHANGED')
            params = cfg['params']
            path = legacy.join_parts(folder.get_download_stream, names, root/'joined',
                                     original_file=params.get('ORIGINAL_SHA_FILE',''), parts_file=params.get('PARTS_SHA_FILE',''),
                                     binding=digest({'project':cfg['project'],'folder':cfg['input_folder']}))
            result = archive.restore(path, root/'restored', expected_sha=info['archive_sha256'])
            return fixed(root/'restore.json', result)
        if stage == 'prepare':
            data = prepare(root, contract, progress)
            return {'source_release_id':digest(data['source']), 'query_release_id':digest(data['query']),
                    'query_rows':sum(t['rows'] for t in data['query']['tables'].values())}
        db = connection(cfg)
        job, generation, data = load_job(db, cfg, root, contract, progress, code)
        if stage == 'source':
            load_sources(job, generation, data['source'])
        elif stage == 'search':
            if any(job.state['source'].get(k,{}).get('rows') != v['rows'] for k,v in data['source']['source_rows'].items()):
                raise Stop('FLOW_LOAD_SOURCE_FIRST')
            load_query(job, generation, data['source'], data['query'], data['paths'], 'full')
        elif stage == 'publish':
            if not ready(job, data['source'], data['query'], data['paths']):
                raise Stop('FLOW_LOAD_INCOMPLETE')
            publish(job, data['source'], data['query'])
            saved = db.query('SELECT COUNT(*) AS N FROM ' + contract.table('SRC_POST') +
                             ' WHERE ' + contract.col('SRC_POST', 'DOC_POST_HASH_VALU') + '=' +
                             literal(digest(data['source'])) + ' AND ' +
                             contract.col('SRC_POST', 'RGSN_AITM') + ' IS NOT NULL')
            if saved != [{'N': 1}]:
                raise Stop('REGISTRATION_TIME_READBACK_FAILED:' + contract.table('SRC_POST'))
        elif stage == 'vector':
            return vectors(db, cfg, root, contract, progress, code, job, generation, data)
        elif stage == 'report':
            return report(db, cfg, root, contract, data)
        else:
            raise Stop('FLOW_STAGE_UNKNOWN')
        return {'status':job.state['status'], 'source':job.state['source'], 'query':job.state['query']}
    finally:
        if db is not None: db.close()
        progress.stop.set(); progress.thread.join(timeout=2)
