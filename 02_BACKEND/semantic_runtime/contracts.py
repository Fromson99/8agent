import hashlib
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


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
        self.registry = Registry()
        paths = {}
        paths.update({c['schema_path']: c['schema_sha256'] for c in self.pipeline['contracts'].values() if 'schema_path' in c})
        for path, expected in paths.items():
            if sha(self.root/path) != expected:
                raise ValueError('schema hash mismatch: '+path)
            schema = json.loads((self.root/path).read_text())
            schema_id=schema.get('$id','urn:8-agent:file:'+Path(path).stem)
            self.schemas[schema_id] = schema
            self.registry = self.registry.with_resource(schema_id, Resource.from_contents(schema,default_specification=DRAFT202012))

    def validate(self, value, schema_id, definition=None):
        schema = self.schemas[schema_id]
        if definition:
            schema = {'$ref': schema_id+'#/$defs/'+definition}
        Draft202012Validator(schema, registry=self.registry, format_checker=FormatChecker()).validate(value)
        return value

