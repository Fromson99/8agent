"""Require actual transmitted package and a committed, source-bound claim for reuse credit."""
from common import *
import collections
import sqlite3

pub=read(ART/'publication-verified.json')
evidence=read(ART/'source-wire-audit.json')
rows=[]
for cell in evidence['cells']:
    d=ART/'usage-live'/(cell['case_id']+'-'+cell['arm'])
    r=read(d/'turn-1/result.json')
    body=read(d/'turn-1/response.json.gz')['body']
    term=body.get('assembly',{}).get('term_agent',{})
    if not isinstance(term,dict): term={}
    report=term.get('review_explanation') or {}
    ontology=report.get('ontology') or {}
    claims=(body.get('answer') or {}).get('claims',[])
    offered={}
    matching_inputs=0
    for b in cell['wire_ontology_inputs']:
        catalog=b.get('payload',{}).get('assembly_catalog',{})
        if catalog and catalog.get('package_sha256')==pub['package_sha256'] and catalog.get('bundle_id')==pub['bundle_id']:
            assert any((c.get('payload',{}).get('assembly_catalog') or {}).get('revision')==pub['revision'] for f in (d/'canonical').glob('???.json.gz') for c in read(f)['view'].get('ontology_bundles',[]))
            matching_inputs+=1
            for path in catalog.get('paths',[]):offered[path['id']]=path
    accepted=[b for b in ontology.get('bundles',[]) if b['bundle_id']==pub['bundle_id'] and b.get('adoption')=='ADOPTED']
    uses=[item for b in accepted for item in b['claim_uses']]
    # Final report plus the accepted proposal in the current request, not a rejected earlier attempt.
    finals=[]
    for path in sorted((d/'canonical').glob('*-output.json.gz')):
        v=read(path)
        if isinstance(v,dict) and 'claims' in v:
            finals.append(v)
    checked=[]
    if uses:
        assert matching_inputs and claims and finals
        assert all(u in finals[-1].get('ontology_usage',[]) for u in uses)
        for u in uses:
            assert u['package_sha256']==pub['package_sha256']
            p=offered[u['path_id']]
            claim=next(c for c in finals[-1]['claims'] if c['claim_id']==u['claim_id'])
            assert u['node_ids'] and set(u['node_ids'])<={n['id'] for n in p['nodes']}
            assert set(p['source_refs'])<=set(claim['evidence_refs'])
            checked.append({'claim_id':u['claim_id'],'path_id':u['path_id'],'node_ids':u['node_ids'],'source_refs':p['source_refs']})
    refs=ontology.get('workspace_publications',[])
    if uses:assert any(v['publication_id']==pub['publication_id'] for v in refs)
    rows.append({'case_id':cell['case_id'],'arm':cell['arm'],'accepted':term.get('accepted_outcome',{}),'claims':len(claims),
                 'answer':(d/'turn-1/answer.txt').read_text(),'matching_inputs':matching_inputs,'delivered_paths':list(offered),
                 'adoption_statuses':[b.get('adoption') for b in ontology.get('bundles',[])],'verified_claim_uses':checked,
                 'active_publication_refs':refs,'physical_calls':r['physical_calls'],'unknown':r['unknown'],
                 'request_seconds':r['request_seconds'],'duplicate_extra':(r.get('duplicate') or {}).get('extra_model_calls'),
                 'reported_cost_usd':cell['reported_cost_usd'],'reported_tokens':cell['reported_tokens'],
                 'source_checks':cell['source_checks'],'delivered_checks':cell['delivered_checks'],'budget_matches':cell['budget_matches'],
                 'mismatches':sum(len(cell[k]) for k in ('source_mismatches','acl_violations','wire_mismatches'))})
put(ART/'usage-inspection.json',{'rows':rows})
for r in rows:
    print(r['arm'],r['claims'],r['matching_inputs'],len(r['verified_claim_uses']),round(r['request_seconds'],2),r['answer'][:350])
