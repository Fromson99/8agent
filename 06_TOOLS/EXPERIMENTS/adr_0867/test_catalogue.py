from pathlib import Path
import json,hashlib,os
from jsonschema import Draft202012Validator as V
from semantic_runtime.legal_agent.minimal_output import Projection
from semantic_runtime.legal_agent.local_gemma import provider_request
import semantic_runtime
R=Path(__file__).resolve().parents[3]
C=Path(semantic_runtime.__file__).resolve().parents[2]

def test_all_selected_static_generation_schema_nodes():
    rows=[]
    def walk(node,p,path):
        if isinstance(node,dict):
            if node.get('type')=='object' and isinstance(node.get('properties'),dict) and ('$schema' in node or 'additionalProperties' in node or 'required' in node):
                V.check_schema(node);projection=Projection(node);V.check_schema(projection.wire)
                actual=provider_request({'response_format':{'type':'json_schema','json_schema':{'name':'audit','schema':projection.wire}}})
                V.check_schema(actual['response_format']['json_schema']['schema'])
                rows.append({'path':str(p.relative_to(C)),'json_pointer':path,**projection.receipt})
            for k,v in node.items():
                if k not in ('const','enum','default'):walk(v,p,path+'/'+k)
        elif isinstance(node,list):
            for i,v in enumerate(node):walk(v,p,path+'/'+str(i))
    for folder in ('00_SYSTEM/SCHEMAS','02_BACKEND/ENGINES','02_BACKEND/WORKFLOWS'):
        for p in sorted((C/folder).rglob('*.json')):walk(json.loads(p.read_text()),p,'')
    assert len(rows)>50
    mode='working' if C==R else 'candidate'
    out=R/'04_EXPERIMENTS/ADR/ADR-0867-derived-target-host-contract/artifacts'/f'{mode}-schema-catalogue.json'
    out.write_text(json.dumps({'code_root':str(C),'schema_nodes':len(rows),'rows':rows,'limitations':'Static syntax and generation projection audit; dynamic and model acceptance checked separately.'},ensure_ascii=False,indent=2)+'\n')
