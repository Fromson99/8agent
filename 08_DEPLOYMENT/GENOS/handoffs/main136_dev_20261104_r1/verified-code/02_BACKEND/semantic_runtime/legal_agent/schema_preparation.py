"""Request-owned preparation for the default jsonschema.validate contract.

Only JSON schemas with local references and the default checker are cached. Key
order is significant: sorting properties can change error enumeration and the
best_match tie break. Instance and current-state checks are never cached.
"""
from collections import OrderedDict
from copy import deepcopy
import json
import math

import jsonschema
from jsonschema.exceptions import best_match
from jsonschema.validators import validator_for

from .. import query_latency as latency


def _json_tree(value):
    """Do not alias non-JSON Python schemas through JSON's coercions."""
    kind = type(value)
    if kind is dict:
        # A cached resolver must not retain an externally retrieved resource.
        if any(key in value and isinstance(value[key], str)
                and value[key] and not value[key].startswith('#')
                for key in ('$ref', '$dynamicRef', '$recursiveRef')):
            return False
        return all(type(key) is str and _json_tree(child) for key, child in value.items())
    if kind is list:
        return all(_json_tree(child) for child in value)
    if kind is float:
        return math.isfinite(value)
    return kind in (str, int, bool, type(None))


class OrderedSchemaValidators:
    """Bounded, in-memory cache owned by one investigation, never checkpointed."""

    def __init__(self, *, max_entries=32, max_bytes=4 * 1024 * 1024):
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self._entries = OrderedDict()
        self._bytes = 0

    def validate(self, instance, schema):
        with latency.span('schema.key') as timing:
            if not _json_tree(schema):
                timing['cache_bypass'] = 1
                # Preserve jsonschema's behavior for Python-only values too.
                return jsonschema.validate(instance, schema)
            serialized = json.dumps(schema, ensure_ascii=False, sort_keys=False,
                separators=(',', ':'), allow_nan=False)
            schema_bytes = len(serialized.encode())
            cls = validator_for(schema)
            key = (cls, serialized)
            timing['schema_bytes'] = schema_bytes
        with latency.span('schema.prepare') as timing:
            entry = self._entries.get(key)
            timing['cache_hit'] = int(entry is not None)
            if entry is None:
                # Invalid schemas never enter the cache. Match validate()'s
                # class selection, schema check, and constructor order.
                cls.check_schema(schema)
                validator = cls(deepcopy(schema))
                if self.max_entries > 0 and schema_bytes <= self.max_bytes:
                    while self._entries and (len(self._entries) >= self.max_entries
                            or self._bytes + schema_bytes > self.max_bytes):
                        _, (_, evicted_bytes) = self._entries.popitem(last=False)
                        self._bytes -= evicted_bytes
                    self._entries[key] = (validator, schema_bytes)
                    self._bytes += schema_bytes
            else:
                validator = entry[0]
                self._entries.move_to_end(key)
        with latency.span('schema.instance'):
            # Validator.validate() raises the first error, whereas the original
            # jsonschema.validate() selects best_match from all errors.
            errors = list(validator.iter_errors(instance))
            error = best_match(errors)
            if error is not None:
                from .output_contract import schema_issues
                error.response_contract_issues = schema_issues(errors)
                raise error


def validate(instance, schema, *, owner):
    cache = getattr(owner, '_navigation_schema_validators', None)
    if cache is None:
        cache = OrderedSchemaValidators()
        owner._navigation_schema_validators = cache
    return cache.validate(instance, schema)
