from common import *
paths={p for p in ART.rglob('*') if p.is_file() and '.observer-versions' not in p.parts and p!=ART/'manifest.json'}
paths.update(Path(__file__).parent.glob('*.py'))
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1400','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen source or actual provider/API/journal/audit evidence','contains_raw_prompts_and_outputs':('raw' in p.parts or 'canonical' in p.parts)} for p in sorted(paths)]})
print('Sealed',len(paths),'artifacts')
