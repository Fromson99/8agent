"""Repair scaffold report index only; sealed datasets/results/criteria are unchanged."""
from runtime import *
import finalize
m=read(D/'실험/manifest.json');cases=read(A/'dataset/product-cases.json');old=m['questions']
assert len(cases)==18 and old[0]['case_id']=='18'
placeholder=D/'실험/질문-001-18.md';placeholder.rename(A/'preflight/scaffold-question-placeholder.md')
m['questions']=[{'number':i,'case_id':c['id'],'file':f"질문-{i:03d}-{c['id']}.md",'sha256':sha(D/'실험'/f"질문-{i:03d}-{c['id']}.md")} for i,c in enumerate(cases,1)]
(D/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
new(A/'report-index-correction.json',{'reason':'CLI --questions18 interpreted18 as a case slug rather than count. Correct report index to the18 actual predeclared sealed product-case IDs. No question/criteria/run/judge/code modification. Original pre-call manifest remains immutable.','old_index':old,'new_index':m['questions']})
finalize.inventory()
