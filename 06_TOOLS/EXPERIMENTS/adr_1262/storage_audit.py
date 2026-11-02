"""Post-run, read-only namespace audit. No models, DDL or data mutations."""
from pathlib import Path
import collections
import hashlib
import importlib.util
import json
import sys

R = Path('/home/jin/8-AGENT')
A = R / '04_EXPERIMENTS/ADR/ADR-1262-main130-progress-dedup-live'
O = A / 'artifacts/run-001'
read = lambda p: json.loads(p.read_text())
C = R / read(A / 'artifacts/design/before.json')['binding']['engine_root']
sys.path[:0] = [str(C / '02_BACKEND'), str(R / '06_TOOLS/maintenance')]
from agent_record_oracle_r2 import connection
from experiment_json import write_summary
from semantic_runtime.oracle_agent_records import AgentRecords
from semantic_runtime.oracle_dp_io import canonical, digest
from semantic_runtime import oracle_progress_body as progress

binding = read(O / 'live/gold-369/record-binding.json')
namespace = binding['namespace']
scope = digest({'format': 'oracle-agent-namespace-v1', 'namespace': namespace})
assert scope == binding['scope']
parts = collections.defaultdict(dict)
rows = []
with connection() as db:
    with db.cursor() as c:
        c.execute('SELECT BODY_HASH_VAL,PART_SEQ_NO,PART_JSON_CN FROM SIDDA.LGL_AGT_BODY_A WHERE SCOPE_HASH_VAL=:s', s=scope)
        for key, seq, lob in c:
            parts[key][seq] = json.loads(lob.read() if hasattr(lob, 'read') else lob)
        c.execute("SELECT BODY_HASH_VAL,REC_REV_NO,REC_KEY_HASH_VAL FROM SIDDA.LGL_AGT_REC_A WHERE SCOPE_HASH_VAL=:s AND REC_KIND_CD='SQLROW:stage_progress' ORDER BY REC_REV_NO,REC_KEY_HASH_VAL", s=scope)
        rows = c.fetchall()
assert parts and rows, 'fresh scope must have stored progress'
resolved = {}
def restore(key, ancestors=()):
    assert key not in ancestors and len(ancestors) < 64
    if key not in resolved:
        resolved[key] = AgentRecords._decode_body(key, parts[key], lambda child: restore(child, (*ancestors, key)))
    raw = resolved[key]
    assert hashlib.sha256(raw).hexdigest() == key
    return raw

layouts = collections.Counter(p[0]['layout_version'] for p in parts.values())
for key in parts:
    restore(key)
history = [r for r in rows if r[1] > 0]
keys = set(r[0] for r in history)
large = {h for h in keys if progress.eligible(restore(h))}
roots = {h for h in keys if parts[h][0]['layout_version'] == 4}
assert large == roots and roots, 'all eligible actual progress roots must use new lossless format'
used = set(roots)
for key in roots:
    manifest, recipe = AgentRecords._stored_body(key, parts[key])
    used.update(progress.references(manifest, recipe))
actual_chars = sum(len(canonical(row)) for h in used for row in parts[h].values())
baseline_chars = 0
baseline_parts = 0
for h in roots:
    envelopes, manifest = AgentRecords._encode_body(restore(h), layout=3)
    baseline_chars += sum(len(canonical(v['json'])) for v in [*envelopes, manifest])
    baseline_parts += len(envelopes) + 1
ordered = [(h, rev, key) for h, rev, key in history]
out = {
    'scope': scope, 'namespace': namespace, 'read_only': True, 'database_writes': 0,
    'body_manifests': len(parts), 'body_parts': sum(map(len, parts.values())),
    'layout_counts': dict(layouts), 'all_stored_bodies_hash_verified': len(resolved),
    'progress_current_rows': len(rows) - len(history), 'progress_history_rows': len(history),
    'progress_unique_history_bodies': len(keys), 'large_progress_roots_v4': len(roots),
    'all_eligible_roots_v4': large == roots,
    'all_progress_history_byte_hash_verified': all(hashlib.sha256(restore(h)).hexdigest() == h for h in keys),
    'history_index_sha256': hashlib.sha256(canonical(ordered).encode()).hexdigest(),
    'progress_all_history_logical_bytes': sum(len(restore(h)) for h in keys),
    'eligible_history_logical_bytes': sum(len(restore(h)) for h in roots),
    'actual_v4_roots_and_unique_leaf_parts': sum(len(parts[h]) for h in used),
    'actual_v4_roots_and_unique_leaf_json_chars': actual_chars,
    'same_actual_roots_hypothetical_v3_parts': baseline_parts,
    'same_actual_roots_hypothetical_v3_json_chars': baseline_chars,
    'envelope_char_reduction_on_same_eligible_history': 1 - actual_chars / baseline_chars,
    'comparison_boundary': 'Same actual distinct eligible progress versions; Oracle JSON envelope characters only, not allocated segment bytes, latency or total SQL. No history deletion or old namespace migration.',
    'new_model_calls': 0,
}
write_summary(O / 'storage-audit.json', out)
print(json.dumps(out, ensure_ascii=False))
