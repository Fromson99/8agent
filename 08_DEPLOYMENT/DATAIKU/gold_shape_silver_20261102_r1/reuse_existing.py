"""Extract only side-effect-free mapping definitions from the frozen Gold importer."""
import ast
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
OLD=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1208/gold-b03/revisions/rev-021/snapshot/08_DEPLOYMENT/LOCAL/gold_connection_r12'

def definition(path,name):
    raw=path.read_text()
    for node in ast.parse(raw).body:
        if (isinstance(node,ast.FunctionDef) and node.name==name or
            isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets)):
            return ast.get_source_segment(raw,node)
    raise ValueError(name)

parts=[definition(OLD/'gold_connection.py','READ_COLUMNS'),
       definition(OLD/'gold_lab.py','mapped_source'),definition(OLD/'gold_lab.py','mapped_query')]
target=OUT/'package/legacy_gold_mapping.py'
target.write_text('"""Exact mapping definitions reused from frozen ADR1208 rev-021. No lab startup."""\n'
                  'from gold_io import canonical\n\n'+'\n\n'.join(parts)+'\n')
sources=[OLD/'gold_lab.py',OLD/'gold_connection.py',ROOT/'02_BACKEND/semantic_runtime/oracle_records_migration.py']
evidence={'mapping_reuse':'AST-extracted definitions, source text unchanged',
          'definitions':['READ_COLUMNS','mapped_source','mapped_query'],
          'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
          'agent_history_import':'Existing maintained module identified; not automatically executed without the runtime source and writer quiescence.',
          'projection_reuse':'Exact R11 source_batch/extend_chain/projected_rows/prepared descriptor and Dataiku render; unchanged vendor bytes.',
          'scope':'Entire retained field R11 source, no implicit CM21 restriction or old Gold packed-stage substitution.'}
(OUT/'package/REUSE_EVIDENCE.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'mapping_definitions_reused':3,'lab_startup_imported':False}))
