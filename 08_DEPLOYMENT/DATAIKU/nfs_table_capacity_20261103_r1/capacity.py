"""Read-only SQLite inventory and explicitly assumed Oracle capacity scenarios.

No loader imports, source changes, DDL, model calls or network access.
Dataiku restored copies and live NFS mounts are distinguished in every report.
"""
import base64
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import time
import uuid

VERSION = 'nfs-table-capacity-20261103-r1'
GIB = 1024 ** 3
SCENARIOS = {
    'A': dict(size_factor=.8, heap_fill=.90, index_fill=.90, lob_fill=.95, lob_unit=512, unknown_chars=256),
    'B': dict(size_factor=1., heap_fill=.85, index_fill=.75, lob_fill=.90, lob_unit=2048, unknown_chars=1024),
    'C': dict(size_factor=1.5, heap_fill=.70, index_fill=.60, lob_fill=.75, lob_unit=8192, unknown_chars=4096),
}
SOURCE_COLUMNS = {
    'document': ('DOC_VER', dict(zip('dataset_version document_id name source_artifact_sha256 json'.split(),
                   'MNFST_HASH_VALU DOC_ID DOC_NAME DOC_HASH_VALU DOC_ADDN_IFMN_CTNT'.split()))),
    'source_unit': ('DOC_UNIT', dict(zip('dataset_version document_id unit_id parent_id json'.split(),
                   'MNFST_HASH_VALU DOC_ID STRC_UNIT_ID UPPR_STRC_UNIT_ID STRC_UNIT_ADDN_IFMN_CTNT'.split()))),
    'block_payload': ('DOC_BLK', dict(zip('dataset_version document_id block_id unit_id text source_artifact_sha256 json json_text_elided'.split(),
                   'MNFST_HASH_VALU DOC_ID BODY_SLC_ID STRC_UNIT_ID BODY_CTNT DOC_HASH_VALU BODY_SLC_ADDN_IFMN_CTNT ADD_INFO_TEXT_OMIT_YN'.split()))),
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def read_json(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(32 * 1024 ** 2 + 1)
    if len(raw) > 32 * 1024 ** 2:
        raise ValueError('METADATA_TOO_LARGE')
    return json.loads(raw)


def signature(path):
    s = Path(path).stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def qi(name):
    return '"' + name.replace('"', '""') + '"'


def safe_path(root, relative):
    path = (Path(root) / relative).resolve(strict=True)
    path.relative_to(Path(root).resolve())
    return path


def query(db, sql, seconds, parameters=()):
    deadline = time.monotonic() + seconds
    db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
    try:
        return [dict(r) for r in db.execute(sql, parameters)]
    finally:
        db.set_progress_handler(None, 0)


def db_open(path):
    for suffix in ('-wal', '-journal'):
        p = Path(str(path) + suffix)
        if p.exists() and p.stat().st_size:
            raise ValueError('NONEMPTY_JOURNAL_SOURCE_MUST_BE_QUIESCENT')
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=3)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    db.execute('PRAGMA cache_size=-8192')
    db.execute('PRAGMA mmap_size=0')
    db.execute('PRAGMA temp_store=FILE')
    return db


def sample_rows(db, table, n, seconds):
    """Bounded prefix, NOT random. Skip oversize rows and disclose them."""
    cols = [r['name'] for r in query(db, 'PRAGMA table_info(' + qi(table) + ')', seconds)]
    if not cols:
        raise ValueError('NO_COLUMNS')
    total = '+'.join('COALESCE(length(CAST(' + qi(c) + ' AS BLOB)),0)' for c in cols)
    expr = ','.join('CASE WHEN (' + total + ')<=4194304 THEN ' + qi(c) + ' END AS ' + qi(c) for c in cols)
    sql = 'SELECT (' + total + ') AS "__capacity_row_bytes__",' + expr + ' FROM ' + qi(table) + ' LIMIT ?'
    rows = query(db, sql, seconds, (n,))
    good, skipped = [], 0
    for row in rows:
        if row.pop('__capacity_row_bytes__') > 4194304:
            skipped += 1
        else:
            good.append(row)
    return good, skipped


def query_value(row, table):
    value = dict(row)
    if table == 'source_request' and isinstance(value.get('response'), bytes):
        value['response'] = base64.b64encode(value['response']).decode('ascii')
    if any(isinstance(v, bytes) for v in value.values()):
        raise ValueError('UNSUPPORTED_BLOB_PROJECTION')
    return value


def mapped_query(row, table, kind):
    def first(*names):
        for name in names:
            if row.get(name) is not None and str(row[name]):
                return str(row[name])
        return None
    def key(value):
        return 'sha256:' + digest(value) if value is not None and len(value.encode()) > 512 else value
    return dict(RFRN_POST_HASH_VALU='0'*64, RFRN_DTA_TYPE_VALU=kind, RFRN_DTA_ID='0'*64,
                DOC_ID=first('document_id'), RFRN_DTA_IDNF_CTNT=key(first('id', 'key', 'term_id', 'node_id')),
                BLNG_DTA_IDNF_CTNT=key(first('source_id', 'reference_id', 'definition_id')),
                TAGT_DTA_IDNF_CTNT=key(first('target_id', 'target', 'parent_id')),
                SRCH_DATA_HASH_VALU='0'*64, SRCH_DATA_CTNT=canonical(query_value(row, table)))


def mapped_source(row, table):
    key, columns = SOURCE_COLUMNS[table]
    source = dict(row, dataset_version='0'*64)
    values = {target: source[name] for name, target in columns.items()}
    if table == 'block_payload':
        v = values['ADD_INFO_TEXT_OMIT_YN']
        values['ADD_INFO_TEXT_OMIT_YN'] = 'Y' if v == 1 else 'N' if v == 0 else None
    return key, values


def row_cost(values, table, scenario, *, fallback=False):
    """Sizing model, not Oracle allocation measurement or a confidence bound.

    VARCHAR assumes AL32UTF8; CLOB assumes AL16UTF16. No compression/dedup.
    Heap/LOB locator and index entry overhead are explicit planning constants.
    """
    factor = 1. if fallback else scenario['size_factor']
    heap, lob, scalar = 3., 0., {}
    for name, column in table['columns'].items():
        value = values.get(name)
        if value is None or value == '':
            heap += 1
            scalar[name] = 0.
            continue
        if 'CLOB' in column['type']:
            n = len(str(value).encode('utf-16-be')) * factor
            heap += 40  # Locator/header assumption, not a measured fixed Oracle value.
            if n <= 3900:
                heap += n
            else:
                heap += 8
                lob += math.ceil(n / scenario['lob_unit']) * scenario['lob_unit'] / scenario['lob_fill'] + 64
            scalar[name] = 0.
        else:
            n = 12. if 'NUMBER' in column['type'] else len(str(value).encode('utf-8')) * factor
            scalar[name] = n
            heap += n + (1 if n < 250 else 3)
    indexes = [table['primary_key']] + table.get('indexes', [])
    index = sum(12 + sum(scalar.get(c, 0) + 1 for c in columns) for columns in indexes) / scenario['index_fill']
    return {'heap': heap / scenario['heap_fill'], 'lob': lob, 'index': index,
            'total': heap / scenario['heap_fill'] + lob + index}


def estimate(count, values, table, *, assumed=False):
    result = {}
    for label, scenario in SCENARIOS.items():
        samples = values
        if assumed:
            samples = [{name: ('x'*scenario['unknown_chars'] if 'CLOB' in column['type'] else 'x'*64)
                        for name, column in table['columns'].items()}]
        if count and not samples:
            raise ValueError('NO_SAMPLE')
        costs = [row_cost(row, table, scenario, fallback=assumed) for row in samples]
        for component in ('heap', 'lob', 'index', 'total'):
            result[label + '_' + component + '_bytes'] = math.ceil(count * sum(c[component] for c in costs) / len(costs)) if costs else 0
    return result


def inspect_database(path, relative, config, kinds, contract):
    before = signature(path)
    result = dict(file=relative, signature=before, status='STARTED', objects=[], tables=[], estimates=[])
    db = db_open(path)
    try:
        catalogue = query(db, "SELECT name,type,tbl_name,sql,rootpage FROM sqlite_master WHERE type IN ('table','index','view')", 10)
        by_name = {r['name']: r for r in catalogue}
        virtual = {r['name'] for r in catalogue if 'CREATE VIRTUAL TABLE' in (r['sql'] or '').upper()}
        # SQLite table_list is preferred: don't classify arbitrary prefix matches as shadows.
        try:
            shadow = {r['name'] for r in query(db, 'PRAGMA table_list', 10) if r['type'] == 'shadow'}
        except sqlite3.Error:
            shadow = set()
        if not shadow:
            shadow = {v+s for v in virtual for s in ('_data','_idx','_content','_docsize','_config','_segments','_segdir','_stat') if v+s in by_name}
        page_size = db.execute('PRAGMA page_size').fetchone()[0]
        page_count = db.execute('PRAGMA page_count').fetchone()[0]
        free_count = db.execute('PRAGMA freelist_count').fetchone()[0]
        result.update(page_size=page_size, page_count=page_count, freelist_bytes=free_count*page_size)
        try:
            stats = query(db, 'SELECT name,SUM(pgsize) AS bytes,SUM(payload) AS payload_bytes,SUM(unused) AS unused_bytes,'
                          "SUM(CASE WHEN pagetype='leaf' THEN ncell ELSE 0 END) AS leaf_cells,SUM(ncell) AS all_cells FROM dbstat GROUP BY name", config['dbstat_seconds'])
            result['dbstat_status'] = 'MEASURED'
        except sqlite3.Error as exc:
            stats = []
            result['dbstat_status'] = 'UNAVAILABLE_OR_TIMEOUT:' + type(exc).__name__
        result['objects'] = stats
        stat = {r['name']: r for r in stats}
        result['btree_bytes'] = sum(r['bytes'] for r in stats) if stats else None
        result['other_bytes'] = page_count*page_size-free_count*page_size-result['btree_bytes'] if stats else None
        schema_only = stat.get('sqlite_schema', stat.get('sqlite_master', {})).get('bytes', 0)
        result['schema_bytes'] = schema_only if stats else None
        for entry in sorted(catalogue, key=lambda r: r['name']):
            name = entry['name']
            if entry['type'] == 'index' or name in shadow:
                continue
            category = 'VIEW' if entry['type'] == 'view' else 'VIRTUAL' if name in virtual else 'SYSTEM_TABLE' if name.startswith('sqlite_') else 'TABLE'
            members = [name] + [r['name'] for r in catalogue if r['type'] == 'index' and r['tbl_name'] == name]
            if name in virtual:
                owned = [s for s in shadow if s.startswith(name+'_')]
                members = owned + [r['name'] for r in catalogue if r['type'] == 'index' and r['tbl_name'] in owned]
            # WITHOUT ROWID secondary PK representation is already in the table btree.
            members = sorted(set(members))
            size = 0 if category == 'VIEW' else sum(stat[m]['bytes'] for m in members if m in stat) if stats else None
            own = stat.get(name)
            count = None
            if own and category in ('TABLE','SYSTEM_TABLE'):
                count = own['all_cells'] if 'WITHOUT ROWID' in (entry['sql'] or '').upper() else own['leaf_cells']
            kind_specs = [(k,s) for k,s in kinds.items() if s.get('asset') == relative and s.get('table') == name]
            planned = kind_specs[0][1]['rows'] if len(kind_specs) == 1 else None
            row = dict(file=relative, table=name, category=category, table_and_index_bytes=size,
                       physical_rows=count, declared_projection_rows=planned,
                       members=';'.join(members), size_status='VIEW_NO_STORAGE' if category=='VIEW' else result['dbstat_status'])
            result['tables'].append(row)
            needed = bool(kind_specs) or (relative == 'store.sqlite' and name in SOURCE_COLUMNS)
            if not needed:
                continue
            print('  표본:', relative, name, flush=True)
            try:
                samples, skipped = sample_rows(db, name, config['sample_rows'], config['sample_seconds'])
                row.update(sample_rows=len(samples), oversize_skipped=skipped, sample_state='PREFIX_NOT_RANDOM')
                usable = bool(samples) and not skipped
            except (sqlite3.Error, ValueError) as exc:
                samples, usable = [], False
                row.update(sample_rows=0, sample_state='UNAVAILABLE:'+type(exc).__name__)
            for kind, spec in kind_specs:
                values = []
                try:
                    values = [mapped_query(r, name, kind) for r in samples] if usable else []
                except (ValueError, TypeError):
                    row['sample_state'] = 'UNSUPPORTED_PROJECTION'
                item = dict(kind=kind, asset=relative, logical_table=name, target='SRCH_ROW', rows=spec['rows'],
                            sample_rows=len(values), basis='PREFIX_VALUE_SAMPLE' if values else 'ASSUMED_UNMEASURED')
                item.update(estimate(spec['rows'], values, contract['tables']['SRCH_ROW'], assumed=not values))
                result['estimates'].append(item)
            if relative == 'store.sqlite' and name in SOURCE_COLUMNS:
                source_count = count
                if source_count is None:
                    try:
                        source_count = query(db, 'SELECT COUNT(*) AS n FROM '+qi(name), config['sample_seconds'])[0]['n']
                    except sqlite3.Error:
                        pass
                if source_count is not None:
                    target = SOURCE_COLUMNS[name][0]
                    values = [mapped_source(r,name)[1] for r in samples] if usable else []
                    item = dict(kind='source_table.'+name, asset=relative, logical_table=name, target=target,
                                rows=source_count, sample_rows=len(values), basis='PREFIX_VALUE_SAMPLE' if values else 'ASSUMED_UNMEASURED')
                    item.update(estimate(source_count, values, contract['tables'][target], assumed=not values))
                    result['estimates'].append(item)
        result['status'] = 'MEASURED' if result['dbstat_status']=='MEASURED' else 'PARTIAL'
    finally:
        db.close()
    if signature(path) != before:
        raise ValueError('SOURCE_CHANGED_DURING_INSPECTION')
    return result


def inventory(root):
    files, skipped, seen = [], [], set()
    def on_error(exc):
        skipped.append(dict(path=str(exc.filename), reason=type(exc).__name__))
    for directory, dirs, names in os.walk(root, followlinks=False, onerror=on_error):
        for name in list(dirs):
            p = Path(directory)/name
            if p.is_symlink():
                dirs.remove(name); skipped.append(dict(path=str(p.relative_to(root)),reason='SYMLINK_DIRECTORY'))
        for name in sorted(names):
            p = Path(directory)/name
            if p.is_symlink():
                skipped.append(dict(path=str(p.relative_to(root)),reason='SYMLINK_FILE')); continue
            try:
                s = p.stat()
                if not p.is_file():
                    skipped.append(dict(path=str(p.relative_to(root)),reason='NOT_REGULAR')); continue
                key=(s.st_dev,s.st_ino)
                allocated = getattr(s,'st_blocks',None)
                duplicate = key in seen
                seen.add(key)
                with p.open('rb') as stream:
                    is_sqlite=stream.read(16)==b'SQLite format 3\x00'
                files.append(dict(path=str(p.relative_to(root)), bytes=s.st_size,
                                  allocated_bytes=allocated*512 if allocated is not None else None,
                                  duplicate_inode=duplicate, unique_bytes=0 if duplicate else s.st_size,
                                  unique_allocated_bytes=0 if duplicate else allocated*512 if allocated is not None else None,
                                  sqlite=is_sqlite, signature=signature(p)))
            except OSError as exc:
                skipped.append(dict(path=str(p.relative_to(root)),reason=type(exc).__name__))
    return files, skipped


def save_json(path, value):
    temp=Path(str(path)+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)


def csv_write(path, rows):
    if not rows:
        Path(path).write_text('status\nNO_ROWS\n',encoding='utf-8-sig'); return
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w',encoding='utf-8-sig',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=fields); w.writeheader()
        for row in rows:
            # Preserve raw values in JSON; prevent Excel treating a filename as a formula.
            w.writerow({k: "'"+v if isinstance(v,str) and v[:1] in ('=','+','-','@','\t','\r') else v for k,v in row.items()})


def with_units(rows):
    return [dict(row, **{key[:-6]+'_gib':round(value/GIB,6) for key,value in row.items()
                         if key.endswith('_bytes') and type(value) in (int,float)}) for row in rows]


def load_descriptor(path, full_state_path=''):
    value=read_json(path)
    body={k:v for k,v in value.items() if k!='checksum'}
    if value.get('checksum')!=digest(body):
        raise ValueError('DESCRIPTOR_CHECKSUM')
    if full_state_path:
        state=read_json(full_state_path)
        plan=state.get('deferred',{}).get('plan',{})
        if body['binding'].get('source')!=plan.get('source_release_id') or body['binding'].get('files')!=plan.get('files'):
            raise ValueError('DESCRIPTOR_STATE_BINDING')
    if any(type(s.get('rows')) is not int or s['rows']<0 for s in body['tables'].values()):
        raise ValueError('INVALID_PLANNED_COUNT')
    return body


def run(config, contract):
    generation=Path(config['generation']).expanduser().resolve(strict=True)
    root=Path(config.get('scan_root') or generation).expanduser().resolve(strict=True)
    generation.relative_to(root)
    output=Path(config['output']).expanduser().resolve()
    if output==root or root in output.parents:
        raise ValueError('REPORT_DIRECTORY_MUST_BE_OUTSIDE_SOURCE')
    binding=dict(config=config,contract_sha256=digest(contract),generation=str(generation),scan_root=str(root),version=VERSION)
    checkpoint_path=output/'REPORT.json'
    if output.exists():
        result=read_json(checkpoint_path)
        if result['binding']!=binding:
            raise ValueError('RESUME_CONFIGURATION_CHANGED_USE_NEW_OUTPUT')
    else:
        output.mkdir(parents=True)
        result=dict(binding=binding,started_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),databases={},errors=[],status='RUNNING')
    result['status']='RUNNING'
    result['forecast_input_validated']=False
    descriptor={}; kinds={}
    descriptor_path=config.get('descriptor')
    if descriptor_path:
        descriptor=load_descriptor(descriptor_path,config.get('full_state',''))
        kinds=descriptor['tables']
        result['descriptor_sha256']=file_sha(descriptor_path)
    files, skipped=inventory(root)
    result.update(files=files,skipped=skipped)
    result['logical_file_bytes']=sum(f['bytes'] for f in files)
    result['unique_inode_file_bytes']=sum(f['unique_bytes'] for f in files)
    result['local_unique_allocated_bytes']=sum(f['unique_allocated_bytes'] for f in files) if all(f['unique_allocated_bytes'] is not None for f in files) else None
    result['nfs_live_verified']=config['source_mode']=='NFS_MOUNT'
    result['nfs_physical_allocated_bytes']=result['local_unique_allocated_bytes'] if result['nfs_live_verified'] else None
    result['notes']=[
        'Scope is the selected scan_root, not the entire NFS server unless you explicitly select that root.',
        'RESTORED_COPY does not measure current NFS allocation, compression, snapshots or other generations.',
        'Views have zero SQLite storage; exported view result rows can consume Oracle storage.',
        'FTS shadow tables are assigned to their virtual parent; object and table CSV totals must not be added together.',
        'A/B/C are sizing assumptions, not confidence intervals or guaranteed bounds. Prefix samples are not random.',
        'Oracle amounts include a single new source/search release only. Existing releases, vector generation, ontology, agent journals, TEMP, UNDO, redo, backups and new growth are not included.',
        'No Oracle compression/dedup assumed. AL32UTF8 scalar and AL16UTF16 CLOB sizes must be checked against SQL metadata.',
        'Directory inventory is not an atomic NFS snapshot. st_blocks is filesystem-reported allocation, not storage-array consumption.',
    ]
    save_json(checkpoint_path,result)
    checked={}
    for relative, expected in descriptor.get('paths',{}).items():
        p=safe_path(generation,relative)
        print('입력 SHA 확인:',relative,flush=True)
        before=signature(p)
        if file_sha(p)!=expected or signature(p)!=before:
            raise ValueError('DESCRIPTOR_INPUT_HASH_MISMATCH:'+relative)
        checked[relative]=before
    result['verified_projection_inputs']=checked
    seen_db={}
    try:
        for f in files:
            if not f['sqlite']:
                continue
            p=root/f['path']
            key=str(p.relative_to(generation)) if p.is_relative_to(generation) else '@outside_generation/'+f['path']
            dbid=str(p.resolve())
            inode=tuple(f['signature'][:2])
            if inode in seen_db:
                result.setdefault('sqlite_aliases',{})[f['path']]=seen_db[inode]
                # Do not double physical accounting; projection of a second logical asset is not inferred.
                continue
            seen_db[inode]=f['path']
            old=result['databases'].get(dbid)
            if old and old.get('signature')==signature(p) and old.get('status')=='MEASURED':
                print('완료 결과 재사용:',key,flush=True); continue
            print('SQLite 용량:',key,flush=True)
            try:
                result['databases'][dbid]=inspect_database(p,key,config,kinds,contract)
            except (OSError,ValueError,sqlite3.Error) as exc:
                result['databases'][dbid]=dict(file=key,status='FAILED',signature=signature(p),error=str(exc),tables=[],objects=[],estimates=[])
            save_json(checkpoint_path,result)
    except KeyboardInterrupt:
        result['status']='INTERRUPTED'
        save_json(checkpoint_path,result)
        raise
    finally:
        export_reports(result,output,contract,kinds,generation)
    for f in files:
        try:
            same=signature(root/f['path'])==f['signature']
        except OSError:
            same=False
        if not same:
            result['status']='SOURCE_CHANGED';save_json(checkpoint_path,result)
            raise ValueError('SOURCE_CHANGED_AFTER_INSPECTION:'+f['path'])
    for relative,before in checked.items():
        if signature(generation/relative)!=before:
            result['status']='SOURCE_CHANGED';save_json(checkpoint_path,result)
            raise ValueError('SOURCE_CHANGED_AFTER_INSPECTION')
    if descriptor_path and file_sha(descriptor_path)!=result['descriptor_sha256']:
        result['status']='DESCRIPTOR_CHANGED';save_json(checkpoint_path,result)
        raise ValueError('DESCRIPTOR_CHANGED')
    result['status']='COMPLETE' if not skipped and all(d['status']=='MEASURED' for d in result['databases'].values()) else 'PARTIAL'
    result['forecast_input_validated']=bool(descriptor)
    save_json(checkpoint_path,result)
    export_reports(result,output,contract,kinds,generation)
    show(result,output)
    return result


def export_reports(result, output, contract, kinds, generation):
    tables=[r for d in result['databases'].values() for r in d.get('tables',[])]
    items=[r for d in result['databases'].values() for r in d.get('estimates',[])]
    found={r['kind'] for r in items}
    for kind,spec in kinds.items():
        if kind in found:
            continue
        item=dict(kind=kind,asset=spec.get('asset'),logical_table=spec.get('table'),target='SRCH_ROW',rows=spec['rows'],sample_rows=0,basis='ASSUMED_SPECIAL_OR_UNAVAILABLE')
        item.update(estimate(spec['rows'],[],contract['tables']['SRCH_ROW'],assumed=True));items.append(item)
    excludes=set()
    try:
        manifest=read_json(generation/'manifest.json')
        excludes={(manifest['navigation']['path']+'/navigation.sqlite','occurrence_keys'),
                  (manifest['glossary']['dictionary'],'entry_corpus_link'),
                  (manifest['glossary']['dictionary'],'entry_definition_link')}
    except (OSError,ValueError,KeyError,TypeError):
        pass
    for r in items:
        r['excluded_in_reduced_scenario']=(r['asset'],r['logical_table']) in excludes
    projected={(s.get('asset'),s.get('table')) for s in kinds.values() if s.get('table')}
    for r in tables:
        r['oracle_mapping_state']='SOURCE_TABLE' if r['file']=='store.sqlite' and r['table'] in SOURCE_COLUMNS else 'PROJECTED_SEARCH_TABLE' if (r['file'],r['table']) in projected else 'FTS_SPECIAL_OR_UNMAPPED_REVIEW_REQUIRED'
    totals=[]
    for policy in ('ORIGINAL','REDUCED_THREE_TABLE_SCENARIO'):
        for target in ('DOC_VER','DOC_UNIT','DOC_BLK','SRCH_ROW'):
            rows=[r for r in items if r['target']==target and (policy=='ORIGINAL' or not r['excluded_in_reduced_scenario'])]
            physical=contract['tables'][target]
            out=dict(policy=policy,target=physical['owner']+'.'+physical['name'],rows=sum(r['rows'] for r in rows),
                     projection_inputs_verified=result.get('forecast_input_validated',False),
                     sampled_plan_rows=sum(r['rows'] for r in rows if r['basis']=='PREFIX_VALUE_SAMPLE'),
                     assumed_plan_rows=sum(r['rows'] for r in rows if r['basis']!='PREFIX_VALUE_SAMPLE'),
                     status='SIZING_SCENARIO' if rows else 'UNMEASURED')
            for label in SCENARIOS:
                for component in ('heap','lob','index','total'):
                    k=label+'_'+component+'_bytes';out[k]=sum(r[k] for r in rows) if rows else None
            totals.append(out)
    result['oracle_tables']=totals
    result['oracle_kind_count']=len(items)
    result['oracle_forecast_scope']='ONE_SOURCE_PLUS_SEARCH_RELEASE; metadata, vectors, ontology and journals unestimated'
    result['oracle_full_database_total_bytes']=None
    csv_write(output/'NFS_FILES.csv',[{k:v for k,v in f.items() if k!='signature'} for f in result['files']])
    csv_write(output/'SQLITE_TABLES.csv',with_units(tables))
    csv_write(output/'SQLITE_OBJECTS.csv',[dict(file=d['file'],**r) for d in result['databases'].values() for r in d.get('objects',[])])
    csv_write(output/'SQLITE_DATABASES.csv',[{k:v for k,v in d.items() if k not in ('signature','tables','objects','estimates')} for d in result['databases'].values()])
    csv_write(output/'ORACLE_BY_KIND.csv',with_units(items))
    csv_write(output/'ORACLE_BY_TABLE.csv',with_units(totals))
    csv_write(output/'ORACLE_NOT_ESTIMATED.csv',[dict(target=t['owner']+'.'+t['name'],status='NOT_ESTIMATED',reason='No row count and future contents supplied for this scope')
              for key,t in contract['tables'].items() if key not in ('DOC_VER','DOC_UNIT','DOC_BLK','SRCH_ROW')])
    csv_write(output/'UNMAPPED_TABLES.csv',[r for r in tables if r['oracle_mapping_state']=='FTS_SPECIAL_OR_UNMAPPED_REVIEW_REQUIRED'])
    save_json(output/'ASSUMPTIONS.json',dict(scenarios=SCENARIOS,notes=result['notes'],contract_version=contract['version'],
              clob_encoding='utf-16-be',varchar_encoding='utf-8',heap_row_header=3,lob_locator=40,
              inline_threshold=3900,index_entry_overhead=12,out_of_row_lob_index_overhead=64))
    save_json(output/'REPORT.json',result)


def show(result, output):
    print('\n상태:',result['status'],'| 범위:',result['binding']['scan_root'])
    print('파일 논리 크기: {:,.3f} GiB / 하드링크 중복 제외 {:,.3f} GiB'.format(result['logical_file_bytes']/GIB,result['unique_inode_file_bytes']/GIB))
    print('원본 구분:',result['binding']['config']['source_mode'],'| NFS 실제 할당:',result['nfs_physical_allocated_bytes'])
    largest=sorted([r for d in result['databases'].values() for r in d.get('tables',[]) if r['table_and_index_bytes'] is not None],key=lambda r:r['table_and_index_bytes'],reverse=True)
    print('큰 테이블 상위 10개 (나머지는 SQLITE_TABLES.csv):')
    for r in largest[:10]:
        print(' ',r['file'],r['table'],round(r['table_and_index_bytes']/GIB,4),'GiB')
    print('Oracle 예상은 단일 원문·검색 세대의 A/B/C 가정입니다. 전체 운영 DB 합계가 아닙니다.')
    for row in result.get('oracle_tables',[]):
        v=row.get('B_total_bytes')
        print(row['policy'],row['target'],'B=',None if v is None else round(v/GIB,3),'GiB',
              '표본 근거 행=',row['sampled_plan_rows'],'가정 행=',row['assumed_plan_rows'])
    print('결과 폴더:',output,flush=True)


def resolve_inputs(old_job='', generation='', scan_root='', source_mode='RESTORED_COPY', scratch=''):
    import tempfile
    job=Path(old_job) if old_job else Path(scratch or tempfile.gettempdir())/'legal-existing-nfs-20261029-r1'/'financial-risk-success-20261005-schema-r2'/'oracle-import-r2'
    state=job/'full-state.json'
    if generation:
        root=Path(generation)
    elif state.exists():
        root=Path(read_json(state)['identity']['generation'])
    else:
        raise ValueError('GENERATION_NOT_FOUND: set GENERATION_DIR or OLD_JOB_DIR; no new download or newest-file guessing')
    descriptor=job/'projection-descriptor-r7.json'
    if source_mode not in ('RESTORED_COPY','NFS_MOUNT'):
        raise ValueError('SOURCE_MODE')
    return dict(generation=str(root.resolve()),scan_root=str(Path(scan_root).resolve()) if scan_root else '',
                descriptor=str(descriptor.resolve()) if descriptor.exists() else '',
                full_state=str(state.resolve()) if state.exists() else '',source_mode=source_mode)
