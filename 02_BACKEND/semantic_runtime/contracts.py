import hashlib
import json
import threading
from .oracle_runtime_paths import Path
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

_CODE_HASH_CACHE = {}
_CODE_HASH_LOCK = threading.Lock()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def cached_code_sha(path):
    """Reuse code proofs within a worker; explicit release gates still use sha."""
    path = Path(path).resolve()
    def signature():
        state = path.stat()
        return (state.st_dev, state.st_ino, state.st_size,
                state.st_mtime_ns, state.st_ctime_ns)
    with _CODE_HASH_LOCK:
        before = signature()
        cached = _CODE_HASH_CACHE.get(path)
        if cached is not None and cached[0] == before:
            return cached[1]
        value = sha(path)
        if signature() != before:
            raise ValueError('engine code changed during verification')
        if len(_CODE_HASH_CACHE) >= 1024:
            _CODE_HASH_CACHE.clear()
        _CODE_HASH_CACHE[path] = (before, value)
        return value


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


class Contracts:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.pipeline = json.loads((self.root/'00_SYSTEM/PIPELINE.json').read_text())
        self.schemas = {}
        self._validators = {}
        self._engine_manifests = {}
        self.registry = Registry()
        paths = {}
        self.schema_id_by_path = {}
        for c in self.pipeline['contracts'].values():
            path, expected = c['schema_path'], c['schema_sha256']
            if path in paths and paths[path] != expected:
                raise ValueError('conflicting hashes for schema path: '+path)
            paths[path] = expected
        for path, expected in paths.items():
            if sha(self.root/path) != expected:
                raise ValueError('schema hash mismatch: '+path)
            schema = json.loads((self.root/path).read_text())
            schema_id=schema.get('$id','urn:8-agent:file:'+Path(path).stem)
            if schema_id in self.schemas and self.schemas[schema_id] != schema:
                raise ValueError('conflicting schema $id: '+schema_id)
            self.schema_id_by_path[path] = schema_id
            self.schemas[schema_id] = schema
            self.registry = self.registry.with_resource(schema_id, Resource.from_contents(schema,default_specification=DRAFT202012))

        for c in self.pipeline['contracts'].values():
            definition = c.get('schema_definition')
            schema = self.schemas[self.schema_id_by_path[c['schema_path']]]
            if definition and definition not in schema.get('$defs', {}):
                raise ValueError('missing contract schema definition: '+definition)

    def validate_port(self, contract_id, value):
        contract = self.pipeline['contracts'][contract_id]
        return self.validate(value, self.schema_id_by_path[contract['schema_path']],
                             contract.get('schema_definition'))

    def validate(self, value, schema_id, definition=None):
        key = (schema_id, definition)
        validator = self._validators.get(key)
        if validator is None:
            schema = self.schemas[schema_id]
            if definition:
                schema = {'$ref': schema_id+'#/$defs/'+definition}
            validator = Draft202012Validator(schema, registry=self.registry,
                                            format_checker=FormatChecker())
            self._validators[key] = validator
        validator.validate(value)
        return value
