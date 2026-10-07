"""Frozen functional integration audit; semantic decisions are explicitly scripted."""
import hashlib, importlib.util, json, shutil, sys, traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'02_BACKEND'));sys.dont_write_bytecode=True
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0602-corrected-route-memory-integration'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def main():
    c=json.loads((ROOT/'02_BACKEND/lawrag/research/candidates/adr_0602/integrated-memory/candidate.json').read_text());r=c['revisions'][-1]
    paths={}
    for f in r['files']:
        p=ROOT/f['frozen_path'];assert sha(p)==f['snapshot_sha256'];paths[f['snapshot_path'].split('/snapshot/',1)[1]]=p
    for p,h in json.loads((ADR/'artifacts/design/freeze.json').read_text()).items():assert sha(ROOT/p)==h
    run=ADR/'artifacts/run-001';assert not run.exists();run.mkdir()
    mem=load('semantic_runtime.legal_agent.corrected_memory',paths['02_BACKEND/semantic_runtime/legal_agent/corrected_memory.py'])
    native=load('semantic_runtime.legal_agent.memory_rag',paths['02_BACKEND/semantic_runtime/legal_agent/memory_rag.py'])
    appmod=load('semantic_runtime.memory_app_candidate',paths['02_BACKEND/semantic_runtime/app.py'])
    proto=load('adr0602_chain',paths['02_BACKEND/semantic_runtime/legal_agent/chain_prototype.py'])
    repo=load('semantic_runtime.legal_agent.adr0602_repository',paths['02_BACKEND/semantic_runtime/legal_agent/repository.py']);proto.NativeRepository=repo.WorkRepository
    guards=load('adr0601_guards',ROOT/'06_TOOLS/EXPERIMENTS/adr_0601/guards.py')
    docs=json.loads((ROOT/'04_EXPERIMENTS/ADR/ADR-0601-rag-chain-empty-state-guards/artifacts/design/RAW/documents.json').read_text())
    inherited=guards.exercise(proto,docs,run/'inherited-guards');write(run/'inherited.json',inherited)
    import contracts
    result=contracts.exercise(mem,native,appmod,run,paths)
    result.update(inherited=inherited,external_model_calls=0,data_kind='SYNTHETIC',semantic_quality='not_measured_scripted_decisions')
    write(run/'result.json',result)
    print(json.dumps({'passed':result['passed'],'total':result['total'],'inherited':inherited['passed'],'external_model_calls':0},ensure_ascii=False),flush=True)
    if result['passed']!=result['total'] or inherited['passed']!=inherited['total']:raise SystemExit(1)
if __name__=='__main__':main()
