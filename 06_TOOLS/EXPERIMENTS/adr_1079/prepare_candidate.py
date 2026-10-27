"""Register an exact copy of completed 1077 B1, with zero product changes."""
from pathlib import Path
import json
import shutil
import sys
from common import ROOT, ADR, ART, read, sha, exact_write
sys.path.insert(0, str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as candidate


def main():
    plan=read(ART/'implementation-plan.json'); manifest=read(ADR/'실험/manifest.json')
    assert manifest['reservation']['status']=='in_progress'
    assert manifest['design']['criteria_record']['sha256']==sha(ART/'implementation-plan.json')
    parent=manifest['lineage']['parents'][0]
    assert parent['experiment_id']=='ADR-1077-experiment-v1' and parent['arm_id']=='B1'
    assert sha(ROOT/parent['manifest_path'])==parent['manifest_sha256']
    assert read(ROOT/parent['manifest_path'])['results']['by_arm']['B1']['status']=='complete'
    source=ROOT/plan['base_code_root']; base_path=source.parent.parent.parent/'candidate.json'
    assert sha(base_path)==plan['base_candidate_manifest_sha256']
    base=read(base_path); rev=next(r for r in base['revisions'] if r['revision_id']==source.parent.name)
    assert rev['revision_sha256']==plan['base_revision_sha256']
    expected={str((ROOT/r['frozen_path']).relative_to(source)):r['snapshot_sha256'] for r in rev['files']}
    assert {str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file()}==expected
    name='departure-a2-r1'
    dest=candidate.snapshot(ADR,name,sorted(p for p in expected if (ROOT/p).is_file()),
        experiment_id=manifest['experiment_id'],arm_id='A2',run_ids=['run-001'])
    for relative in expected:
        path=dest/'snapshot'/relative; path.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source/relative,path)
    registered={row['target_path'] for row in read(dest/'candidate.json')['files']}
    for relative in sorted(set(expected)-registered):
        candidate.register_file(dest,relative,upstream_state='absent')
    candidate.refresh(dest); candidate.freeze(dest)
    assert candidate.validate(dest)==[]
    current=read(dest/'candidate.json'); revision=current['revisions'][-1]
    code=dest/'revisions'/revision['revision_id']/'snapshot'
    actual={str(p.relative_to(code)):sha(p) for p in code.rglob('*') if p.is_file()}
    assert actual==expected
    binding={'candidate_id':name,'experiment_id':manifest['experiment_id'],'arm_id':'A2','run_ids':['run-001'],
        'manifest_path':str((dest/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(dest/'candidate.json'),
        'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256'],
        'runner_path':str((Path(__file__).parent/'run_matrix.py').relative_to(ROOT)),
        'runner_sha256':sha(Path(__file__).parent/'run_matrix.py')}
    exact_write(ART/'candidate-bindings.json',{'schema_version':'adr1079-candidate-binding-v1',
        'arm_code_bindings':[binding],'parent_code_files':expected,'product_changed_files':[],
        'parent_exact':True,'files':len(actual),'model_calls':0,'corpus_loads':0})
    manifest['design']['code_isolation']['candidates']=[binding]
    (ADR/'실험/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'candidate':str(code.relative_to(ROOT)),'exact_parent_files':len(actual),'changed':0}))


if __name__=='__main__':main()
