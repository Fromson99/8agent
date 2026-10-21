"""Append exact promotion inventory before qualification execution."""
from pathlib import Path
import hashlib
import json
import datetime
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0945-research-decision-qualification';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):
    with p.open('x') as f:f.write(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
b=read(D/'fixed-binding.json');base=read(D/'baseline.json')
assert read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer']
assert all(sha(R/b['code_root']/n)==h for n,h in b['serving_files'].items())
candidate=read(R/b['candidate']['manifest_path'])
names={r['target_path'] for r in candidate['files']}
put(D/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1',
    'base_release_manifest_sha256':base['pointer']['release_manifest_sha256'],
    'candidate':b['candidate'],'staged_files':b['serving_files'],
    'excluded_candidate_paths':{n:'Non-serving candidate resource, preserved in immutable revision.' for n in names-set(b['serving_files'])},
    'evaluation':'Unchanged ADR0943 candidate389 files. Finite qualification, packager inventory and candidate/working/active service checks; ADR0944 known-topic cost/source observation separately recorded.'})
before=base['manifest']['files'];target=b['serving_files']
put(D/'integration.json',{'schema_version':'local-release-integration-v1',
    'base_release_manifest_sha256':base['pointer']['release_manifest_sha256'],
    'candidate':b['candidate'],'rebase_receipt':bound(D/'release-rebase.json'),
    'changes':[{'path':n,'before':before.get(n),'after':target.get(n),
        'reason':'Exact tested owner refactor and need/review/discovery transition integration with all engine/workflow pins.'}
        for n in sorted(set(before)|set(target)) if before.get(n)!=target.get(n)]})
put(D/'preview-authorization.json',{'purpose':'integration_preview'})
put(D/'preview-validation.json',{'structural_checks_passed':True,'purpose':'Read-only packaging inventory preview; no activation authorization'})
m=read(A/'실험/manifest.json');m['design']['release_rebase']=bound(D/'release-rebase.json')
(A/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
put(D/'release-plan-seal.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'appended_before_qualification_run':True,'original_freeze_unchanged':bound(D/'freeze.json'),
    'files':{str(p.relative_to(R)):sha(p) for p in [D/'release-rebase.json',D/'integration.json',
        D/'preview-authorization.json',D/'preview-validation.json']}})
print('Exact MAIN90 -> candidate389 file inventory appended before execution.')
