from pathlib import Path
import hashlib,json,sys
root=Path(sys.argv[1]).resolve()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
changed={'02_BACKEND/semantic_runtime/legal_agent/'+f for f in ('structure_query.py','investigation_chain.py','law_navigation.py','judgment_view.py')}
changed|={'02_BACKEND/semantic_runtime/progress.py','08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'}
p=root/'00_SYSTEM/PIPELINE.json';pipeline=json.loads(p.read_text())
for e in pipeline['engines'].values():
 ep=root/e['manifest'];v=json.loads(ep.read_text());dirty=False
 for f in changed&set(v['files']):
  if v['files'][f]!=sha(root/f):v['files'][f]=sha(root/f);dirty=True
 if dirty:put(ep,v);e['sha256']=sha(ep)
put(p,pipeline)
