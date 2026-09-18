"""Ordinary contracts and read-only source binding; no live model or quality study."""
import subprocess,os
from runtime import *
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 if (A/'verification.json').exists():raise ValueError('completed audit is immutable')
 mod,typed,multi,mods,root=load();cm=read(C/'candidate.json');rev=cm['revisions'][-1];manifest=read(D/'실험/manifest.json')
 manifest['design']['code_isolation']['candidates']=[{'candidate_id':'mapped','experiment_id':manifest['experiment_id'],'arm_id':'mapped','run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str((T/'runtime.py').relative_to(R)),'runner_sha256':sha(T/'runtime.py')}];write(D/'실험/manifest.json',manifest)
 active=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/active['manifest_path']);data=R/release['data_path'];projection=R/'04_EXPERIMENTS/ADR/ADR-0449-multi-entry-catalogue-navigation/artifacts/origin-projection.json'
 paths=list(T.glob('*.py'))+[A/'design-before-snapshot.json',projection,C/'candidate.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',data/'manifest.json',data/'store.sqlite']+[R/f['frozen_path'] for f in rev['files']]+[R/'02_BACKEND/semantic_runtime'/f for f in ('provider.py','genos.py','storage.py','term_index.py','learning_store.py')]
 lock={str(p.relative_to(R)):sha(p) for p in paths};new(A/'input-lock.json',lock)
 env={**os.environ,'PYTHONPATH':'02_BACKEND','ADR451_TEST_FROZEN':'1'}
 cmd=['.venv/bin/python','-B','-m','pytest','-q','-p','no:cacheprovider',str((T/'test_mapping.py').relative_to(R))];p=subprocess.run(cmd,capture_output=True,text=True,env=env);new(A/'tests.json',{'command':cmd,'returncode':p.returncode,'output':p.stdout+p.stderr})
 # Public ESG metadata only, disposable operator ledger, never active learning data.
 allow=A/'public-authorized-documents.json';new(allow,['65731d03bd65c441']);ledger=A/'operator-smoke.sqlite'
 common=['--generation',str(data),'--origin-projection',str(projection),'--authorized-documents',str(allow),'--actor','audit-example-operator']
 def cli(command,args):
  cmd=['.venv/bin/python','-B',str(T/'learn.py'),'--ledger',str(ledger),command,*common,*args];r=subprocess.run(cmd,capture_output=True,text=True,env=env)
  if r.returncode:raise RuntimeError(r.stderr)
  return {'command':cmd,'output':json.loads(r.stdout),'returncode':r.returncode}
 records=[cli('mapping-targets',['--type','folder','--query','kofia'])]
 records.append(cli('mapping-add',['--expression','금투협','--type','folder','--identity','external/kofia','--reason','공개 메타데이터 CLI 계약 검사']))
 ident=records[-1]['output']['candidate_id'];records.append(cli('mapping-list',[]));assert records[-1]['output'][0]['status']=='APPROVED'
 records.append(cli('mapping-review',['--candidate',ident,'--status','REVOKED','--reason','검사 종료; 운영 매핑 아님']))
 new(A/'operator-smoke.json',{'scope':'one public ESG document metadata; isolated audit ledger','model_calls':0,'steps':records})
 drift=[path for path,h in lock.items() if sha(R/path)!=h]
 v={'passed':p.returncode==0 and not drift,'kind':'ordinary implementation and wiring contract audit','contract_tests':21,'operator_cli_actual_generation_checked':True,'operator_ledger':str(ledger.relative_to(R)),'input_drift':drift,'live_model_calls':0,'external_transmission':False,'genos_transport':'existing provider mocked at request_json; actual internal endpoint not accessed','active_release':active['release_id'],'main_unchanged':True,'quality_certified':False,'limitations':['No live LLM interpretation accuracy measurement','Explicit research factory/operator CLI only; no active MAIN or GENOS deployment','Mappings are operator-specific and generation/store/scope bound; not canonical legal definitions','Lookup uses metadata names; absent/ambiguous semantic candidates still require user clarification']};new(A/'verification.json',v);print(json.dumps(v,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
