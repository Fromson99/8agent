"""Observe actual final requests without grading semantics or resending anything."""
from common import *
import ast
cid=sys.argv[1];P=ART/'live'/cid;f=read(DES/'freeze.json');C=ROOT/f['code_root']
def constant(path,name):
 tree=ast.parse(path.read_text())
 return ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign)
  and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)))
prompts=[constant(C/'02_BACKEND/semantic_runtime/legal_agent/completion_execution.py','MODERN_ASSESS_PROMPT'),
 constant(C/'02_BACKEND/semantic_runtime/legal_agent/completion_v8.py','PROMPT')]
rows=[]
for row in read(P/'calls.json'):
 if not str(row.get('stage','')).startswith('memory-assess'):continue
 path=P/'raw'/f"call-{row['number']:03d}"/'request.json.gz';request=read(path)
 system=request['messages'][0]['content'];user=request['messages'][1]['content']
 rows.append({'number':row['number'],'stage':row['stage'],'actual_provider':row.get('actual_provider'),
  'candidate_prompts_present_once':all(system.count(s)==1 for s in prompts),
  'system_chars':len(system),'user_chars':len(user),
  'scope_clause_present_in_input':'상장예비심사를 신청한 후에 국내에서 모집·매출한' in user,
  'request_path':str(path.relative_to(ROOT)),'request_sha256':sha(path)})
put(P/'prompt-audit.json',{'case_id':cid,'final_calls':rows,'reached_final_assessment':bool(rows),
 'all_observed_final_calls_use_candidate':bool(rows) and all(x['candidate_prompts_present_once'] for x in rows),
 'meaning_verified_by_this_audit':False,'new_model_calls':0})
print(json.dumps(rows,ensure_ascii=False))
