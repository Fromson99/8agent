from common import *
import subprocess,datetime
f=read(ART/'freeze.json');C=ROOT/f['code_root']
changed=[n for n,h in f['files'].items() if sha(C/n)!=h]
graph=(ART/'graph-final.txt').read_text();previous=(ROOT/'04_EXPERIMENTS/ADR/ADR-1124-ontology-explicit-exception-contract/artifacts/graph-final.txt').read_text()
errors=lambda s:{l for l in s.splitlines() if l.startswith('ERROR:')}
validation=[]
for n in (1130,1131,1132,1133):
 adr=next((ROOT/'04_EXPERIMENTS/ADR').glob(f'ADR-{n}-*'))
 p=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/run_tool.py'),'adr_structure.py','validate','--path',str(adr),'--final'],capture_output=True,text=True)
 validation.append({'adr':n,'exit_code':p.returncode,'output':p.stdout+p.stderr})
pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
audit={'captured_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'frozen_code_files':len(f['files']),'changed_files':changed,'pointer_sha256':sha(pointer),'frozen_pointer_sha256':f['pointer_sha256'],'pointer_unchanged':sha(pointer)==f['pointer_sha256'],'final_validations':validation,'graph':{'exit_code':1,'errors':sorted(errors(graph)),'additional_errors_vs1124':sorted(errors(graph)-errors(previous)),'scope':'global graph still fails on9 pre-existing historical errors; not a full pass'},'candidate_only':True,'main_promoted':False,'genos_deployed':False,'data_layer_published':False,'new_model_calls':4,'contract_checks':140,'route_score':{'passed':3,'total':4},'quality_certified':False,'decision_eligible':False}
put(ART/'completion-audit.json',audit)
assert not changed and audit['pointer_unchanged'] and all(v['exit_code']==0 for v in validation) and not audit['graph']['additional_errors_vs1124'],audit
index=read(ART/'manifest.json');index['files']=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'description':'Frozen design, actual calls, synthetic contracts or post-selection reporting','contains_raw_prompts_and_outputs':('/raw/' in str(p) or p.name.startswith(('input-','output-')))} for p in sorted(set([p for p in ART.rglob('*') if p.is_file() and p.name!='manifest.json']+list(Path(__file__).parent.glob('*.py'))))];put(ART/'manifest.json',index)
print(json.dumps(audit,ensure_ascii=False,indent=2))
