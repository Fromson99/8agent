"""Lossless content-defined sharing for large structured progress SQL rows.

Logical bytes/hashes never change. Leaves use the existing BODY codec, share
only inside the Agent namespace, and are durable before the referring recipe.
There is no previous-revision dependency, deletion, NFS IO or lossy projection.
"""
from __future__ import annotations
import hashlib
import json
import re
from .oracle_dp_io import DPError, canonical

MIN_BODY = 64 * 1024
MIN_CHUNK = 4 * 1024
MAX_CHUNK = 32 * 1024
MASK = (1 << 14) - 1
MAX_BYTES = 256 * 1024 * 1024
MAX_REFS = 16384
GEAR = tuple(int.from_bytes(hashlib.sha256(bytes([i])).digest()[:8], 'big') for i in range(256))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def eligible(raw):
    if len(raw) < MIN_BODY: return False
    try: value = json.loads(raw)
    except (ValueError, UnicodeError): return False
    return (isinstance(value, dict) and value.get('table') == 'stage_progress'
            and isinstance(value.get('columns'), list) and 'payload' in value['columns']
            and isinstance(value.get('values'), list))


def split(raw):
    start = 0; length = len(raw)
    while start < length:
        pos = min(start + MIN_CHUNK, length); stop = min(start + MAX_CHUNK, length); code = 0
        while pos < stop:
            code = ((code << 1) + GEAR[raw[pos]]) & ((1 << 64) - 1); pos += 1
            if code & MASK == 0: break
        yield raw[start:pos]; start = pos


def plan(values):
    """Return raw bodies plus bounded leaf bodies and root recipes, by hash."""
    bodies = dict(values); recipes = {}
    for key, raw in values.items():
        if not eligible(raw): continue
        if len(raw) > MAX_BYTES: raise DPError('AGENT_PROGRESS_SIZE: bounded checkpoint required')
        leaves = list(split(raw))
        refs = [sha(v) for v in leaves]
        if len(refs) < 2: continue
        if key in refs or len(refs) > MAX_REFS: raise DPError('AGENT_PROGRESS_REFS: invalid checkpoint graph')
        recipes[key] = canonical(refs).encode()
        for child, value in zip(refs, leaves): bodies.setdefault(child, value)
    return bodies, recipes


def references(manifest, recipe):
    if (type(manifest.get('total_bytes')) is not int or not MIN_BODY <= manifest['total_bytes'] <= MAX_BYTES
            or type(manifest.get('recipe_bytes')) is not int
            or not 0 < manifest['recipe_bytes'] <= MAX_REFS * 68 + 2
            or len(recipe) != manifest['recipe_bytes'] or sha(recipe) != manifest.get('recipe_sha256')):
        raise DPError('AGENT_PROGRESS_HASH: invalid checkpoint recipe')
    try: refs = json.loads(recipe)
    except (ValueError, UnicodeError) as exc: raise DPError('AGENT_PROGRESS_REFS: malformed checkpoint recipe') from exc
    if (not isinstance(refs, list) or not 2 <= len(refs) <= MAX_REFS
            or any(not isinstance(h, str) or not re.fullmatch('[0-9a-f]{64}', h) for h in refs)):
        raise DPError('AGENT_PROGRESS_REFS: bounded content references required')
    return refs


def restore(key, manifest, recipe, resolve):
    if resolve is None: raise DPError('AGENT_PROGRESS_MISSING: checkpoint leaves require a namespace resolver')
    raw = bytearray()
    for ref in references(manifest, recipe):
        value = resolve(ref)
        if not isinstance(value, bytes) or not 0 < len(value) <= MAX_CHUNK:
            raise DPError('AGENT_PROGRESS_SIZE: invalid checkpoint leaf')
        if len(raw) + len(value) > manifest['total_bytes']:
            raise DPError('AGENT_PROGRESS_SIZE: checkpoint exceeds declared size')
        raw.extend(value)
    if len(raw) != manifest['total_bytes'] or sha(raw) != key:
        raise DPError('AGENT_PROGRESS_HASH: restored original bytes differ')
    return bytes(raw)
