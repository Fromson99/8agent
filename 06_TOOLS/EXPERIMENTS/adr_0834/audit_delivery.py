"""Read-only audit of actual assessment source delivery; no calls or repairs."""
from pathlib import Path
import json,sqlite3,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0834-comparison-main78-live-check'
O=A/'artifacts/run-001/public-liquidity-01'
rows=[];journals=[]
for p in sorted((O/'runtime').rglob('journal.sqlite')):
    before=hashlib.sha256(p.read_bytes()).hexdigest()
    db=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    for row in db.execute('SELECT view_id,body_json FROM model_view'):
        view=json.loads(row['body_json'])
        if view.get('source_stage') not in ('memory-assess','memory-assess-repair'):continue
        opts=view.get('evidence_options',[])
        if not opts:continue
        presentations=[]
        for e in db.execute('SELECT e.* FROM presentation p JOIN evidence_unit e USING(evidence_id) WHERE p.view_id=?',(row['view_id'],)):
            for s in db.execute('SELECT * FROM evidence_span WHERE evidence_id=?',(e['evidence_id'],)):
                presentations.append((e['source_id'],e['document_id'],s['block_id'],s['start_cp'],s['end_cp'],s['text']))
        expected={(o['source_id'],o['document_id'],o['block_id'],o['start_cp'],o['end_cp'],o['text']) for o in opts}
        attempts=[dict(v) for v in db.execute('SELECT attempt_id,status FROM model_attempt WHERE view_id=?',(row['view_id'],))]
        rows.append({'journal':str(p.relative_to(R)),'view_id':row['view_id'],'stage':view['source_stage'],'option_spans':len(expected),
                     'presentation_spans':len(presentations),'exact_options_recorded':expected<=set(presentations),'attempts':attempts})
    db.close();after=hashlib.sha256(p.read_bytes()).hexdigest();assert before==after
    journals.append({'path':str(p.relative_to(R)),'sha256':before})
result={'kind':'read-only actual journal audit','assessment_views':rows,'all_exact_options_recorded':bool(rows) and all(r['exact_options_recorded'] for r in rows),
        'journals_unchanged':True,'journal_hashes':journals,'extra_model_calls':0,'legal_accuracy_certified':False}
(O/'delivery-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'assessment_views':len(rows),'all_exact_options_recorded':result['all_exact_options_recorded'],'journals_unchanged':True}))
