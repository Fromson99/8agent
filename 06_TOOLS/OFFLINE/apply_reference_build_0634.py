"""Local reviewed-candidate application receipt; not a GENOS entrypoint."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[2]
AUDIT=ROOT/'09_ARTIFACTS/AUDITS/genos-reference-build-20261003'
def main():
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
    candidate=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0634/compact'
    value=json.loads((candidate/'candidate.json').read_text())
    decision=json.loads((ROOT/'04_EXPERIMENTS/ADR/ADR-0634-genos-reference-build-repair/실험/manifest.json').read_text())
    assert decision['decision_eligible'] and not decision['in_sample'] and decision['results']['status']=='complete' and decision['results']['decision']['accepted']
    if AUDIT.exists():raise ValueError('application receipt already exists')
    rows=[]
    for item in value['files']:
        name=item['target_path'];current=ROOT/name;frozen=candidate/'revisions/rev-001/snapshot'/name
        previous=sha(current) if current.exists() else None
        expected=item.get('upstream_sha256') if item['upstream_state']=='present' else None
        assert previous==expected,('upstream drift',name)
        if sha(frozen)!=previous:rows.append({'path':name,'before':previous,'after':sha(frozen)})
    AUDIT.mkdir(parents=True)
    for row in rows:
        name=row['path'];dest=ROOT/name
        if dest.exists():
            backup=AUDIT/'before'/name;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(dest,backup)
        shutil.copyfile(candidate/'revisions/rev-001/snapshot'/name,dest)
    write(AUDIT/'APPLICATION.json',{'experiment':'ADR-0634-experiment-v1/compact','revision_sha256':value['revisions'][0]['revision_sha256'],'files':rows,'activated':False})
    changed={r['path'] for r in rows};manifests=[]
    added={'02_BACKEND/semantic_runtime/reference_build.py','02_BACKEND/semantic_runtime/navigation_build.py'}
    for path in sorted((ROOT/'02_BACKEND/ENGINES').rglob('*.json')):
        m=json.loads(path.read_text());files=m.get('files',{})
        if not isinstance(files,dict) or not changed.intersection(files):continue
        old=sha(path);backup=AUDIT/'before'/path.relative_to(ROOT);backup.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,backup)
        for name in changed.intersection(files):files[name]=sha(ROOT/name)
        if '02_BACKEND/semantic_runtime/term_index.py' in files:
            for name in added:files[name]=sha(ROOT/name)
        write(path,m);manifests.append({'engine':m['id'],'manifest':str(path.relative_to(ROOT)),'old':old,'new':sha(path)})
    path=ROOT/'00_SYSTEM/PIPELINE.json';backup=AUDIT/'before/00_SYSTEM/PIPELINE.json';backup.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,backup)
    pipe=json.loads(path.read_text())
    for row in manifests:
        entry=pipe['engines'].get(row['engine'])
        if entry:
            assert entry['manifest']==row['manifest'];entry['sha256']=row['new']
    write(path,pipe)
    write(AUDIT/'ENGINE_PINS.json',{'applied':True,'changed_code':sorted(changed),'engine_manifests':manifests,'pipeline_sha256':sha(path),'unrelated_pins_preserved':True})
    print(json.dumps({'changed_files':len(rows),'engine_manifests':len(manifests),'audit':str(AUDIT)}))
if __name__=='__main__':main()
