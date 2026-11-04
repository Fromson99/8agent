"""Read a declared, immutable generation without rebuilding or server job state.

The authenticated serving adapter fixes the root. Requests select only inventory
members; DSS owns checkpoints, received bytes and Oracle publication.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

PROTOCOL = 'existing-nfs-generation-v1'
RESTORED_FORMAT = 'oracle-existing-nfs-generation-v1'
CHUNK = 1024 * 1024
MAX_METADATA = 16 * CHUNK


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def pin(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('NFS_HASH_FORMAT')
    return value


def relative(value):
    if not isinstance(value, str):
        raise ValueError('NFS_PATH')
    p = PurePosixPath(value)
    if (not p.parts or p.is_absolute() or '..' in p.parts or str(p) != value
            or '\\' in value or '\x00' in value):
        raise ValueError('NFS_PATH')
    return value


def signature(path):
    st = path.stat()
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


class Snapshot:
    """Metadata only. Full byte hashes are verified by DSS while receiving."""
    def __init__(self, generation, code_sha256):
        self.root = Path(generation).resolve(strict=True)
        self.paths, self.signatures, self.metadata_paths, self.files = {}, {}, set(), {}
        self.code = pin(code_sha256)
        manifest, manifest_sha = self._json('manifest.json')
        if manifest.get('schema_version') not in {'term-source-generation-v1', 'term-source-generation-v2'}:
            raise ValueError('NFS_SOURCE_SCHEMA')
        self._add('store.sqlite', manifest['store_sha256'])
        nav = manifest['navigation']
        nm, _ = self._json(relative(nav['path']) + '/manifest.json', nav['manifest_sha256'])
        source_digest = digest({k: v for k, v in manifest.items()
                                if k not in {'navigation', 'fulltext', 'fulltext_derivation'}})
        if (nm['source_store_sha256'] != manifest['store_sha256']
                or nm['source_manifest_sha256'] != source_digest):
            raise ValueError('NFS_NAVIGATION_BINDING')
        self._add(nav['path'] + '/navigation.sqlite', nm['index_sha256'])
        ft = manifest.get('fulltext')
        if ft:
            fm, _ = self._json(relative(ft['path']) + '/manifest.json', ft['manifest_sha256'])
            if (fm['source_store_sha256'] != manifest['store_sha256']
                    or fm['navigation_index_sha256'] != nm['index_sha256']):
                raise ValueError('NFS_FULLTEXT_BINDING')
            if fm['schema_version'] == 'semantic-unit-fulltext-v1':
                self._add(ft['path'] + '/units.sqlite', fm['index_sha256'])
            elif fm['schema_version'] == 'semantic-fulltext-v2':
                self._add(ft['path'] + '/fulltext.sqlite', fm['fulltext_sha256'])
            else:
                raise ValueError('NFS_FULLTEXT_SCHEMA')
        glossary = manifest['glossary']
        gm, _ = self._json(relative(glossary['bundle']) + '/manifest.json', glossary['manifest_sha256'])
        self._add(glossary['dictionary'], gm['dictionary_sha256'])
        for entry in gm['files']:
            self._add(glossary['bundle'] + '/' + relative(entry['path']), entry['sha256'])
        receipt_name = glossary['cache'] + '/' + glossary['cache_receipt']
        receipt, _ = self._json(receipt_name, glossary['cache_receipt_sha256'])
        self._add(str(PurePosixPath(receipt_name).with_suffix('.sqlite')), receipt['sha256'])
        if manifest.get('vectors'):
            raise ValueError('NFS_VECTOR_CONTRACT_REQUIRED')
        # Match the maintained immutable_inputs selection contract exactly.
        selection = self.root.parent / 'SEARCH_SELECTION' / (self.root.name + '.json')
        self.selection_path = selection
        self.selection_exists = selection.exists()
        if self.selection_exists:
            self._safe_file(selection, self.root.parent)
            raw, selected = self._read_json(selection)
            if (selected['store_sha256'] != manifest['store_sha256']
                    or selected['manifest_sha256'] != manifest_sha):
                raise ValueError('NFS_SELECTION_BINDING')
            self._remember('SEARCH_SELECTION/generation.json', selection, hashlib.sha256(raw).hexdigest())
            self.metadata_paths.add('SEARCH_SELECTION/generation.json')
        value = {'protocol': PROTOCOL, 'generation': str(self.root),
                 'generation_id': manifest.get('generation_id'), 'dataset_version': manifest_sha,
                 'code_sha256': self.code, 'chunk_bytes': CHUNK,
                 'files': dict(sorted(self.files.items())), 'source_modified': False,
                 'rebuild': False, 'source_bytes_verified': False}
        if len(json.dumps(value).encode()) > 2 * CHUNK:
            raise ValueError('NFS_INVENTORY_LIMIT')
        self.info = {**value, 'snapshot_sha256': digest(value)}
        self.check()

    @staticmethod
    def _safe_file(path, base):
        path.resolve(strict=True).relative_to(base.resolve(strict=True))
        if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
            raise ValueError('NFS_FILE_TYPE')
        if path.suffix in {'.sqlite', '.db'}:
            for suffix in ('-wal', '-journal'):
                side = Path(str(path) + suffix)
                if side.exists() and side.stat().st_size:
                    raise ValueError('NFS_SOURCE_MUTABLE')

    def _remember(self, name, path, sha):
        pin(sha)
        self._safe_file(path, self.root if name.startswith('generation/') else self.root.parent)
        sig = signature(path)
        item = {'bytes': sig[2], 'sha256': sha}
        if name in self.files and self.files[name] != item:
            raise ValueError('NFS_DUPLICATE_FILE_CONFLICT')
        self.paths[name], self.signatures[name], self.files[name] = path, sig, item

    def _add(self, name, sha):
        name = relative(name)
        self._remember('generation/' + name, self.root / name, sha)

    @staticmethod
    def _read_json(path):
        before = signature(path)
        with path.open('rb') as stream:
            raw = stream.read(MAX_METADATA + 1)
        if signature(path) != before:
            raise ValueError('NFS_SOURCE_CHANGED')
        if len(raw) > MAX_METADATA:
            raise ValueError('NFS_METADATA_LIMIT')
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError('NFS_METADATA_OBJECT')
        return raw, value

    def _json(self, name, expected=None):
        name = relative(name)
        path = self.root / name
        self._safe_file(path, self.root)
        before = signature(path)
        raw, value = self._read_json(path)
        sha = hashlib.sha256(raw).hexdigest()
        if expected is not None and pin(expected) != sha:
            raise ValueError('NFS_METADATA_HASH')
        self._add(name, sha)
        if self.signatures['generation/' + name] != before:
            raise ValueError('NFS_SOURCE_CHANGED')
        self.metadata_paths.add('generation/' + name)
        return value, sha

    def check(self, name=None):
        if self.selection_path.exists() != self.selection_exists:
            raise ValueError('NFS_SOURCE_CHANGED')
        selected = self.metadata_paths | ({name} if name else set(self.paths))
        for key in selected:
            path = self.paths[key]
            self._safe_file(path, self.root if key.startswith('generation/') else self.root.parent)
            if signature(path) != self.signatures[key]:
                raise ValueError('NFS_SOURCE_CHANGED')

    def read(self, snapshot_sha256, name, offset):
        if snapshot_sha256 != self.info['snapshot_sha256']:
            raise ValueError('NFS_SNAPSHOT_CHANGED')
        if not isinstance(name, str) or name not in self.paths:
            raise ValueError('NFS_UNDECLARED_FILE')
        size = self.files[name]['bytes']
        if type(offset) is not int or not 0 <= offset <= size:
            raise ValueError('NFS_READ_RANGE')
        self.check(name)
        with self.paths[name].open('rb') as stream:
            stream.seek(offset)
            block = stream.read(min(CHUNK, size - offset))
        self.check(name)
        return {'snapshot_sha256': snapshot_sha256, 'file': name, 'offset': offset,
                'total_bytes': size, 'bytes': len(block),
                'sha256': hashlib.sha256(block).hexdigest(),
                'content': base64.b64encode(block).decode()}


def validate_info(info, *, code_sha256, generation):
    if (info.get('protocol') != PROTOCOL or info.get('code_sha256') != code_sha256
            or info.get('generation') != generation or info.get('chunk_bytes') != CHUNK
            or info.get('source_modified') is not False or info.get('rebuild') is not False):
        raise ValueError('NFS_SERVICE_BINDING')
    pin(info['dataset_version'])
    if pin(info['snapshot_sha256']) != digest({k: v for k, v in info.items() if k != 'snapshot_sha256'}):
        raise ValueError('NFS_INVENTORY_HASH')
    files = info.get('files')
    if not isinstance(files, dict) or not {'generation/manifest.json', 'generation/store.sqlite'} <= files.keys():
        raise ValueError('NFS_FILE_LIST')
    for name, item in files.items():
        relative(name)
        if not (name.startswith('generation/') or name == 'SEARCH_SELECTION/generation.json'):
            raise ValueError('NFS_FILE_SCOPE')
        if type(item['bytes']) is not int or item['bytes'] < 0:
            raise ValueError('NFS_FILE_SIZE')
        pin(item['sha256'])
    if files['generation/manifest.json']['sha256'] != info['dataset_version']:
        raise ValueError('NFS_MANIFEST_BINDING')
    return info


def finish_received(folder, info):
    """Run the maintained full inventory only after complete byte verification."""
    from . import oracle_full_package as full
    root, _, actual = full.inventory(Path(folder) / 'generation')
    if actual['files'] != info['files'] or actual['dataset_version'] != info['dataset_version']:
        raise ValueError('NFS_RECEIVED_BINDING')
    result = {**actual, 'format': RESTORED_FORMAT,
              'nfs_snapshot': info, 'snapshot_sha256': info['snapshot_sha256']}
    from semantic_runtime.oracle_dp_io import atomic_json
    atomic_json(Path(folder) / 'full-manifest.json', result)
    full.verify_restored(folder)
    return result
