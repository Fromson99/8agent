from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[3];T=Path(__file__).parent;old=T.parent/'adr_1225'
s=(old/'common.py').read_text().replace('ADR-1225-cumulative-authoring-main','ADR-1227-source-first-authoring-semantics').replace('20261029-cumulative-authoring-main122','20261029-source-first-authoring').replace('cumulative-authoring-20261029-r1','source-first-authoring-20261029-r1').replace('adr_1225/authoring-contract','adr_1227/source-first')
s=s.replace("def read(p):return json.loads(Path(p).read_text())","def read(p):\n p=Path(p)\n if p==DES/'freeze.json':p=DES/'freeze-current.json'\n return json.loads(p.read_text())")
(T/'common.py').write_text(s)
s=(old/'consumer.py').read_text().replace("len(f['files'])==487","len(f['files'])==489").replace("active['generation']==122","active['generation']==123").replace('main122=','main123=').replace("'configuration'])","'configuration','recorded_fields','authoring_semantics'])")
needle="checks['canonical_profile_schema_unchanged']="
pos=s.index(needle)
s=s[:pos]+"""roles=importlib.import_module(package+'.ontology_work.recorded_fields')
role_schema=roles.request_schema(dynamic,r)
fields=role_schema['properties']['observations']['items']['properties']
checks['recorded_roles_nullable']=all(fields[k]['anyOf'][0]=={'type':'null'} for k in ('recorded_reason','recorded_purpose'))
checks['old_role_output_absent']=not {'reason','purpose'} & fields.keys()
semantics=importlib.import_module(package+'.ontology_work.authoring_semantics')
checks['source_only_stage_selected']='SOURCE_ANALYSIS' in (C/'02_BACKEND/semantic_runtime/ontology_work/domain_workflow.py').read_text()
checks['no_role_word_whitelist']=not hasattr(roles,'LABELS')
"""+s[pos:]
(T/'consumer.py').write_text(s)
ART=ROOT/'04_EXPERIMENTS/ADR/ADR-1227-source-first-authoring-semantics/artifacts'
(ART/'schema-sizes.json').write_text((ROOT/'04_EXPERIMENTS/ADR/ADR-1225-cumulative-authoring-main/artifacts/schema-sizes.json').read_text())
print('Consumers prepared; no calls')
