from common import *
allfiles=[p for p in ART.rglob('*') if p.is_file() and not p.is_symlink() and '.observer-versions' not in p.parts and p.name not in ('manifest.json','runtime-files-sha256.json.gz')]
rows=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(allfiles)]
p=ART/'runtime-files-sha256.json.gz'
if not p.exists():write_raw_json(p,rows)
else:assert read(p)==rows
excluded={'runtime','checkout','selected-entry-runtime'}
paths={p for p in allfiles if not any(n in excluded for n in p.relative_to(ART).parts)}
paths.add(ART/'runtime-files-sha256.json.gz');paths.update(Path(__file__).parent.glob('*.py'))
H=ROOT/read(ART/'mail-package.json')['handoff'];paths.update(p for p in H.iterdir() if p.is_file())
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1410','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Actual guided answer trials, preserved failures, selected MAIN151, exact delivery and sent-mail verification','contains_raw_prompts_and_outputs':('model' in p.parts or p.name=='actual-input.json.gz')} for p in sorted(paths)]})
print('Archived files',len(rows),'manifest entries',len(paths))
