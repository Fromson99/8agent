"""Separate asserted field citations from preserved unreviewed originals."""
from pathlib import Path
import json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0936-durable-research-review-patch'
for p in sorted((A/'artifacts/run-001/fixed').glob('*/audit.json')):
    a=json.loads(p.read_text());by={e['evidence_id']:e for child in a['children'].values() for e in child['all_read_evidence']}
    fields={};current_fields={};prior_fields={}
    for item in a['field_rows']:
        for side in ('internal','external'):
            row=item[side];refs=row['citations']+row.get('dependencies',[])
            key=item['issue_id']+':'+item['field']+':'+side
            current_fields[key]=sorted({r['evidence'] for r in refs})
            prior_fields[key]=sorted({r['evidence'] for old in row.get('alternatives',[]) for r in old['citations']+old.get('dependencies',[])})
            for old in row.get('alternatives',[]):refs+=old['citations']+old.get('dependencies',[])
            fields[item['issue_id']+':'+item['field']+':'+side]=sorted({r['evidence'] for r in refs})
    cited={i for values in fields.values() for i in values};unreviewed={r['evidence_id'] for r in a['unreviewed_sources']}
    result={'field_cited_ids':sorted(cited),'preserved_unreviewed_ids':sorted(unreviewed),'field_links':fields,
        'current_field_links':current_fields,'prior_field_links':prior_fields,
        'current_field_cited_ids':sorted({i for values in current_fields.values() for i in values}),
        'retained_prior_cited_ids':sorted({i for values in prior_fields.values() for i in values}),
        'field_cited_roots':list({json.dumps(by[i]['canonical'],sort_keys=True):by[i]['canonical'] for i in cited if i in by and by[i].get('canonical')}.values()),
        'unmapped_field_citations':sorted(cited-set(by)),
        'field_source_labels':[{'id':i,'document_name':by[i]['metadata']['document_name'],'heading':by[i]['metadata'].get('heading','')} for i in sorted(cited&set(by))],
        'meaning':'field_cited_ids includes current judgments and retained prior alternatives; current_field_cited_ids isolates the current selection. Unreviewed originals are separately preserved. None certifies legal correctness.'}
    (p.parent/'claim-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(p.parent.name,'field_selected',len(cited),'preserved_unreviewed',len(unreviewed))
