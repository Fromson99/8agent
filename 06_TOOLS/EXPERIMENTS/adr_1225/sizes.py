from common import *
f=read(DES/'freeze.json');C=ROOT/f['code_root'];sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent.wire_schema import project_request,REF_PATTERN,PORTABLE_REF_PATTERN
from semantic_runtime.ontology_work.profile_schema import observation_schema,accumulation_schema
profile=read(C/'00_SYSTEM/ONTOLOGY_PROFILES/domain-profile-v1.json');rows={}
for name,maker in [('NORMALIZE',observation_schema),('ACCUMULATE',accumulation_schema)]:
 s=maker(profile);_,r=project_request({'response_format':{'json_schema':{'schema':s}}});rows[name]={'original_chars':r['validation_schema_chars'],'wire_chars':r['wire_schema_chars'],'projection':r}
put(ART/'schema-sizes.json',rows);print(rows)
