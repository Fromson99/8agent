"""Saved-view transformation audit only. No LLM, no invented replacement decisions."""
from pathlib import Path
import sys,json,gzip,hashlib,socket
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1155-investigation-focus-offline';F=json.loads((A/'artifacts/design/freeze.json').read_text());S=R/F['code_root']
sys.path.insert(0,str(S/'02_BACKEND'))
def blocked(*a,**kw):raise RuntimeError('External network forbidden in offline replay')
socket.socket.connect=blocked;socket.create_connection=blocked
from semantic_runtime.legal_agent import read_candidate_pages as pages,compact_model_input as minimal
from semantic_runtime.legal_agent.navigation_input import NavigationReferences,expand_cards
from semantic_runtime.legal_agent.gateway import compact_wire_view
from semantic_runtime.legal_agent.repository import encoded
from copy import deepcopy
for n,h in F['files'].items():assert hashlib.sha256((S/n).read_bytes()).hexdigest()==h
assert str(S) in pages.__file__
P=R/'04_EXPERIMENTS/ADR/ADR-1151-main109-cm51-qwen/artifacts/run-001';results=[]
def size(v):return len(encoded({'view':v}))
def wire(v,s):
 refs=NavigationReferences(v)
 return minimal.project(compact_wire_view(refs.view(v),'investigate'),refs.schema(s))
for case in ['cm-007','cm-009']:
 rows=[]
 for f in sorted((P/case/'canonical').glob('[0-9][0-9][0-9].json.gz')):
  o=json.loads(gzip.decompress(f.read_bytes()));v=o['view'];schema=o['schema']
  if 'read_candidates' not in v:continue
  prior=deepcopy(v);seen=set();seen_read=set();seen_scopes=set();v0,s0=pages.page_view(v,schema,0,20)
  for p in range(v0['read_candidate_page']['pages']):
   view,sc=pages.page_view(v,schema,p,20)
   seen.update((x['choice'],x['target']) for x in view['tool_options']);seen_read.update(x['target'] for x in view['read_candidates']);seen_scopes.update(x['id'] for x in view.get('connection_scope_choices',[]))
   assert view['sources']==v['sources'] and view['read_judgments']==v['read_judgments'] and view['request']==v['request']
   for b in sc['anyOf']:
    kind=b['properties']['choice'].get('const')
    if kind=='READ':assert set(b['properties']['selections']['items']['properties']['target']['enum'])=={x['target'] for x in view['read_candidates']}
    elif 'target' in b['properties']:assert set(b['properties']['target']['enum'])=={x['target'] for x in view['tool_options'] if x['choice']==kind}
  assert seen=={(x['choice'],x['target']) for x in v['tool_options']}
  assert seen_read=={x['target'] for x in v['read_candidates']}
  assert seen_scopes=={x['id'] for x in v.get('connection_scope_choices',[])}
  assert v==prior
  before=wire(v,schema);after=wire(v0,s0)
  # Actual stored wire and reconstructed baseline must agree before comparison.
  raw=json.loads(gzip.decompress((P/case/'wire'/f.name).read_bytes()))
  delivered=json.loads(next(x['content'] for x in raw['messages'] if x['role']=='user'))['view']
  assert before==delivered,(case,f.name,'baseline wire mismatch')
  assert expand_cards(after)['sources']==expand_cards(before)['sources']
  rows.append({'input':str(f.relative_to(R)),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'baseline_chars':size(before),'candidate_first_page_chars':size(after),'tool_before':len(v['tool_options']),'tool_first_page':len(v0['tool_options']),'pages':v0['read_candidate_page']['pages'],'all_original_targets_reachable':True,'source_question_judgments_preserved':True,'baseline_wire_exact':True})
 results.append({'case':case,'views':rows})
output={'type':'saved-input-projection-audit','new_model_calls':0,'network_blocked':True,'view_count':sum(len(x['views']) for x in results),'cases':results,'limits':'Menu projection only, no new semantic choices or final answers. Original decisions not replayed as if they matched new pages. New goal observations not fabricated.'}
(A/'artifacts/run-001').mkdir(exist_ok=True)
(A/'artifacts/run-001/replay.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'views':output['view_count'],'last_views':[x['views'][-1] for x in results]},ensure_ascii=False))
