"""Freeze baseline, explicit revision overlays, data, transport, controls and grading."""
from pathlib import Path
import json,hashlib,datetime,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0558-model-presentation-repair'
def read(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while chunk:=f.read(8388608):h.update(chunk)
 return h.hexdigest()
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 assert not (A/'artifacts/frozen-design.json').exists()
 active=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert active['generation']==31
 manifest=R/active['manifest_path'];assert sha(manifest)==active['release_manifest_sha256']
 release=read(manifest);code=R/release['code_root'];paths=[]
 for name,expected in release['files'].items():
  p=code/name;assert sha(p)==expected,name;paths.append(p)
 fixture=read(A/'product-cases.json');gen=R/release['data_path'];assert fixture['generation']==release['data_path']
 assert sha(gen/'manifest.json')==release['data_manifest_sha256']
 grant=read(code/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')
 assert set(grant['public_document_ids'])==set(fixture['public_scope_document_ids'])
 assert sha(gen/'store.sqlite')==grant['source_store_sha256']
 assert sha(code/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')==grant['policy_sha256']
 assert sha(R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')==grant['policy_sha256']
 basis=R/grant['basis_path'];assert sha(basis)==grant['basis_sha256']
 old=read(basis);assert sha(R/'08_DEPLOYMENT/CONFIG/legal-source-export.json')==old['source_authorization_sha256']
 for doc in old['document_provenance']:assert sha(R/'01_DATA/RAW'/doc['raw_relative_path'])==doc['raw_sha256']
 gold=read(A/'gold-cases.json');g=next(c for c in gold['cases'] if c['case_id']=='structure-explicit')
 g['decisive_source_ids']=['article:f4703af26401fad7f666a0d1']
 g['reference_answer']='상법 제389조 제1항: 회사는 이사회의 결의로 회사를 대표할 이사를 선정하여야 한다. 정관으로 주주총회에서 이를 선정할 것을 정할 수 있다.'
 write(A/'gold-cases.json',gold)
 m=read(A/'실험/manifest.json');overlays={};candidates=[]
 runner=Path(__file__).with_name('run_probe.py')
 for arm in ('presentation','selected-only'):
  c=R/'02_BACKEND/lawrag/research/candidates/adr_0558'/arm;cm=read(c/'candidate.json');rev=cm['revisions'][-1]
  for file in cm['files']:
   if file['upstream_state']=='present':assert sha(code/file['target_path'])==file['upstream_sha256'],file['target_path']
  for file in rev['files']:
   p=R/file['frozen_path'];assert sha(p)==file['snapshot_sha256'];paths.append(p)
  overlays[arm]=str((R/rev['files'][0]['frozen_path']).parent.relative_to(R))
  paths.append(c/'candidate.json')
  candidates.append({'candidate_id':arm,'experiment_id':m['experiment_id'],'arm_id':arm,'run_ids':['run-001'],'manifest_path':str((c/'candidate.json').relative_to(R)),'manifest_sha256':sha(c/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(R)),'runner_sha256':sha(runner)})
 write(A/'artifacts/selected-main.json',active)
 paths += [manifest,A/'PLAN.md',A/'product-cases.json',A/'artifacts/selected-main.json',basis,R/'08_DEPLOYMENT/CONFIG/legal-source-export.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'02_BACKEND/lawrag/research/experiment_client.py',R/'02_BACKEND/lawrag/research/openrouter_legal_adapter.py']
 paths += list(Path(__file__).parent.glob('*.py'))
 paths += [gen/name for name in ('manifest.json','navigation/manifest.json','fulltext/manifest.json')]
 m['design']['code_isolation']['candidates']=candidates;m['dataset']['sha256']=sha(A/'product-cases.json')
 design={'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'code_root':release['code_root'],'generation':release['data_path'],'profile_path':str((code/'00_SYSTEM/LEGAL_AGENT/profile-tools-v5.json').relative_to(R)),'release_binding':active,'candidate_overlays':overlays,'transport_path':'02_BACKEND/lawrag/research/experiment_client.py','file_hashes':{str(p.relative_to(R)):sha(p) for p in paths},'grader_only_hashes':{str((A/'gold-cases.json').relative_to(R)):sha(A/'gold-cases.json')},'design':m['design'],'runs':m['runs'],'workers':2,'model':'google/gemma-4-31b-it','configs':{arm:{'model':'google/gemma-4-31b-it','thinking_level':'off'} for arm in ('baseline','presentation','selected-only')},'product_gold_visible':False,'production_code_changed':False,'pipeline_entrypoint':'Frozen semantic_runtime.pipeline.Pipeline.run with coordinator and synchronous publication','mutable_main_pointers_used':False,'max_physical_calls':270}
 write(A/'artifacts/frozen-design.json',design);write(A/'실험/manifest.json',m)
 print('Frozen',len(paths),'files, 2 candidate revisions, generation31; no calls')
if __name__=='__main__':main()
