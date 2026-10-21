from common import *
import sys,shutil,os
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
assert not (DES/'freeze.json').exists()
base=read(DES/'baseline.json');data=ROOT/base['release']['data_path']
assert sha(data/'store.sqlite')==base['grant']['source_store_sha256']
config=Path('/home/jin/.cache/huggingface/hub/models--BAAI--bge-m3/snapshots/5617a9f61b028005a4858fdac845db406aefb181')
weight=Path('/home/jin/.cache/huggingface/hub/models--BAAI--bge-m3/snapshots/9a0624b896d81da7492a910ffa53731274b6cf3d/model.safetensors')
model=ART/'models/bge-m3';model.mkdir(parents=True)
models={};paths=[]
for p in sorted(config.rglob('*')):
    if p.is_file() and p.suffix in ('.json','.model'):
        q=model/p.relative_to(config);q.parent.mkdir(parents=True,exist_ok=True);os.link(p.resolve(),q);paths.append(q)
os.link(weight.resolve(),model/'model.safetensors');paths.append(model/'model.safetensors')
rerank=ROOT/'04_EXPERIMENTS/ADR/ADR-0218-retrieval-assembly-answer-guards/artifacts/models/mmarco-mMiniLMv2-L12-H384-v1'
old=read(ROOT/'04_EXPERIMENTS/ADR/ADR-0226-fresh-retrieval-scoped-context/artifacts/models-lock.json')[1]
for row in old['files']:assert sha(rerank/row['path'])==row['sha256']
paths.extend(rerank/row['path'] for row in old['files'])
put(DES/'models.json',{'embedding':str(model.relative_to(ROOT)),'embedding_provenance':'Existing BGE-M3 config5617a9f + cached safetensors9a0624; exact byte hashes and fresh-cache cosine check required; no download','reranker':str(rerank.relative_to(ROOT)),'reranker_revision':old['revision'],'files':{str(p.relative_to(ROOT)):sha(p) for p in paths}})
source=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0969/dense-rerank/snapshot'/TARGET
dense=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0969/dense'
dest=dense/'snapshot'/TARGET;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
m=read(ADR/'실험/manifest.json');cs=[]
for arm in ('dense','dense-rerank'):
    c=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0969'/arm
    ac.register_file(c,TARGET,upstream_state='absent');ac.freeze(c);assert not ac.validate(c)
    cm=read(c/'candidate.json');rev=cm['revisions'][-1];runner=Path(__file__).with_name('run.py')
    cs.append({'candidate_id':arm,'arm_id':arm,'experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((c/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(c/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(ROOT)),'runner_sha256':sha(runner)})
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=cs)
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((RUN/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
inputs=[data/'store.sqlite',data/'manifest.json',ROOT/'01_DATA/embeddings/sections/meta.jsonl',ROOT/'01_DATA/embeddings/sections/vectors.npz',ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',ROOT/'02_BACKEND/lawrag/research/experiment_client.py',ROOT/'01_DATA/GOLDEN/registry-v2-risk_cm.json']
inputs+=list(DES.glob('*.json'));inputs+=list(Path(__file__).parent.glob('*.py'))
put(DES/'freeze.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in inputs},'candidates':cs,'product_calls_before_freeze':0})
print('Frozen sources, shared model weights, two candidate revisions, scripts; no model calls')
