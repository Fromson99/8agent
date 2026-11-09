"""Artifact manifest under the summary size limit: top-level evidence listed individually,
every per-cell raw/canonical/runtime file hashed in one gzip inventory (listed and hashed here)."""
from common import *
import sys
adr_id=sys.argv[1] if len(sys.argv)>1 else 'ADR-1462'
bulk=('public-live','public-ready','transport','tree-swap-backup')
paths=sorted(p for p in ART.rglob('*') if p.is_file() and '.observer-versions' not in p.parts and p.name not in ('manifest.json','artifact-inventory.json.gz'))
inner=[p for p in paths if p.relative_to(ART).parts[0] in bulk];top=[p for p in paths if p not in inner]
inv_path=ART/'artifact-inventory.json.gz'
if inv_path.exists():inv_path.unlink()
write_raw_json(inv_path,{'schema_version':'adr-artifact-inventory-v1','adr_id':adr_id,'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size} for p in inner]})
tools=sorted(Path(__file__).parent.glob('*.py'))
entry=lambda p,d:{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':d,'contains_raw_prompts_and_outputs':p.suffix=='.gz'}
files=[entry(p,'Execution, review and audit evidence') for p in top]+[entry(inv_path,'Hash inventory of per-cell raw/canonical/runtime files ('+str(len(inner))+')')]+[entry(p,'Experiment runner/post-processing source') for p in tools]
m=ART/'manifest.json'
if m.exists():m.unlink()
m.write_text(json.dumps({'schema_version':'adr-artifacts-v1','adr_id':adr_id,'files':files},ensure_ascii=False,indent=1)+'\n')
print(adr_id,'manifest entries',len(files),'inventory',len(inner))
