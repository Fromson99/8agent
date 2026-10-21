"""Measure prospective synthetic contracts, never private field prompts or tokens."""
from pathlib import Path
import json, sys, hashlib
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0850-minimal-output-qualification'
f=json.loads((A/'artifacts/design/freeze.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert all(sha(R/n)==h for n,h in f['files'].items()), 'frozen input drift'
S=R/f['code_root'];sys.dont_write_bytecode=True
sys.path[:0]=[str(S/'02_BACKEND'),str(R/'06_TOOLS/EXPERIMENTS/adr_0848'),str(R/'02_BACKEND')]
from semantic_runtime.legal_agent.minimal_output import Projection
from semantic_runtime.legal_agent.model_contract import genos_wire_schema
from test_minimal_output import navigation
encoded=lambda v:json.dumps(v,ensure_ascii=False,separators=(',',':')).encode()
rows=[]
for n in (1,4,12):
    old,expand,canonical=navigation(n);p=Projection(old)
    full={'next_action':'RESEARCH','targets':['T1'],'queries':['기준'],
        'reason':'규정 찾기','evidence_sufficient':False,'sufficiency_reason':'아직 미확인',
        'exploration':[{'target':'T1','issue_id':'Q1','missing_need':'규정','relation':'DIRECT'}]}
    # Prior GENOS wire already excludes optional host-owned values.
    previous={k:v for k,v in full.items() if k in genos_wire_schema(old)['properties']}
    compact=p.project(previous)
    from jsonschema import validate
    validate(compact,p.wire)
    row={'actions':n,'baseline_schema_bytes':len(encoded(genos_wire_schema(old))),
        'compact_schema_bytes':len(encoded(p.wire)),
        'baseline_response_bytes':len(encoded(previous)), 'compact_response_bytes':len(encoded(compact)),
        'same_canonical_json':expand(p.expand(compact))==expand(previous)}
    row['schema_reduction_percent']=round(100*(1-row['compact_schema_bytes']/row['baseline_schema_bytes']),2)
    rows.append(row)
out=A/'artifacts/run-001';out.mkdir(exist_ok=True)
(out/'measurements.json').write_text(json.dumps({'cases':rows,'real_model_calls':0,
    'units':'canonical UTF-8 bytes; synthetic navigation shapes, not measured tokens or field latency',
    'strict_success':all(r['same_canonical_json'] and (r['actions']==1 or r['schema_reduction_percent']>=50) for r in rows)},ensure_ascii=False,indent=2)+'\n')
print(json.dumps(rows,ensure_ascii=False))
