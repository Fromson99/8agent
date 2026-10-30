from common import *
import subprocess
r=read(ART/'report.json');a=read(ART/'manifest.json')
paths=[p for p in ART.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p!=ART/'manifest.json']
paths+=list(Path(__file__).parent.glob('*.py'))+[ROOT/read(DES/'freeze.json')['candidate_revision']['manifest_path'],ROOT/r['path']]
a['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Assessment consistency implementation, native replay, synthetic tests, actual CM001/007/009 wire/journal or audit report','contains_raw_prompts_and_outputs':bool('raw' in p.parts or 'canonical' in p.parts or p.suffix in ('.log','.sqlite','.gz'))} for p in paths]
put(ART/'manifest.json',a)
for name,args in [('hash-result-r2',('hash','--path',str(ADR))),('validate-before-close-r2',('validate','--path',str(ADR)))]:
 o=subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py',*args],capture_output=True,text=True);(ART/(name+'.txt')).write_text(o.stdout+o.stderr);print(name,o.returncode);print((o.stdout+o.stderr)[-4500:]);assert o.returncode==0
