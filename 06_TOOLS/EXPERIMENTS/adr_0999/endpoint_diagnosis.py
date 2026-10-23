"""Inspect the stored article-only endpoint and exact saved payloads, read-only."""
from common import *
import sqlite3
P=ART/'known-query/candidate'
s=read(ART/'stage.json')
db=sqlite3.connect((ROOT/s['base_release']['data_path']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
rid='ref:c831c0e077405835b0917ae8';sid='article:0d5ed1a27bf5ae92bad392e3'
ref=json.loads(db.execute('select json from reference where id=?',(rid,)).fetchone()[0])
source=json.loads(db.execute('select json from source where id=?',(sid,)).fetchone()[0])
known={str(b['block_id']) for b in source['blocks']}
snapshots=[]
for raw in (P/'scope-trace.jsonl').open():
 e=json.loads(raw)
 if e['kind']!='scoped_catalog':continue
 for g in e['data']['groups']:
  for c in g['connections']:
   if c['reference_id']==rid:snapshots.append({'seq':e['seq'],'time':e['time'],'target':g['target'],'connection':c})
checks=read(ART/'source-audit.json');evidence=[r for r in checks['read_evidence'] if r['source_id']==sid]
read_blocks={str(b) for r in evidence for b in r['blocks']}
record={'reference':ref,'canonical_target_block_ids':sorted(known),
 'acquired_target_block_ids':sorted(read_blocks),'entire_article_acquired':known<=read_blocks,
 'catalog_snapshots':snapshots,
 'cause':'catalog endpoint_read requires bool(end.block_ids). Stored article-only reference has empty block_ids; optional CITES also has empty required_blocks. The displayed endpoint_block_ids separately falls back to all canonical blocks, but already_read does not. Thus an acquired entire article still has an unread inline card and READ action.',
 'secondary_effect':'The repeated READ action is rejected as unchanged navigation action; one native correction repeats it. No duplicate original read executes.',
 'code_path':'02_BACKEND/semantic_runtime/legal_agent/unit_relations.py',
 'correction_required':'Use the same validated effective endpoint extent for read coverage and display; suppress READ when exact complete target is already acquired. Preserve partial-read and source integrity checks.',
 'code_changed_in_this_experiment':False}
save(ART/'article-endpoint-diagnosis.json',record)
print('Stored article-only blocks:',ref['targets'][0]['block_ids'],'canonical:',len(known),'acquired:',len(read_blocks),'fully_acquired:',known<=read_blocks)
db.close()
