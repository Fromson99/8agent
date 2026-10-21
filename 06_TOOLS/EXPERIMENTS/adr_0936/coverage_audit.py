"""Offline source identity/label comparison; never imported by the product."""
from pathlib import Path
import json,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0936-durable-research-review-patch';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
G=R/read(D/'baseline.json')['manifest']['data_path']
db=sqlite3.connect('file:'+str(G/'navigation/navigation.sqlite')+'?mode=ro',uri=True)
def labels(a):
    stages={k:{} for k in ('acquired','returned','cited')}
    returned={i for c in a['children'].values() for i in c['returned_evidence_ids']};cited=set(a['evidence_refs'])
    for side,c in a['children'].items():
        acquired=set(c['read_evidence_ids'])
        for e in c['all_read_evidence']:
            raw=db.execute('SELECT json FROM source WHERE id=?',(e['source_id'],)).fetchone()
            if not raw:continue
            s=json.loads(raw[0]);key=s['document_id']+':'+str(s.get('unit_id'))
            v={k:s.get(k) for k in ('id','document_id','unit_id','document_name','heading')};v['side']=side
            for stage,ids in (('acquired',acquired),('returned',returned),('cited',cited)):
                if e['evidence_id'] in ids:stages[stage][key]=v
    return stages
out={}
for c in read(D/'cases.json'):
    ident=c['id'];p=A/'artifacts/run-001/fixed'/ident
    if not (p/'audit.json').exists():continue
    base=labels(read(A/'artifacts/run-001/baseline'/ident/'audit.json'));new=labels(read(p/'audit.json'))
    out[ident]={'baseline':base,'fixed':new,'differences':{k:{'baseline_only':[base[k][i] for i in sorted(set(base[k])-set(new[k]))],
        'fixed_only':[new[k][i] for i in sorted(set(new[k])-set(base[k]))]} for k in base},
        'interpretation':'Exact source versions remain distinct. A different catalogue copy is not silently merged. Original inclusion, final citation and legal applicability are separate.'}
(A/'artifacts/coverage-comparison.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({i:{s:{k:len(v) for k,v in d.items()} for s,d in r['differences'].items()} for i,r in out.items()}))
