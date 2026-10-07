"""Seal Qwen scope, policy, code, source, criteria and scoring before first send."""
import hashlib,json,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0492-source-article-read-scope'
CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0492/repaired'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
    target=ADR/'artifacts/frozen-design.json'
    if target.exists():raise RuntimeError('Already frozen')
    product=read(ADR/'product-cases.json');m=read(ADR/'실험/manifest.json')
    gen=ROOT/product['generation'];source=read(gen/'manifest.json')
    origin=ROOT/'01_DATA/PROJECTIONS/document-origins/term-source-adca5fbe3650f90fb372.json'
    projection=read(origin);auth_path=ROOT/'08_DEPLOYMENT/CONFIG/legal-source-export.json';old_auth=read(auth_path)
    policy_path=ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json';policy=read(policy_path)
    scope=product['public_scope_document_ids']
    assert set(scope)<=set(old_auth['bindings'][0]['document_version_ids'])
    assert old_auth['enabled'] and projection['store_sha256']==source['store_sha256']
    receipts=[]
    with sqlite3.connect("file:"+str(gen/"store.sqlite")+"?mode=ro",uri=True) as db:
        artifact_hashes=dict(db.execute("SELECT document_id,source_artifact_sha256 FROM document"))
    for did in scope:
        row=projection['documents'][did];raw=ROOT/'01_DATA/RAW'/row['raw_relative_path']
        assert row['status']=='verified' and row['raw_relative_path'].split('/')[0] in ('law','krx','fsc','fss','kofia')
        raw_sha=sha(raw)
        assert raw_sha[:16]==did and artifact_hashes[did]==row['source_artifact_sha256']
        receipts.append({'document_id':did,**row,'raw_sha256':raw_sha,'verification':'RAW hash prefix=document version ID; structured artifact hash=stored document provenance'})
    assert sha(gen/'store.sqlite')==source['store_sha256']
    authorization={'schema_version':'request-scoped-public-experiment-rebinding-v1','source_store_sha256':source['store_sha256'],
        'generation_id':source['generation_id'],'scope_document_ids':scope,'destination':policy['endpoint'],'model':policy['model'],
        'basis':'Existing public-law source authorization plus subsequent user-wide experimental model policy and current CM test request.',
        'source_authorization_sha256':sha(auth_path),'policy_sha256':sha(policy_path),'projection_sha256':sha(origin),
        'immutable_export_flags_changed':False,'source_manifest_export_allowed':source['export_allowed'],
        'public_questions_only':True,'private_documents_allowed':False,'document_provenance':receipts}
    write(ADR/'artifacts/export-rebinding.json',authorization)
    runner=ROOT/'06_TOOLS/EXPERIMENTS/adr_0492/run_probe.py';rev=read(CAND/'candidate.json')['revisions'][0]
    paths=[ADR/'PLAN.md',ADR/'product-cases.json',ADR/'gold-cases.json',CAND/'candidate.json',gen/'manifest.json',gen/'navigation/manifest.json',gen/'fulltext/manifest.json',origin,auth_path,policy_path,
        ROOT/'00_SYSTEM/PIPELINE.json',ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',runner,
        ROOT/'06_TOOLS/EXPERIMENTS/adr_0492/score.py',ROOT/'06_TOOLS/EXPERIMENTS/adr_0492/freeze.py',ROOT/'06_TOOLS/EXPERIMENTS/adr_0473/build_ledger.py']
    paths += [ROOT/'02_BACKEND/lawrag/research/candidates/adr_0488/source-tiers-v4/candidate.json',ROOT/'06_TOOLS/EXPERIMENTS/adr_0492/test_workflow.py']
    parent=ROOT/'04_EXPERIMENTS/ADR/ADR-0491-source-tool-error-repair-cm018'
    paths += [parent/'실험/manifest.json'] + sorted(p for p in (parent/'artifacts/run-001').rglob('*') if p.is_file() and 'judge' not in p.parts)
    paths+=sorted(p for p in (ADR/'artifacts/historical').rglob('*') if p.is_file())
    paths+=sorted(p for p in (ROOT/'02_BACKEND/lawrag').rglob('*.py') if 'research/candidates' not in str(p))
    paths+=sorted((ROOT/'00_SYSTEM/LEGAL_AGENT').glob('*.json'))
    paths+=sorted((ROOT/'02_BACKEND/ENGINES').rglob('*.json'))
    runtime=ADR/'artifacts/sealed-runtime'
    paths=[p for p in paths if not str(p.relative_to(ROOT)).startswith('02_BACKEND/lawrag/') or (runtime/p.relative_to(ROOT)).is_file() or '/candidates/' in str(p)]
    paths=[runtime/p.relative_to(ROOT) if (runtime/p.relative_to(ROOT)).is_file() else p for p in paths]
    paths+=sorted(p for p in runtime.rglob('*') if p.is_file())
    design={'runtime_root':str(runtime.relative_to(ROOT)),'arms':['baseline','repaired'],'model':policy['model'],'order':'fresh CM018 once; inherited ADR0491/run-001 control',
        'selection_rule':m['runs'][0]['selection_rule'],'criteria':m['design']['success_criteria'],'design':m['design'],'runs':m['runs'],
        'export_authorization':authorization,'file_hashes':{str(p.relative_to(ROOT)):sha(p) for p in paths},
        'known_limitations':['CM in-sample 3 cases; no independent law version verification','Qwen external FP8 proxy, not GENOS execution',
            'Question trailing context remains original and is split into separate question pieces by current shared runtime',
            'One fresh product run; inherited control; answer-only and source-only Qwen judges separately; no human calibration', 'Both inherited control and candidate validate scoped grants; original v4 mismatch was repaired in ADR0489',
            'Controller deadline excludes initial resource loading; record end-to-end wall separately']}
    write(target,design)
    m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{
        'candidate_id':'repaired','experiment_id':m['experiment_id'],'arm_id':'repaired','run_ids':['run-001'],
        'manifest_path':str((CAND/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(CAND/'candidate.json'),
        'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(ROOT)),'runner_sha256':sha(runner)}])
    write(ADR/'실험/manifest.json',m)
    print('Frozen: Qwen, one fresh CM018 and inherited control, public',len(scope),'documents; no calls')
if __name__=='__main__':main()
