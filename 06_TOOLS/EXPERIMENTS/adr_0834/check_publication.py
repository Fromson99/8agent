"""Independent read-only check of published spans, side and saved consumers."""
from pathlib import Path
import json, hashlib, sqlite3
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0834-comparison-main78-live-check'
O=A/'artifacts/run-001/public-liquidity-01'
read=lambda p:json.loads(p.read_text())
def db(p):
    d=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True);d.row_factory=sqlite3.Row;return d
body=read(O/'response.json')['body'];run=read(O/'result.json')
saved=read(O/'status-response.json')['body'];duplicate=read(O/'duplicate-response.json')['body']
source=db(R/read(A/'artifacts/design/baseline.json')['manifest']['data_path']/'store.sqlite')
parent=db(R/run['journal_root']/'journal.sqlite')
evidence={}
for row in parent.execute('SELECT * FROM evidence_unit'):
    e=dict(row)
    e['spans']=[dict(s) for s in parent.execute('SELECT * FROM evidence_span WHERE evidence_id=? ORDER BY ordinal',(e['evidence_id'],))]
    metadata=json.loads(source.execute('SELECT json FROM document WHERE document_id=?',(e['document_id'],)).fetchone()[0]).get('document_metadata',{})
    e['side']=metadata.get('source_category')
    evidence[e['evidence_id']]=e
checks={}
for key in ('status','answer','comparison_items','evidence_refs','unreviewed_sources','research_attempts','latest_rag_attempts','report'):
    checks['saved_'+key]=body.get(key)==saved.get(key)
    checks['duplicate_'+key]=body.get(key)==duplicate.get(key)
checks['consumer_no_model_calls']=run['checks']['consumer_no_model_calls']
checks['within_model_budget']=run['model_calls']<=40
checks['active_pointer_unchanged']=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(A/'artifacts/design/baseline.json')['pointer']
cards=body['assembly']['term_agent']['source_bundle']['sources']
checks['published_ids_equal_cards']=set(body['evidence_refs'])=={c['selection_id'] for c in cards}
checks['cards_exact_original_spans']=all(c['selection_id'] in evidence and c['excerpt']=='\n'.join(s['text'] for s in evidence[c['selection_id']]['spans']) for c in cards)
checks['cards_correct_document_side']=all(c['side']==evidence[c['selection_id']]['side'] for c in cards)
citations=[];field_checks=[]
for row in body['comparison_items']['items']:
    for side in ('internal','external'):
        for v in [row[side],*row[side].get('alternatives',[])]:
            for c in v['citations']+v['dependencies']:
                citations.append({'evidence':c['evidence'],'side':side,'valid':c['evidence'] in evidence and evidence[c['evidence']]['side']==side and any(c['quote'] in s['text'] for s in evidence[c['evidence']]['spans'])})
        if row[side]['status']=='MISSING':
            field_checks.append(not row[side]['citations'] and not row[side]['text'] and not row[side]['scope_sufficient'])
    if row['content_status']!='UNKNOWN':
        field_checks.append(all(row[s]['citations'] and row[s]['status'] not in ('MISSING','CONFLICT') for s in ('internal','external')))
checks['field_quotes_own_side_and_exact']=all(c['valid'] for c in citations)
checks['missing_fields_not_fabricated']=all(field_checks)
checks['span_audit_pass']=all(c['exact_original_match'] for c in read(O/'audit.json')['evidence_span_checks'])
checks['unreviewed_are_published_on_correct_side']=all(e['evidence_id'] in body['evidence_refs'] and evidence[e['evidence_id']]['side']==e['side'] for e in body.get('unreviewed_sources',[]))
value={'checks':checks,'pass':all(checks.values()),'citation_occurrences_checked':len(citations),'source_cards_checked':len(cards),'field_rows_checked':len(body['comparison_items']['items']),'semantic_accuracy_certified':False}
(O/'publication-check.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(value,ensure_ascii=False))
