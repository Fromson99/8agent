"""Separate asserted field citations from preserved unreviewed originals."""
from pathlib import Path
import json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0933-packet-update-threaded-validation'
for p in sorted((A/'artifacts/run-001/fixed').glob('*/audit.json')):
    a=json.loads(p.read_text());by={e['evidence_id']:e for child in a['children'].values() for e in child['all_read_evidence']}
    fields={}
    for item in a['field_rows']:
        for side in ('internal','external'):
            row=item[side];refs=row['citations']+row.get('dependencies',[])
            for old in row.get('alternatives',[]):refs+=old['citations']+old.get('dependencies',[])
            fields[item['issue_id']+':'+item['field']+':'+side]=sorted({r['evidence'] for r in refs})
    cited={i for values in fields.values() for i in values};unreviewed={r['evidence_id'] for r in a['unreviewed_sources']}
    result={'field_cited_ids':sorted(cited),'preserved_unreviewed_ids':sorted(unreviewed),'field_links':fields,
        'field_cited_roots':list({json.dumps(by[i]['canonical'],sort_keys=True):by[i]['canonical'] for i in cited if i in by and by[i].get('canonical')}.values()),
        'unmapped_field_citations':sorted(cited-set(by)),
        'field_source_labels':[{'id':i,'document_name':by[i]['metadata']['document_name'],'heading':by[i]['metadata'].get('heading','')} for i in sorted(cited&set(by))],
        'meaning':'Field selection and exact source preservation are separate; neither certifies legal correctness.'}
    (p.parent/'claim-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(p.parent.name,'field_selected',len(cited),'preserved_unreviewed',len(unreviewed))
