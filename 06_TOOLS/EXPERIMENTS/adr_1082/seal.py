"""Bind all preserved artifacts after report/archive, before final ADR validation."""
from common import *
from datetime import datetime,timezone
assert read(RUN/'result.json')['status']=='complete'
put(ART/'analysis-tools.json',{'role':'Post-selection audit, reporting and preservation; product design unchanged',
    'files':{str(p.relative_to(ROOT)):sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}})
manifest=ART/'manifest.json'
put(manifest,{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1082','created_at':read(ADR/'실험/manifest.json')['reservation']['created_at'],
    'files':[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),
       'description':'Exact frozen inputs, actual service output, offline source audit or verified lossless original records',
       'contains_raw_prompts_and_outputs':p.suffix=='.gz' or p.name in ('response.json','request.json')}
       for p in sorted(ART.rglob('*')) if p.is_file() and p!=manifest and not p.name.endswith(('-wal','-shm'))]})
print('Artifact hashes sealed; complete reservation only after validating final structure')
