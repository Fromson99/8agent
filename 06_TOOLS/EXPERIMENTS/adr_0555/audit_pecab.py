"""Read-only audit of the maintained deployment surface, not archived experiments."""
import ast, hashlib, importlib.util, json
from pathlib import Path
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0555-pecab-only-catalogue-routing'
spec=importlib.util.spec_from_file_location('current_code_ship',R/'06_TOOLS/COMMANDS/code_ship.py')
ship=importlib.util.module_from_spec(spec);spec.loader.exec_module(ship)
files=ship._files();imports=[];pecab=[]
for p in files:
 if p.suffix!='.py':continue
 tree=ast.parse(p.read_bytes(),filename=str(p))
 for node in ast.walk(tree):
  names=[]
  if isinstance(node,ast.Import):names=[x.name for x in node.names]
  elif isinstance(node,ast.ImportFrom):names=[node.module or '']
  for name in names:
   if name.startswith('kiwipiepy'):imports.append({'path':str(p.relative_to(R)),'line':node.lineno,'module':name})
   if name.startswith('pecab'):pecab.append({'path':str(p.relative_to(R)),'line':node.lineno,'module':name})
requirements={str(p.relative_to(R)):p.read_text() for p in files if p.name.startswith('requirements')}
assert not imports,imports
assert all('kiwipiepy' not in text for text in requirements.values())
assert any('pecab==1.0.8' in text for text in requirements.values())
active=json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
release=json.loads((R/active['manifest_path']).read_text())
generation=R/release['data_path']
# Report actual frozen selection separately; never rewrite or execute old code.
ft=json.loads((generation/'fulltext/manifest.json').read_text())
report={'schema_version':'pecab-maintained-code-audit-v1','python_files':sum(p.suffix=='.py' for p in files),
 'maintained_surface_kiwi_imports':imports,'pecab_imports':pecab,'requirements_pecab_pinned':True,
 'active_local_pointer_unchanged':True,'selected_release_id':active.get('release_id'),
 'selected_generation':str(generation.relative_to(R)),'selected_fulltext_tokenizer':ft['tokenizer'],
 'old_selected_release_usable_under_new_entrypoint':ft.get('schema_version')=='semantic-fulltext-v2' and ft['tokenizer'].get('name')=='pecab',
 'policy':'No Kiwi imports or fallback in maintained code. New service rejects old fulltext before importing a frozen runtime. Historical immutable bytes preserved.',
 'runtime_morphology':'semantic_runtime.term_morph PeCab 1.0.8; fulltext builder/query and term candidate extraction',
 'literal_assets':'navigation occurrence/approved labels/definitions/explicit references are tokenizer-independent',
 'file_hashes':{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.suffix=='.py' or p.name.startswith('requirements')}}
(A/'artifacts/pecab-code-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='file_hashes'},ensure_ascii=False,indent=2))
