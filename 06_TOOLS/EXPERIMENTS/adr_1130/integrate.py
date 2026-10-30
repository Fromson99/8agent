from common import *
import sys,ast
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
S=CAND/'snapshot';P=S/'02_BACKEND/semantic_runtime/legal_agent'
p=P/'ontology_context.py';s=p.read_text();old="{'mode', 'snapshot', 'snapshot_sha256', 'semantic_binding'}):";new="{'mode', 'snapshot', 'snapshot_sha256', 'semantic_binding'}, {'mode', 'snapshot', 'snapshot_sha256', 'scenario_package'}):";assert old in s;s=s.replace(old,new)
needle='    identities = set()';s=s.replace(needle,"    if 'scenario_package' in value:\n        from .ontology_scenarios import verify_package\n        verify_package(value['scenario_package'])\n"+needle,1);p.write_text(s)
p=P/'ontology_assessment.py';s=p.read_text();needle='        payload = ontology_input.payload(payload)';replacement=needle+"\n        package=settings.get('scenario_package')\n        if package and package['bundle_id']==bundle['bundle_id']:\n            from .ontology_scenarios import bind_current\n            payload['scenario_catalog']=bind_current(package,fragments)";assert needle in s;s=s.replace(needle,replacement,1);p.write_text(s)
p=P/'completion_execution.py';s=p.read_text();needle="            assessment = parts['ASSESS']['payload']";s=s.replace(needle,needle+"\n            if assessment.get('scenario_selection'):\n                from .ontology_scenarios import verify_selected_text\n                verify_selected_text(assessment)\n                rich=False  # Selected precompiled text is published without another model rewrite.",1)
needle='        ontology_payload=ontology_assessment.project(self.s.sources,investigation,sources,options)';s=s.replace(needle,needle+"\n        from . import ontology_scenario_runtime\n        scenario_catalog=ontology_scenario_runtime.catalog_from(ontology_payload)\n        if scenario_catalog is not None:\n            return ontology_scenario_runtime.assess(self,scenario_catalog,sources,options,self.issues,utterance,selection,judgment_context)",1);p.write_text(s)
comp=read(ART/'composition.json')
for name in ('ontology_scenarios.py','ontology_scenario_runtime.py'):
 n='02_BACKEND/semantic_runtime/legal_agent/'+name;ac.register_file(CAND,n,upstream_state='absent');comp['added_product'].append(n)
for name in ('ontology_context.py','ontology_assessment.py','completion_execution.py'):
 n='02_BACKEND/semantic_runtime/legal_agent/'+name
 if n not in comp['changed_product']:comp['changed_product'].append(n)
put(ART/'composition.json',comp)
parent=read(ART/'parent.json');snapshot=read(ROOT/parent['snapshot_path']);r=read(ART/'recipe.json');bundle=next(b for b in snapshot['bundles'] if b['concept']['label']==r['bundle_id']);r['bundle_id']=bundle['bundle_id'];put(ART/'recipe.json',r)
for n in P.glob('ontology_scenar*.py'):ast.parse(n.read_text())
print('Integrated scenario package into existing READ/ASSESS/COMPOSE; active release unchanged')
