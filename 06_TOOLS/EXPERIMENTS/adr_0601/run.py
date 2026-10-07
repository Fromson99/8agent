"""Frozen ordinary state/transaction contracts only. Never imports a model client."""
import ast,hashlib,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'02_BACKEND'));sys.dont_write_bytecode=True
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0601-rag-chain-empty-state-guards'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 for p,h in json.loads((ADR/'artifacts/design/freeze.json').read_text()).items():assert sha(ROOT/p)==h
 cp=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0601/safe-state-chain/candidate.json';c=json.loads(cp.read_text());r=c['revisions'][-1];paths={}
 for f in r['files']:
  q=ROOT/f['frozen_path'];assert sha(q)==f['snapshot_sha256'];paths[f['snapshot_path'].split('/snapshot/',1)[1]]=q
 def load(name,p):
  spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
 module_path=paths['02_BACKEND/semantic_runtime/legal_agent/chain_prototype.py'];mod=load('adr0601',module_path)
 native=load('semantic_runtime.legal_agent.adr0601',paths['02_BACKEND/semantic_runtime/legal_agent/repository.py']);mod.NativeRepository=native.WorkRepository
 parent_path=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0599/admitted-chain/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/chain_prototype.py';parent=load('adr0599_reference',parent_path)
 same_prompts=all(getattr(mod,k)==getattr(parent,k) for k in ['RESOLVER','COMMAND_CHECK_PROMPT','ANSWER_PROMPT','TEXT_EXTRACT_PROMPT','TEXT_CHECK_PROMPT','TEXT_EXTRACT_SCHEMA','TEXT_CHECK_SCHEMA'])
 functions=lambda p:{n.name:ast.dump(n,include_attributes=False) for n in ast.parse(p.read_text()).body if isinstance(n,ast.FunctionDef)}
 a,b=functions(module_path),functions(parent_path);same_text_functions=all(a[k]==b[k] for k in ['normalize_text_evidence','text_fact_errors'])
 assert same_prompts and same_text_functions
 run=ADR/'artifacts/run-001';assert not run.exists();run.mkdir()
 docs=json.loads((ADR/'artifacts/design/RAW/documents.json').read_text());import guards
 result=guards.exercise(mod,docs,run/'guards')
 result.update(external_model_calls=0,semantic_prompts_unchanged=same_prompts,text_verifier_functions_unchanged=same_text_functions,prior_equivalent_product_calibration={'path':'04_EXPERIMENTS/ADR/ADR-0599-rag-chain-provenance-repair-admission/artifacts/run-001/calibration-result.json','passed':17,'total':17,'fresh_model_test':False},scope='Ordinary offline state contracts; not model accuracy or complete RAG certification')
 (run/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'passed':result['passed'],'total':result['total'],'external_model_calls':0}))
 if result['passed']!=result['total']:raise SystemExit(1)
if __name__=='__main__':main()
