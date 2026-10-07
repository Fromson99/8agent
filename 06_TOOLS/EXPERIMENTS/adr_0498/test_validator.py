"""Check the live stable validator rejects model-policy scope leakage."""
import sys,json,shutil,tempfile,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[3];sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'))
import adr_structure as v
A=R/'04_EXPERIMENTS/ADR/ADR-0498-gemma4-fp8-compatible-schema-cm51-fsc10'
def main():
 with tempfile.TemporaryDirectory() as temp:
  a=Path(temp)/A.name;(a/'artifacts').mkdir(parents=True)
  shutil.copy2(A/'README.md',a/'README.md');shutil.copy2(A/'claim.json',a/'claim.json');shutil.copytree(A/'실험',a/'실험')
  shutil.copy2(A/'artifacts/manifest.json',a/'artifacts/manifest.json')
  p=a/'artifacts/gemma-policy.json';shutil.copy2(A/'artifacts/gemma-policy.json',p)
  mp=a/'실험/manifest.json';m=json.loads(mp.read_text());m['llm_policy']['experiment_override']['policy_path']=str(p);mp.write_text(json.dumps(m))
  initial=v.validate_adr(a);assert not initial,initial;passed=1
  for mutate in ['judge_model','hash','main','private']:
   mm=json.loads(json.dumps(m));policy=json.loads((A/'artifacts/gemma-policy.json').read_text())
   if mutate=='judge_model':mm['llm_policy']['llm_calls'][1]['model']='google/gemma-4-31b-it'
   elif mutate=='hash':mm['llm_policy']['experiment_override']['policy_sha256']='0'*64
   elif mutate=='main':policy['main_wiring']='changed'
   elif mutate=='private':policy['source_scope']=['private']
   p.write_text(json.dumps(policy))
   if mutate!='hash':mm['llm_policy']['experiment_override']['policy_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
   mp.write_text(json.dumps(mm));errors=v.validate_adr(a)
   assert any('override' in e or 'All new experiment roles' in e for e in errors),(mutate,errors);passed+=1
  print(json.dumps({'passed':passed,'live_model_calls':0,'checks':'authorized scope accepted; judge change, stale hash, MAIN and private data rejected'}))
if __name__=='__main__':main()
