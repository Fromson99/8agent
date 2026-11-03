from common import *
p=ART/'validation-first-format.txt'
if not p.exists():p.write_text('Post-run metadata validation failed before completion: artifact manifest schema_version must be adr-artifacts-v1; adr_id must be ADR-1310. Execution results unchanged. Corrected metadata only before status transition.\n')
files=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Offline latency diagnostic, original record or preserved observer revision','contains_raw_prompts_and_outputs':('canonical' in p.parts or p.name in ('response.json.gz','request.json','answer.txt','runtime.tar.gz'))} for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json' and not (p.parent.name=='.observer-versions' and p.name.startswith('manifest-'))]
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1310','files':files})
print('Artifact files',len(files))
