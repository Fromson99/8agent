"""Read-only inspection of the preserved ADR1345 failure, without a model replay."""
from common import *
import sqlite3
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from semantic_runtime.legal_agent import journal_storage, evidence_inventory as ei
from semantic_runtime.contracts import digest
p=ART/'recorded-state/365-on.sqlite';before=sha(p)
db=journal_storage.connect(p.as_uri()+'?mode=ro',uri=True)
v=json.loads(db.execute("SELECT payload_json FROM entity_version WHERE entity_id='case:SELECT' ORDER BY version DESC LIMIT 1").fetchone()[0])
s=v['investigation_state'];db.close()
data=ROOT/read(DES/'baseline.json')['release']['data_path']
raw=sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro',uri=True)
rows=[]
for gid,current in s['selected'].items():
    records=list(ei.acquired_records(s,group_ids=[gid],include_context=False).values())
    verified=0;blocks=set()
    for record in records:
        for e in record['evidence']:
            for span in e['spans']:
                text=raw.execute('SELECT text FROM source_block WHERE document_id=? AND block_id=?',(record['document_id'],span['block_id'])).fetchone()[0]
                assert text[span['start_cp']:span['end_cp']]==span['text']
                blocks.add(span['block_id']);verified+=1
    rows.append({'branch':gid,'source_id':current['source_id'],'current_offer':current['offer'],
      'current_block_ids':sorted({x['block_id'] for e in current['evidence'] for x in e['spans']}),
      'same_branch_verified_offers':[r['offer']['id'] for r in records],
      'history_and_current_blocks':sorted(blocks),'verified_spans':verified})
raw.close();assert sha(p)==before
put(ART/'recorded-failure-audit.json',{'source_adr':'ADR1345 ontology-365 ontology-on',
 'journal_sha256':before,'original_journal_unchanged':True,'new_model_calls':0,'rows':rows,
 'finding':'Actual current selection retained only365 paragraph3, while verified same-branch history retained the whole four-block article. Old refresh inspected current only.',
 'scope':'Source acquisition evidence only; no retrospective modification of excluded goals or final legal decisions.'})
print('Read-only recorded failure verified',len(rows),'branches')
