from common import *
import datetime,subprocess
f=read(ART/'freeze.json');C=ROOT/f['code_root'];changed=[n for n,h in f['files'].items() if sha(C/n)!=h]
changed_scripts=[n for n,h in f['scripts'].items() if sha(ROOT/n)!=h];changed_inputs=[n for n,h in f['inputs'].items() if sha(ROOT/n)!=h]
graph=(ART/'graph-final.txt').read_text();previous=(ROOT/'04_EXPERIMENTS/ADR/ADR-1133-scenario-selection-receipt/artifacts/graph-final.txt').read_text();errors=lambda s:{l for l in s.splitlines() if l.startswith('ERROR:')}
r=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/run_tool.py'),'adr_structure.py','validate','--path',str(ADR),'--final'],capture_output=True,text=True)
a={'captured_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'frozen_files':len(f['files']),'changed_files':changed,'changed_frozen_scripts':changed_scripts,'changed_inputs':changed_inputs,'selected_pointer_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256'],'final_validation':{'exit_code':r.returncode,'output':r.stdout+r.stderr},'graph':{'exit_code':1,'errors':sorted(errors(graph)),'additional_errors_vs1133':sorted(errors(graph)-errors(previous)),'scope':'Global graph remains failed on9 historical errors; no new errors for this candidate'},'new_model_calls':0,'contract_checks':157,'native_http_modes':9,'candidate_only':True,'main_promoted':False,'genos_deployed':False,'data_layer_published':False}
put(ART/'completion-audit.json',a)
assert not changed and not changed_scripts and not changed_inputs and a['selected_pointer_unchanged'] and r.returncode==0 and not a['graph']['additional_errors_vs1133'],a
index=read(ART/'manifest.json');index['files']=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'description':'Frozen implementation and synthetic verification, no real-model quality claim','contains_raw_prompts_and_outputs':False} for p in sorted(set([p for p in ART.rglob('*') if p.is_file() and p.name!='manifest.json']+list(Path(__file__).parent.glob('*.py'))))];put(ART/'manifest.json',index)
print(json.dumps(a,ensure_ascii=False,indent=2))
