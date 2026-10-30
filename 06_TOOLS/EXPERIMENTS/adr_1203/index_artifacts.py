from common import *
a=read(ART/'manifest.json')
paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and 'runtime' not in p.parts and not p.name.startswith(('validation','graph'))]
paths+=list(Path(__file__).parent.glob('*.py'))+[ROOT/read(DES/'freeze-live.json')['candidate_revision']['manifest_path']]
a['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Actual one-shot CM009, frozen code/inputs, exact scope and purpose-change audits; failed results retained','contains_raw_prompts_and_outputs':p.suffix=='.gz' and ('raw' in p.parts or 'canonical' in p.parts)} for p in paths]
(ART/'manifest.json').write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n')
print('Indexed',len(paths),'artifacts')
