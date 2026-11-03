from common import *
S=ROOT/read(DES/'candidate-path.json')['snapshot']
p=S/'02_BACKEND/semantic_runtime/ontology_work/mapped_authoring.py';s=p.read_text().replace('found = found or bool(rows)',"prefix = 'cb-kb-ws-' + scope_key(scope) + '-'\n            found = found or any(row['context']['snapshot']['bundles'][0]['bundle_id'].startswith(prefix) for row in rows)");p.write_text(s)
p=S/'02_BACKEND/semantic_runtime/legal_agent/scenario_computation.py';s=p.read_text();a=s.index('PROMPT =');print(s[a:a+550])
