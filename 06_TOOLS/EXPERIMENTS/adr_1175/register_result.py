from common import *
r=read(ART/'report.json');a=read(ART/'manifest.json')
paths=[p for p in ART.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p!=ART/'manifest.json' and not p.name.startswith(('validate-','hash-'))]
paths+=list(Path(__file__).parent.glob('*.py'))+[ROOT/read(DES/'freeze.json')['candidate_revision']['manifest_path'],ROOT/r['path']]
a['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Source-scope contract fix, immutable parent record correction, frozen candidate, native API and stored-output tests','contains_raw_prompts_and_outputs':bool('raw' in p.parts or 'canonical' in p.parts or p.suffix in ('.log','.sqlite','.gz'))} for p in paths];put(ART/'manifest.json',a);print('registered',len(paths),'stable artifacts')
