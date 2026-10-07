"""Bind exact already selected product release and a research-only Qwen transport."""
from pathlib import Path
import datetime, hashlib, json

R = Path(__file__).resolve().parents[3]
A = R/'04_EXPERIMENTS/ADR/ADR-0557-structure-main-qwen14'
C = R/'02_BACKEND/lawrag/research/candidates/adr_0557/structure-main'
PREVIOUS = R/'04_EXPERIMENTS/ADR/ADR-0555-pecab-only-catalogue-routing/artifacts/frozen-design.json'

def read(p):
    return json.loads(p.read_text())

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while c:=f.read(8388608):
            h.update(c)
    return h.hexdigest()

def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')

def main():
    assert not (A/'artifacts/frozen-design.json').exists()
    active=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
    assert active['release_id']=='legal-agent-structure-catalogue-pecab-20260929-r1'
    assert active['generation']==30
    manifest_path=R/active['manifest_path']
    assert sha(manifest_path)==active['release_manifest_sha256']
    release=read(manifest_path)
    code=R/release['code_root']
    paths=[]
    for name,expected in release['files'].items():
        p=code/name
        assert sha(p)==expected,name
        paths.append(p)
    fixture=read(A/'product-cases.json')
    gen=R/release['data_path']
    assert fixture['generation']==release['data_path']
    assert sha(gen/'manifest.json')==release['data_manifest_sha256']
    grant=dict(read(PREVIOUS)['export_authorization'])
    policy=A/'artifacts/scoped-model-policy.json'
    grant.update(experiment_policy_path=str(policy.relative_to(R)),policy_sha256=sha(policy),
        basis='User requested new exact structure-first MAIN generation30; same authorized public originals; scoped Qwen policy only')
    assert set(grant['scope_document_ids'])==set(fixture['public_scope_document_ids'])
    assert sha(gen/'store.sqlite')==grant['source_store_sha256']
    assert read(gen/'manifest.json')['generation_id']==grant['generation_id']
    assert sha(R/'08_DEPLOYMENT/CONFIG/legal-source-export.json')==grant['source_authorization_sha256']
    for doc in grant['document_provenance']:
        assert sha(R/'01_DATA/RAW'/doc['raw_relative_path'])==doc['raw_sha256']
    ft=read(gen/'fulltext/manifest.json')
    assert ft['tokenizer']['name']=='pecab' and ft['tokenizer']['version']=='1.0.8'
    assert set(ft['scope']['document_version_ids'])==set(fixture['public_scope_document_ids'])
    write(A/'artifacts/export-rebinding.json',grant)
    write(A/'artifacts/selected-main.json',active)
    rev=read(C/'candidate.json')['revisions'][-1]
    transport=rev['files'][0]['frozen_path']
    m=read(A/'실험/manifest.json')
    runner=Path(__file__).with_name('run_probe.py')
    m['design']['code_isolation']['candidates']=[{
        'candidate_id':'structure-main','experiment_id':m['experiment_id'],'arm_id':'structure-main','run_ids':['run-001'],
        'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),
        'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],
        'runner_path':str(runner.relative_to(R)),'runner_sha256':sha(runner)}]
    m['dataset']['sha256']=sha(A/'product-cases.json')
    old=read(PREVIOUS)
    paths += [manifest_path,A/'PLAN.md',A/'product-cases.json',A/'artifacts/export-rebinding.json',
              A/'artifacts/selected-main.json',policy,C/'candidate.json',R/transport,
              R/'08_DEPLOYMENT/CONFIG/legal-source-export.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',
              R/'02_BACKEND/lawrag/research/openrouter_legal_adapter.py']
    paths += list(Path(__file__).parent.glob('*.py'))
    paths += [gen/name for name in ('manifest.json','navigation/manifest.json','fulltext/manifest.json')]
    paths += [R/name for name in old['historical_paths'].values()]
    design={'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'code_root':release['code_root'],'generation':release['data_path'],
        'profile_path':str((code/'00_SYSTEM/LEGAL_AGENT/profile-tools-v5.json').relative_to(R)),
        'release_binding':active,'release_manifest_path':active['manifest_path'],
        'transport_path':transport,'scope_authorization':read(policy)['authorization'],
        'export_authorization':grant,'design':m['design'],'runs':m['runs'],
        'file_hashes':{str(p.relative_to(R)):sha(p) for p in paths},
        'grader_only_hashes':{str((A/'gold-cases.json').relative_to(R)):sha(A/'gold-cases.json')},
        'historical_paths':old['historical_paths'],'workers':3,'model':'qwen/qwen3.8-27b',
        'configs':{'structure-main':{'model':'qwen/qwen3.8-27b','thinking_level':'none'}},
        'max_physical_calls':196,'product_gold_visible':False,'product_code_changed':False,
        'pipeline_entrypoint':'Selected frozen semantic_runtime.pipeline.Pipeline.run; real coordinator and synchronous publication',
        'experimental_profile_overrides':{'model_binding':'Qwen3.8 Parasail FP8', 'wall_seconds':300,
                                         'max_schema_repairs':0,'max_transport_retries':0},
        'mutable_main_pointers_used':False}
    write(A/'artifacts/frozen-design.json',design)
    m['llm_policy']['experiment_override']={'schema_version':'user-authorized-openrouter-product-v2',
        'policy_path':str(policy.relative_to(R)),'policy_sha256':sha(policy),
        'frozen_design_path':str((A/'artifacts/frozen-design.json').relative_to(R)),
        'frozen_design_sha256':sha(A/'artifacts/frozen-design.json')}
    write(A/'실험/manifest.json',m)
    print('Frozen',len(paths),'files; exact selected MAIN generation30; public145; no model calls')

if __name__=='__main__':
    main()
