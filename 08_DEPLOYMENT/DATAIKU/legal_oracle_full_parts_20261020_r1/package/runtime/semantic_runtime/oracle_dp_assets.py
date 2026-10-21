"""Immutable Oracle serving-asset parts and release records (source rows are separate)."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import zlib

from .oracle_dp_io import DPError, canonical, digest, file_sha, identifier

PART_BYTES = 1024 * 1024
PART_TABLE = 'SIDDA.LEGAL_RAG_ASSET_PART_A'
RELEASE_TABLE = 'SIDDA.LEGAL_RAG_RELEASE_A'
SCHEMA = 'oracle-rag-release-v1'


def safe_relative(name):
    if not isinstance(name, str) or '\\' in name:
        raise DPError('ASSET_PATH: invalid path')
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(p in ('..', '.') for p in path.parts):
        raise DPError('ASSET_PATH: relative generation path required')
    return str(path)


def checked_path(root, name):
    name = safe_relative(name)
    path = Path(root)/name
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise DPError('ASSET_PATH: symlinks are not serving assets')
    path.resolve().relative_to(Path(root).resolve())
    return path


def json_file(path):
    if Path(path).stat().st_size > 16*1024*1024:
        raise DPError('MANIFEST_SIZE: unexpected manifest size')
    return json.loads(Path(path).read_text())


def inventory(generation):
    """Select declared serving dependencies; exclude build audit, RAW and SQLite duplicate."""
    root = Path(generation).resolve()
    manifest = json_file(root/'manifest.json')
    selected = {}
    def add(name, expected=None):
        path = checked_path(root, name)
        if not path.is_file(): raise DPError('ASSET_MISSING: '+name)
        actual = file_sha(path)
        if expected and actual != expected: raise DPError('ASSET_HASH: '+name)
        selected[name] = {'path': name, 'sha256': actual, 'bytes': path.stat().st_size,
                          'parts': (path.stat().st_size + PART_BYTES - 1)//PART_BYTES}
        return path
    nav = manifest.get('navigation') or {}
    nm = json_file(add(nav['path']+'/manifest.json', nav['manifest_sha256']))
    add(nav['path']+'/navigation.sqlite', nm['index_sha256'])
    original_source_digest = digest({k:v for k,v in manifest.items() if k not in {'navigation','fulltext','fulltext_derivation'}})
    if nm['source_store_sha256'] != manifest['store_sha256'] or nm['source_manifest_sha256'] != original_source_digest:
        raise DPError('NAVIGATION_BINDING: index belongs to a different source')
    ft = manifest.get('fulltext')
    if ft:
        fm = json_file(add(ft['path']+'/manifest.json', ft['manifest_sha256']))
        if fm['source_store_sha256'] != manifest['store_sha256'] or fm['navigation_index_sha256'] != nm['index_sha256']:
            raise DPError('FULLTEXT_BINDING: source/navigation differs')
        if fm['schema_version']=='semantic-unit-fulltext-v1':
            add(ft['path']+'/units.sqlite', fm['index_sha256'])
        elif fm['schema_version']=='semantic-fulltext-v2':
            add(ft['path']+'/fulltext.sqlite', fm['fulltext_sha256'])
        else: raise DPError('FULLTEXT_SCHEMA: unsupported explicit asset format')
    glossary = manifest.get('glossary') or {}
    gm = json_file(add(glossary['bundle']+'/manifest.json', glossary['manifest_sha256']))
    add(glossary['dictionary'], gm['dictionary_sha256'])
    for entry in gm['files']:
        add(glossary['bundle']+'/'+safe_relative(entry['path']), entry['sha256'])
    receipt_name = glossary['cache']+'/'+glossary['cache_receipt']
    receipt = json_file(add(receipt_name, glossary['cache_receipt_sha256']))
    add(str(PurePosixPath(receipt_name).with_suffix('.sqlite')), receipt['sha256'])
    if manifest.get('vectors'):
        raise DPError('VECTOR_ASSETS: this migration needs an explicit vector asset contract; do not omit vectors silently')
    return manifest, [selected[n] for n in sorted(selected)]


def clob_text(sql, table, column, where, binds, *, max_chars=16*1024*1024):
    """Fetch a complete CLOB; bounded ASCII chunk fallback for ORDS size limits."""
    identifier(column)
    result=sql.query(f'SELECT TO_CLOB({column}) AS VALUE, DBMS_LOB.GETLENGTH({column}) AS N FROM {table} WHERE {where}', binds, limit=1)
    if not result: return None
    value=result[0]['VALUE']; n=result[0]['N']
    if n is None: return None
    n=int(n)
    if n<0 or n>max_chars: raise DPError('CLOB_SIZE: declared asset metadata exceeds bound')
    # Some Oracle clients expose IS JSON CLOB columns as decoded objects.
    # Only a complete string proves byte/character preservation; otherwise use
    # the same bounded VARCHAR chunk fallback as a truncated ORDS response.
    if isinstance(value,str) and len(value.encode('utf-16-le'))//2==n:
        return value
    # Used for base64 and canonical release JSON (ensure_ascii=True at publication).
    chunks=[]; offset=1
    while offset<=n:
        parts=min(100,(n-offset+3000)//3000)
        statement=(f'SELECT q.I, DBMS_LOB.SUBSTR(t.{column},3000,:lob_start+(q.I-1)*3000) AS VALUE '
                   f'FROM {table} t CROSS JOIN (SELECT LEVEL AS I FROM DUAL CONNECT BY LEVEL<=:lob_parts) q '
                   f'WHERE {where} ORDER BY q.I')
        rows=sql.query(statement,[*binds,('lob_start',offset,'NUMBER'),('lob_parts',parts,'NUMBER')],limit=parts)
        if len(rows)!=parts or [r['I'] for r in rows]!=list(range(1,parts+1)):
            raise DPError('CLOB_PARTIAL: missing CLOB pieces')
        for r in rows:
            piece=r['VALUE']
            if not isinstance(piece,str) or not piece.isascii() or not piece:
                raise DPError('CLOB_PARTIAL: invalid ASCII asset piece')
            chunks.append(piece);offset+=len(piece)
    value=''.join(chunks)
    if len(value)!=n:raise DPError('CLOB_PARTIAL: reconstructed length differs')
    return value


def get_part(sql, asset, number):
    binds=[('a',asset,'VARCHAR2'),('p',number,'NUMBER')]
    where='ASSET_SHA256=:a AND PART_NO=:p'
    rows=sql.query(f'SELECT RAW_BYTES,PART_SHA256 FROM {PART_TABLE} WHERE {where}',binds,limit=1)
    if not rows:return None
    text=clob_text(sql,PART_TABLE,'DATA_B64',where,binds,max_chars=2*PART_BYTES)
    if text is None:raise DPError('ASSET_NULL: asset payload missing')
    try:
        compressed=base64.b64decode(text,validate=True)
        decoder=zlib.decompressobj()
        raw=decoder.decompress(compressed,PART_BYTES+1)
        if len(raw)>PART_BYTES or decoder.unconsumed_tail or not decoder.eof or decoder.unused_data:
            raise ValueError('compression bounds')
    except (ValueError,zlib.error):raise DPError('ASSET_ENCODING: invalid/oversized compressed part') from None
    if len(raw)!=rows[0]['RAW_BYTES'] or hashlib.sha256(raw).hexdigest()!=rows[0]['PART_SHA256']:
        raise DPError('ASSET_HASH: part bytes differ')
    return raw


def put_part(sql, asset, number, raw):
    previous=get_part(sql,asset,number)
    if previous is not None:
        if previous!=raw:raise DPError('ASSET_CONFLICT: immutable part differs')
        return
    encoded=base64.b64encode(zlib.compress(raw,6)).decode()
    sha=hashlib.sha256(raw).hexdigest()
    binds=[('a',asset,'VARCHAR2'),('p',number,'NUMBER'),('n',len(raw),'NUMBER'),('s',sha,'VARCHAR2'),('body',encoded,'CLOB')]
    # Concurrent identical insertion may raise a PK error; explicit resume reads/verifies it.
    statement=(f'DECLARE n NUMBER; BEGIN INSERT INTO {PART_TABLE} '
        '(ASSET_SHA256,PART_NO,RAW_BYTES,PART_SHA256,DATA_B64) VALUES (:a,:p,:n,:s,:body); '
        f'SELECT COUNT(*) INTO n FROM {PART_TABLE} WHERE ASSET_SHA256=:a AND PART_NO=:p '
        'AND RAW_BYTES=:n AND PART_SHA256=:s AND DBMS_LOB.COMPARE(DATA_B64,:body)=0; '
        "IF n<>1 THEN RAISE_APPLICATION_ERROR(-20002,'DP_ASSET_VERIFY'); END IF; "
        'COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
    sql.request(statement,binds,write=True)
    if get_part(sql,asset,number)!=raw:raise DPError('ASSET_READBACK: stored part differs')


def get_release(sql, release_id):
    if not isinstance(release_id,str) or len(release_id)!=64 or any(c not in '0123456789abcdef' for c in release_id):
        raise DPError('RELEASE_ID: explicit SHA-256 release ID required')
    text=clob_text(sql,RELEASE_TABLE,'RELEASE_JSON','RELEASE_ID=:r',[('r',release_id,'VARCHAR2')])
    if text is None:raise DPError('RELEASE_MISSING: selected complete release is unavailable')
    value=json.loads(text)
    if digest(value)!=release_id or value.get('schema_version')!=SCHEMA or value.get('status')!='COMPLETE':
        raise DPError('RELEASE_HASH: incomplete or altered release')
    return value


def put_release(sql, value):
    release_id=digest(value)
    existing=sql.query(f'SELECT RELEASE_ID FROM {RELEASE_TABLE} WHERE RELEASE_ID=:r',[('r',release_id,'VARCHAR2')],limit=1)
    if existing:
        if get_release(sql,release_id)!=value:raise DPError('RELEASE_CONFLICT: immutable release differs')
        return release_id
    text=json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':'),allow_nan=False)
    binds=[('r',release_id,'VARCHAR2'),('v',value['dataset_version'],'VARCHAR2'),('body',text,'CLOB')]
    statement=(f'DECLARE n NUMBER; BEGIN INSERT INTO {RELEASE_TABLE} '
        '(RELEASE_ID,DATASET_VERSION,RELEASE_JSON) VALUES (:r,:v,:body); '
        f'SELECT COUNT(*) INTO n FROM {RELEASE_TABLE} WHERE RELEASE_ID=:r AND DATASET_VERSION=:v '
        'AND DBMS_LOB.COMPARE(RELEASE_JSON,:body)=0; '
        "IF n<>1 THEN RAISE_APPLICATION_ERROR(-20003,'DP_RELEASE_VERIFY'); END IF; "
        'COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
    sql.request(statement,binds,write=True)
    if get_release(sql,release_id)!=value:raise DPError('RELEASE_READBACK: complete record differs')
    return release_id
