"""Integrate only verified changed files; refuse unrelated worktree changes."""
from common import *
import shutil
f=read(DES/'freeze.json');C=ROOT/f['code_root']
before=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1085-compact-agent-input-sql/artifacts/design/working-before.json')
result=read(RUN/'fsc-hard-005/result.json');audit=read(RUN/'fsc-hard-005/audit.json')
assert result.get('http_status')==200 and not result.get('fatal'),result
assert audit['span_checks'] and all(x['exact_original_match'] and x['within_scope'] for x in audit['span_checks'])
assert not audit['unmapped_final']
assert '127 passed' in (ART/'run-001/contracts-final.log').read_text()
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(DES/'live-freeze.json')['pointer_sha256']
changes={n:h for n,h in f['files'].items() if h!=before.get(n)}
for n,h in changes.items():
 assert sha(C/n)==h,n
 if n in before:assert sha(ROOT/n)==before[n],n
 else:assert not (ROOT/n).exists(),n
receipt={'scope':'working development code only; selected MAIN105/GENOS unchanged','candidate':f['binding'],'files':[],'active_pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')}
for n,h in changes.items():
 p=ROOT/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(C/n,p)
 assert sha(p)==h
 receipt['files'].append({'path':n,'before':before.get(n),'after':h})
put(ART/'integration.json',receipt)
print('Integrated',len(changes),'files; selected MAIN105 unchanged')
