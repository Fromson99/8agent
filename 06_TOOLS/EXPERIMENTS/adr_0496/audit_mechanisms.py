"""Read-only audit of live article extents and model use of offered page actions."""
from pathlib import Path
import json,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0496-qwen-source-workflow-cm51-fsc10'
def main():
 f=json.loads((A/'product-cases.json').read_text());rows=[]
 with sqlite3.connect('file:'+str(R/f['generation']/'navigation/navigation.sqlite')+'?mode=ro',uri=True) as nav:
  for case in f['cases']:
   cid=case['case_id'];p=A/'artifacts/run-001'/cid/'repaired';t=json.loads((p/'trace.json').read_text());handles={h['handle']:json.loads(h['identity_json']) for h in t['handles']};ev={e['evidence_id']:e for e in t['evidence']};bykey={};article=[];matches=[]
   with sqlite3.connect('file:'+str(p/'journal.sqlite')+'?mode=ro',uri=True) as db:
    views={k:json.loads(v) for k,v in db.execute('SELECT view_id,body_json FROM model_view')}
   for action in t['actions']:
    req=json.loads(action['proposed_json']);res=json.loads(action['result_json'] or '{}')
    if action['actor']=='MODEL' and any(req['tool']==n['tool'] and req['args']==n['args'] for n in views.get(action['input_view_id'],{}).get('next_actions',[])):matches.append(action['action_id'])
    if req['tool']!='read' or req['args']['extent']!='article':continue
    n=handles.get(req['args']['target'],{});sid=n.get('source_id');ids=res.get('evidence_ids',[])
    if sid is None and ids:sid=ev[ids[0]]['source_id']
    sr=nav.execute('SELECT json FROM source WHERE id=?',(sid,)).fetchone()
    if not sr:article.append({'action_id':action['action_id'],'status':res.get('status','INTERRUPTED'),'verified':False,'reason':'No unambiguous canonical source in receipt'});continue
    blocks={b['block_id']:b['text'] for b in json.loads(sr[0])['blocks']};key=res.get('coverage_key');bykey.setdefault(key,set()).update(ids);spans=[s for eid in bykey[key] for s in ev[eid]['spans']];complete=True
    for bid,text in blocks.items():
     end=0
     for start,stop in sorted((s['start_cp'],s['end_cp']) for s in spans if s['block_id']==bid):
      if start>end:break
      end=max(end,stop)
     complete=complete and end==len(text)
    marked=res.get('coverage',{}).get('complete');article.append({'action_id':action['action_id'],'source_id':sid,'canonical_chars':sum(map(len,blocks.values())),'canonical_blocks':len(blocks),'read_blocks':len({s['block_id'] for s in spans}),'marked_complete':marked,'independent_complete':complete,'verified':bool(marked)==complete,'continuation':res.get('next_cursor')})
   rows.append({'case_id':cid,'article_reads':article,'offered_page_action_matches':matches,'views_with_next_actions':sum(bool(v.get('next_actions')) for v in views.values()),'live_article_path_exercised':bool(article)})
 out={'rows':rows,'note':'No live exercise is marked unverified, not assumed passed. Mechanical range/receipt checks do not certify legal correctness.'};(A/'artifacts/mechanism-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
