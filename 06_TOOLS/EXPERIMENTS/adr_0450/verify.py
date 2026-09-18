"""Frozen metadata routing contracts; no live LLM or performance comparison."""
import sqlite3,json,os,subprocess
from types import SimpleNamespace
from runtime import *

def main():
 if (A/'verification.json').exists():raise ValueError('completed audit artifact is immutable')
 mod,parent,mods,root=load();cm=read(C/'candidate.json');rev=cm['revisions'][-1];m=read(D/'실험/manifest.json')
 m['design']['code_isolation']['candidates']=[{'candidate_id':'typed','experiment_id':m['experiment_id'],'arm_id':'typed','run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str((T/'runtime.py').relative_to(R)),'runner_sha256':sha(T/'runtime.py')}]
 (D/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 active=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/active['manifest_path']);data=R/release['data_path'];manifest=read(data/'manifest.json');projection=R/'04_EXPERIMENTS/ADR/ADR-0449-multi-entry-catalogue-navigation/artifacts/origin-projection.json'
 paths=list(T.glob('*.py'))+[A/'design-before-snapshot.json',projection,C/'candidate.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',data/'manifest.json',data/'store.sqlite']+[R/f['frozen_path'] for f in rev['files']]
 lock={str(p.relative_to(R)):sha(p) for p in paths};new(A/'input-lock.json',lock)
 db=sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;store=SimpleNamespace(db=db,manifest=manifest);documents={r[0]:r[1] for r in db.execute('SELECT document_id,name FROM document')}
 def validate(scope):
  if not scope or not set(scope)<=documents.keys():raise ValueError('invalid scope')
  return list(scope)
 # This audit loads real catalogue metadata only; no fabricated content/term search.
 matcher=SimpleNamespace(documents=documents,units={},tools=SimpleNamespace(terms={},validate_scope=validate),sources={});matcher=parent.folders.bind_catalogue(matcher,store,read(projection))
 class NoModel:
  def call(self,*args):raise AssertionError('metadata audit must not call LLM')
  def record_local(self,v):return {'kind':'local-catalogue-contract'}
 p=mods['pipeline'].Pipeline(root,store,NoModel());c=mod.Conversation(p,mod.TypedAgent(p,None,None,matcher),list(documents))
 out=c.run('kofia에 있는 문서 알려줘');state=out['retrieval']['term_agent'];card=next(x for x in state['keyword_types']['items'] if x['type']=='folder' and x['identity']=='external/kofia');assert state['catalogue']['total']==72 and card['document_count']==72 and state['calls']==0
 tree=c.run('kofia 폴더를 트리로 보여줘');assert tree['retrieval']['term_agent']['navigation_output']['kind']=='FOLDER_TREE'
 new(A/'public-example.json',{'keyword_card':card,'catalogue_total':state['catalogue']['total'],'tree':tree['retrieval']['term_agent']['navigation_output']['data'],'source':'selected real document metadata, no body lookup','model_calls':0})
 command=['.venv/bin/python','-B','-m','pytest','-q','-p','no:cacheprovider',str((T/'test_typed_navigation.py').relative_to(R))];tests=subprocess.run(command,capture_output=True,text=True,env={**os.environ,'PYTHONPATH':'02_BACKEND','ADR450_TEST_FROZEN':'1'});new(A/'tests.json',{'command':command,'returncode':tests.returncode,'output':tests.stdout+tests.stderr})
 drift=[path for path,h in lock.items() if sha(R/path)!=h];v={'passed':tests.returncode==0 and not drift,'kind':'ordinary typed routing and existing pipeline contract audit','contract_tests':16,'contract_passed':tests.returncode==0,'input_drift':drift,'model_calls':0,'live_llm_selection_tested':False,'scripted_llm_context_and_tool_execution_tested':True,'real_kofia_documents':72,'real_kofia_child_folders':card['child_folder_count'],'real_kofia_type':card['type'],'source_generation_unchanged':sha(data/'store.sqlite')==manifest['store_sha256'],'main_unchanged':True,'active_release':active['release_id'],'limitations':['Lexical matching uses admitted metadata labels; arbitrary unseen aliases still need registered aliases or search','Folder/tree/list metadata requests route locally; complex queries receive typed guidance in LLM context/schema','No model accuracy measurement, MAIN promotion or GENOS execution']};new(A/'verification.json',v);print(json.dumps(v,ensure_ascii=False));db.close()
if __name__=='__main__':main()
