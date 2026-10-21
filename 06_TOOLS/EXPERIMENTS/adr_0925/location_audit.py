"""Post-selection exact coordinate audit across duplicate catalogue documents."""
from pathlib import Path
import json,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0925-source-lead-exact-observation';P=A/'artifacts/run-001/observed/leverage-comparison'
read=lambda p:json.loads(p.read_text());G=R/read(A/'artifacts/design/baseline.json')['manifest']['data_path']
def db(p):
 d=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True);d.row_factory=sqlite3.Row;return d
nav=db(G/'navigation/navigation.sqlite');store=db(G/'store.sqlite');body=read(P/'response.json')['body'];audit=read(P/'audit.json')
returned=set(body.get('rag_results',{}).get('external',{}).get('evidence_ids',[]));cited=set(body.get('evidence_refs',[]));rows={}
for j in audit['journals']:
 if j['side']!='external':continue
 d=db(R/j['path'])
 for e in d.execute('SELECT * FROM evidence_unit'):
  raw=nav.execute('SELECT json FROM source WHERE id=?',(e['source_id'],)).fetchone();src=json.loads(raw[0]) if raw else {}
  name=src.get('document_name','');heading=src.get('heading','').split()[0] if src.get('heading') else ''
  if '금융투자업규정' not in name or '시행세칙' in name or heading not in ('제3-6조','제3-24조의4','제3-26조'):continue
  rec=rows.setdefault(e['source_id'],{'source_id':e['source_id'],'document_id':e['document_id'],'document_name':name,'coordinate':heading,'artifact_sha256':e['source_artifact_hash'],'read_spans':[],'returned_spans':[],'cited_spans':[]})
  spans=[dict(x) for x in d.execute('SELECT block_id,start_cp,end_cp,text FROM evidence_span WHERE evidence_id=?',(e['evidence_id'],))]
  for key,keep in [('read_spans',True),('returned_spans',e['evidence_id'] in returned),('cited_spans',e['evidence_id'] in cited)]:
   if keep:
    for s in spans:
     if s not in rec[key]:rec[key].append(s)
 d.close()
for sid,row in rows.items():
 src=json.loads(nav.execute('SELECT json FROM source WHERE id=?',(sid,)).fetchone()[0]);did=row['document_id'];uid=str(src['unit_id'])
 unit=json.loads(store.execute('SELECT json FROM source_unit WHERE document_id=? AND unit_id=?',(did,uid)).fetchone()[0]);lo,hi=unit['span']
 # For 3-26, report paragraph 7 independently of article title/other paragraphs.
 if row['coordinate']=='제3-26조':
  matches=[json.loads(x[0]) for x in store.execute('SELECT json FROM source_unit WHERE document_id=? AND parent_id=?',(did,uid))]
  para=next((v for v in matches if v.get('surface')=='⑦'),None)
  if para is None:raise ValueError('Paragraph 7 not structurally identified: '+sid)
  lo,hi=para['span'];row['checked_scope']='제3-26조 제7항'
 else:row['checked_scope']=row['coordinate']+' 전체'
 expected=[{'block_id':str(x[0]),'end_cp':len(x[1])} for x in store.execute('SELECT block_id,text FROM source_block WHERE document_id=? AND CAST(block_id AS INTEGER)>=? AND CAST(block_id AS INTEGER)<?',(did,lo,hi))]
 for key in ('read','returned','cited'):
  spans=row.pop(key+'_spans');selected=[s for s in spans if lo<=int(s['block_id'])<hi]
  row[key+'_scope_observed']=bool(selected)
  def covered(w):
   end=0
   for s in sorted([s for s in selected if s['block_id']==w['block_id']],key=lambda s:s['start_cp']):
    if s['start_cp']>end:break
    end=max(end,s['end_cp'])
   return end>=w['end_cp']
  row[key+'_scope_complete']=bool(expected) and all(covered(w) for w in expected)
  row[key+'_block_ids']=sorted({s['block_id'] for s in selected},key=int)
out={'post_selection_only':True,'legal_gold':False,'source':'Exact acquired journals and selected generation structural coordinates; duplicate catalogue variants retained separately','variants':list(rows.values()),'note':'Required canonical IDs in trace.json remain unchanged. This audit identifies other actually read copies of the same named provisions; it does not infer legal equivalence across versions.'}
(P/'location-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False))
