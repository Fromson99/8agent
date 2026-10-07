"""Read-only range audit. No LLM replay, source mutation, or changed scoring."""
import json,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0492-source-article-read-scope'
def main():
 f=json.loads((A/'product-cases.json').read_text());rows=[]
 with sqlite3.connect('file:'+str(R/f['generation']/'navigation/navigation.sqlite')+'?mode=ro',uri=True) as db:
  for arm in ['baseline','repaired']:
   t=json.loads((A/'artifacts/run-001/cm-018'/arm/'trace.json').read_text())
   handles={h['handle']:json.loads(h['identity_json']) for h in t['handles']};evidence={e['evidence_id']:e for e in t['evidence']};by_key={}
   for action in t['actions']:
    request=json.loads(action['proposed_json']);result=json.loads(action['result_json'])
    if request['tool']!='read' or request['args']['extent']!='article':continue
    n=handles.get(request['args']['target'],{});sid=n.get('source_id');key=result.get('coverage_key');ids=result.get('evidence_ids',[])
    if sid is None and ids:sid=evidence[ids[0]]['source_id']
    source=db.execute('SELECT json FROM source WHERE id=?',(sid,)).fetchone()
    if not source:
     rows.append({'arm':arm,'action_id':action['action_id'],'status':result['status'],'scope_verified':False,'reason':'no single canonical source in action receipt'});continue
    blocks={b['block_id']:b['text'] for b in json.loads(source[0])['blocks']}
    by_key.setdefault(key,set()).update(ids)
    spans=[s for eid in by_key[key] for s in evidence[eid]['spans']]
    full=True
    for bid,text in blocks.items():
     end=0
     for start,stop in sorted((s['start_cp'],s['end_cp']) for s in spans if s['block_id']==bid):
      if start>end:break
      end=max(end,stop)
     full=full and end==len(text)
    marked=result.get('coverage',{}).get('complete')
    rows.append({'arm':arm,'action_id':action['action_id'],'source_id':sid,'canonical_blocks':len(blocks),'read_blocks':len({s['block_id'] for s in spans}),'canonical_chars':sum(map(len,blocks.values())),'marked_complete':marked,'independent_complete':full,'scope_verified':bool(marked)==full,'continuation':result.get('next_cursor'),'status':result['status']})
 out={'rows':rows,'candidate_article_calls':sum(r['arm']=='repaired' for r in rows),'candidate_false_complete':sum(r['arm']=='repaired' and r.get('marked_complete') and not r.get('independent_complete') for r in rows),'note':'Union checked against immutable canonical source blocks; synthetic range/paging tests separately cover cases not exercised live.'}
 (A/'artifacts/article-scope-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
