from common import *
import subprocess,datetime
def audit(name,number):
 A=ROOT/'04_EXPERIMENTS/ADR'/name;D=A/'artifacts';T=ROOT/f'06_TOOLS/EXPERIMENTS/adr_{number}'
 def index():
  m=read(D/'manifest.json');m['files']=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'description':'Frozen design/code binding, raw product evidence, result or audit; no secrets','contains_raw_prompts_and_outputs':('/raw/' in str(p) or p.name.startswith(('input-','output-')))} for p in sorted(list(p for p in D.rglob('*') if p.is_file() and p.name!='manifest.json')+list(T.glob('*.py')))];put(D/'manifest.json',m)
 index()
 cmd=[str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/run_tool.py'),'adr_structure.py']
 v=subprocess.run(cmd+['validate','--path',str(A),'--final'],capture_output=True,text=True);(D/'validate-final.txt').write_text(v.stdout+v.stderr)
 g=subprocess.run(cmd+['graph','--adr-root',str(ROOT/'04_EXPERIMENTS/ADR')],capture_output=True,text=True);(D/'graph-final.txt').write_text(g.stdout+g.stderr)
 errors=[s for s in (g.stdout+g.stderr).splitlines() if s.startswith('ERROR:')];f=read(D/'freeze.json')
 changed={arm:[n for n,h in b['files'].items() if sha(ROOT/b['code_root']/n)!=h] for arm,b in f['arms'].items()}
 scripts=[n for n,h in f['scripts'].items() if sha(ROOT/n)!=h];inputs=[n for n,h in f['inputs'].items() if sha(ROOT/n)!=h]
 a={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'individual_final_validation':{'exit_code':v.returncode,'output':v.stdout+v.stderr},'global_graph':{'exit_code':g.returncode,'errors':errors,'errors_involving_this_adr':[s for s in errors if str(number) in s],'claim':'Global historical errors remain; this is not a whole-graph pass'},'frozen_code_drift':changed,'frozen_script_drift':scripts,'frozen_input_drift':inputs,'active_pointer_now':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'main_changes_by_this_task':0,'candidate_only':True,'quality_certified':False,'tests':read(D/'check-001.json')}
 # Do not repeat the full48test trace in every audit.
 a['tests']={k:v for k,v in a['tests'].items() if k not in ('rows','imports')}
 put(D/'completion-audit.json',a);index()
 print(number,'final',v.returncode,'global_errors',len(errors),'local_errors',len(a['global_graph']['errors_involving_this_adr']),'drift',changed,scripts,inputs)
 assert v.returncode==0 and not any(changed.values()) and not scripts and not inputs and not a['global_graph']['errors_involving_this_adr']
audit('ADR-1148-scenario-complement-walltime',1148)
audit('ADR-1150-scenario-complement-candidate-check',1150)
