"""Compose only frozen, explicitly selected bytes and register each live arm.

No model, corpus load, performance measurement or production mutation.
"""
from pathlib import Path
import hashlib
import json
import shutil
import sys

from common import ROOT, ADR, ART, read, sha, exact_write
from stage_candidate import stage

sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as candidate


def require(value,message):
    if not value:raise ValueError(message)


def file_map(root):
    result={}
    for path in root.rglob('*'):
        require(not path.is_symlink(),'symlink in candidate')
        if path.is_file():result[str(path.relative_to(root))]=sha(path)
    return result


def main():
    plan_path=ART/'implementation-plan.json';plan=read(plan_path)
    manifest=read(ADR/'실험/manifest.json')
    require(manifest['reservation']['status']=='in_progress','inactive ADR')
    require(manifest['design']['criteria_record']['sha256']==sha(plan_path),'criteria drift')
    parent=manifest['lineage']['parents'][0]
    require(parent['experiment_id']=='ADR-1072-experiment-v1' and parent['arm_id']=='B2','wrong parent')
    require(sha(ROOT/parent['manifest_path'])==parent['manifest_sha256'],'parent changed')
    require(read(ROOT/parent['manifest_path'])['results']['by_arm']['B2']['status']=='complete','parent incomplete')
    source=ROOT/plan['base_code_root']; source_candidate=source.parent.parent.parent
    base=read(source_candidate/'candidate.json')
    revision=next(r for r in base['revisions'] if r['revision_id']==source.parent.name)
    require(candidate.canonical_sha256({k:v for k,v in revision.items() if k!='revision_sha256'})==plan['base_revision_sha256'],'base revision changed')
    expected={str((ROOT/r['frozen_path']).relative_to(source)):r['snapshot_sha256'] for r in revision['files']}
    require(file_map(source)==expected,'base file inventory drift')
    patch_root=ROOT/plan['source_patches']['root']
    patches=plan['source_patches']['files']
    for p,h in patches.items():require(sha(patch_root/p)==h,'patch changed '+p)
    for p,h in plan['preservation'].items():require(sha(ROOT/p)==h,'preserved source changed')
    bindings=[]; common_files=None
    for arm in ('A0','A1','A2'):
        name='merged-'+arm.lower()+'-r1';dest=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1074'/name
        require(not dest.exists(),'candidate already exists; no overwrite')
        names=set(expected)|set(patches)
        present=sorted(p for p in names if (ROOT/p).is_file())
        created=candidate.snapshot(ADR,name,present,experiment_id=manifest['experiment_id'],arm_id=arm,run_ids=['run-001'])
        require(created==dest,'unexpected candidate location')
        for relative in sorted(names):
            path=dest/'snapshot'/relative;path.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2((patch_root if relative in patches else source)/relative,path)
        stage(name,True)
        current=read(dest/'candidate.json');frozen=current['revisions'][-1]
        code=dest/'revisions'/frozen['revision_id']/'snapshot';actual=file_map(code)
        require(common_files is None or actual==common_files,'arms differ in code')
        common_files=actual
        for relative in ('02_BACKEND/semantic_runtime/legal_agent/definition_entry.py','02_BACKEND/semantic_runtime/search_selection.py'):
            require(actual[relative]==expected[relative],'SQL implementation changed')
        bindings.append({'candidate_id':name,'experiment_id':manifest['experiment_id'],'arm_id':arm,'run_ids':['run-001'],
            'manifest_path':str((dest/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(dest/'candidate.json'),
            'revision_id':frozen['revision_id'],'revision_sha256':frozen['revision_sha256'],
            'runner_path':str((Path(__file__).parent/'run_matrix.py').relative_to(ROOT)),
            'runner_sha256':sha(Path(__file__).parent/'run_matrix.py')})
    deltas=[{'path':p,'base_sha256':expected.get(p),'new_sha256':h,'source':'1067-selected-fix' if p in patches else 'pin-or-policy'}
        for p,h in sorted(common_files.items()) if h!=expected.get(p)]
    exact_write(ART/'candidate-bindings.json',{'schema_version':'adr1074-candidate-bindings-v1','status':'COMPLETE',
        'base':plan['base_code_root'],'base_revision_sha256':plan['base_revision_sha256'],'arm_code_bindings':bindings,
        'all_file_maps_identical':True,'file_count':len(common_files),'file_map_sha256':candidate.canonical_sha256(common_files),
        'deltas':deltas,'sql_two_files_exact_1072':True,'production_changed':False,'model_calls':0,'real_corpus_loads':0})
    manifest['design']['code_isolation']['candidates']=bindings
    (ADR/'실험/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'FROZEN_CANDIDATES','files':len(common_files),'arms':bindings,'deltas':len(deltas)},ensure_ascii=False))


if __name__=='__main__':main()
