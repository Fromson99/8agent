"""Stage the already implemented work and synthetic fixture before freeze/calls."""
from common import *
import shutil
from dataset import build
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==98
base=read(ROOT/pointer['manifest_path']);basecode=ROOT/base['code_root']
paths=set(base['files'])|{'02_BACKEND/semantic_runtime/legal_agent/structure_selection.py'}
allowed=set()
for name in ['natural-language-routing','structured-selection']:
    audit=read(ROOT/f'09_ARTIFACTS/AUDITS/20261021-{name}/CHANGES.json');allowed.update(audit['runtime']);allowed.update(audit['engine_manifests'])
allowed.add('00_SYSTEM/PIPELINE.json')
changed=sorted(n for n in paths if base['files'].get(n)!=sha(ROOT/n))
assert set(changed)<=allowed,set(changed)-allowed
C=ART/'code-candidate';C.mkdir(exist_ok=False)
for n in sorted(paths):
    dst=C/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,dst)
assert all(sha(basecode/n)==h for n,h in base['files'].items())
save(ART/'stage.json',{'base_pointer':pointer,'roots':{'baseline':str(basecode.relative_to(ROOT)),'candidate':str(C.relative_to(ROOT))},'files':{'baseline':base['files'],'candidate':{n:sha(C/n) for n in sorted(paths)}},'working_baseline':{n:sha(ROOT/n) for n in sorted(paths)}})
save(ART/'integration-delta.json',{'against_main98':changed,'runtime_changes':[n for n in changed if n.startswith('02_BACKEND/semantic_runtime/')],'preexisting_work':'Existing authorized natural-language routing cleanup and structured set feature, implemented before this qualification. No unrelated serving-code drift.'})
build()
print('Staged',len(paths),'files;',len(changed),'changes;',len(read(ART/'cases.json')),'fresh cases; zero model calls')
