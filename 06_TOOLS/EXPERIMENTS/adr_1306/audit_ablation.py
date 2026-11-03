"""Post-run verification of what was actually removed from ASSESS wire input."""
from common import *

rows=[]
for folder in sorted((ART/'live').iterdir()):
    if not (folder/'calls.json').exists():
        continue
    calls=read(folder/'calls.json')
    stages=[]
    for i,call in enumerate(calls,1):
        if call['stage'] not in ('memory-assess','memory-assess-repair'):
            continue
        canon=read(folder/'canonical'/f'{i:03}.json.gz')
        wire=read(folder/'raw'/f'call-{i:03}'/'request.json.gz')
        schema=wire['response_format']['json_schema']['schema']
        view=canon['view']
        stages.append({'call':i,'stage':call['stage'],
            'judgment_review_absent': 'read_judgment_review' not in schema['properties'],
            'judgment_context_absent': 'read_judgments' not in view,
            'requirement_review_present': 'requirement_review' in schema['properties'],
            'evidence_options':len(view['evidence_options']),
            'claims_required': 'claims' in canon['schema']['required'],
            'wire_sha256':sha(folder/'raw'/f'call-{i:03}'/'request.json.gz'),
            'canonical_sha256':sha(folder/'canonical'/f'{i:03}.json.gz')})
    resources=read(folder/'resource-final.json') if (folder/'resource-final.json').exists() else {}
    rows.append({'cell':folder.name,'assessment_calls':stages,
        'oracle_absent':resources.get('oracle_driver_loaded') is False,
        'candidate_unchanged':resources.get('frozen_candidate_unchanged') is True,
        'passed':bool(stages) and all(s['judgment_review_absent'] and s['judgment_context_absent'] and s['requirement_review_present'] and s['evidence_options'] and s['claims_required'] for s in stages)})
result={'rows':rows,'passed':len(rows)==2 and all(r['passed'] and r['oracle_absent'] and r['candidate_unchanged'] for r in rows),
        'scope':'Final read_judgment_review contract only. Navigation review and core source checks remain in unchanged modules. Requirement review remains.',
        'new_model_calls':0}
put(ART/'ablation-wire-audit.json',result)
print(json.dumps(result,ensure_ascii=False))
