from common import *
import sys
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from semantic_runtime.legal_agent.navigation_input import expand_cards
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1020-direct-connections-bounded-review/artifacts/known-query/candidate'
selections=[json.loads(l)['data'] for l in (P/'scope-trace.jsonl').open() if json.loads(l)['kind']=='scope_selected']
old=selections[0];new=next(s for s in selections if s['id']!=old['id'])
def spans(s):return {(m['source_id'],p['block_id'],p['start_cp'],p['end_cp'],p.get('span_hash')) for m in s['members'] for p in m['spans']}
v=expand_cards(json.loads(read(P/'model/call-007-service/request.json')['messages'][1]['content'])['view'])
assert old['structural_selection']==new['structural_selection'] and spans(old)<spans(new)
assert len(v['references']['dependency_cards'])==0 and v['references']['selected_scope_id']==old['id']
save(ART/'scope-loss-diagnosis.json',{'recorded_parent':'ADR1020/candidate/call007','old_scope_id':old['id'],'new_scope_id':new['id'],
 'selected_structure_identical':True,'old_spans':len(spans(old)),'new_spans':len(spans(new)),'old_spans_preserved':True,
 'visible_dependency_cards_before_fix':0,'source_request_sha256':sha(P/'model/call-007-service/request.json'),
 'cause':'Candidate list recomputed delivered-member hash after new paragraph acquisition; selection still pointed at old hash and had no matching candidate. Exact structural selection was unchanged.',
 'correction':'Preserve structural authority, verify old-span subset, refresh selected delivery identity; no new model selection or target READ.'})
print('Exact recorded scope loss:',len(spans(old)),'->',len(spans(new)),'spans; same structure; 0 cards')
