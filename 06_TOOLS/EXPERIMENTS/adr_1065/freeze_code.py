"""Freeze tested mutable snapshots into new immutable per-arm revisions."""
from pathlib import Path
import json,hashlib,sys,shutil
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1065-ontology-task-local-navigation';ART=ADR/'artifacts'
CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1065/task-local-r1'
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rel(p):return str(p.relative_to(ROOT))


def main():
    tested=read(ART/'release-check-summary.json')
    assert tested['validation_status']==0 and not tested['new_failures'] and not tested['production_import_leaks'] and not tested['candidate_changed_during_tests']
    assert tested['files']=={str(p.relative_to(CAND/'snapshot')):sha(p) for p in (CAND/'snapshot').rglob('*') if p.is_file()}
    m=read(ADR/'실험/manifest.json')
    policy=read(CAND/'snapshot/00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')
    if policy.get('provider_failover',{}).get('scope')!=m['experiment_id']:
        raise ValueError('provider failover scope differs from current experiment before code freeze')
    sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as c
    prior_revisions={}
    prior_revisions['A2']=[r['revision_id'] for r in read(CAND/'candidate.json')['revisions']]
    # Appends an immutable revision. Neither earlier revisions nor their files
    # are edited, even when a pre-call freeze was invalidated.
    c.freeze(CAND);assert not c.validate(CAND)
    v=read(CAND/'candidate.json');rev=v['revisions'][-1]
    bindings=[]
    for arm,name in [('A0','task-local-a0-r1'),('A1','task-local-a1-r1'),('A2','task-local-r1')]:
        directory=CAND.parent/name
        if arm!='A2':
            rows=v['files'];targets={r['target_path']:r for r in rows}
            manifest_path=directory/'candidate.json'
            if manifest_path.is_file():
                current=read(manifest_path)
                assert current['experiment_id']==m['experiment_id'] and current['arm_id']==arm and current['run_ids']==['run-001']
                registered={r['target_path']:r for r in current['files']}
                assert set(registered)<=set(targets),'existing arm snapshot has files outside current tested candidate'
                prior_revisions[arm]=[r['revision_id'] for r in current['revisions']]
                for target,row in registered.items():
                    assert all(row.get(k)==targets[target].get(k) for k in
                               ('upstream_state','upstream_path','upstream_sha256')),'arm upstream provenance differs'
            else:
                assert not directory.exists(),'partial candidate directory; inspect before retry'
                c.snapshot(ADR,name,[r['target_path'] for r in rows if r['upstream_state']=='present'],
                           experiment_id=m['experiment_id'],arm_id=arm,run_ids=['run-001'])
                registered={r['target_path']:r for r in read(manifest_path)['files']}
                prior_revisions[arm]=[]
            for row in rows:
                target=directory/'snapshot'/row['target_path'];target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(CAND/'snapshot'/row['target_path'],target)
                if row['target_path'] not in registered:
                    c.register_file(directory,row['target_path'],upstream_state=row['upstream_state'])
            c.refresh(directory);c.freeze(directory)
        assert not c.validate(directory)
        manifest=read(directory/'candidate.json');revision=manifest['revisions'][-1]
        assert {r['target_path']:r['snapshot_sha256'] for r in manifest['files']}==tested['files']
        assert [r['revision_id'] for r in manifest['revisions'][:-1]]==prior_revisions[arm]
        bindings.append({'candidate_id':name,'arm_id':arm,'experiment_id':m['experiment_id'],'run_ids':['run-001'],
            'manifest_path':rel(directory/'candidate.json'),'manifest_sha256':sha(directory/'candidate.json'),
            'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256'],
            'runner_path':rel(Path(__file__).parent/'run_matrix.py'),'runner_sha256':sha(Path(__file__).parent/'run_matrix.py')})
    m['design']['code_isolation']['candidates']=bindings
    save(ADR/'실험/manifest.json',m)
    save(ART/'tested-freeze.json',{'candidate':rel(CAND),'revision':rev['revision_id'],'revision_sha256':rev['revision_sha256'],
        'preserved_prior_revisions':prior_revisions,'files':len(tested['files']),
        'test_summary':rel(ART/'release-check-summary.json'),'sha256':sha(ART/'release-check-summary.json'),
        'exact_tested_files':True,'external_model_calls':0})
    print('FROZEN',rev['revision_id'],len(tested['files']),'files;',tested['passed'],'tests passed')

if __name__=='__main__':main()
