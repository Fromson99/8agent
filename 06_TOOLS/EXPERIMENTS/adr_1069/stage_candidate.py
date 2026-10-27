"""Register and pin ADR1069 snapshots without changing any active runtime."""
from pathlib import Path
import argparse, hashlib, json, sys
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1069-navigation-view-211s-profile'
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as candidate

def read(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def stage(name,freeze=False):
    if name != 'profile-baseline-r1':raise ValueError('ADR1069 has only B0 profile-baseline-r1')
    directory=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1069'/name; root=directory/'snapshot'
    policy=read(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'); policy['http_retries']=0
    if policy.get('provider_failover') or policy['max_output_tokens'] is not None or policy.get('fallback_allowed') is not False:raise ValueError('strict output-unlimited model policy required')
    save(root/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',policy)
    p=root/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json';grant=read(p);grant['policy_sha256']=sha(root/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json');save(p,grant)
    known={x['target_path'] for x in read(directory/'candidate.json')['files']}
    for p in sorted(root.rglob('*')):
        if not p.is_file():continue
        name=str(p.relative_to(root))
        if '__pycache__' in name or '.pytest_cache' in name:raise ValueError('generated file in candidate: '+name)
        if name not in known:candidate.register_file(directory,name,upstream_state='present' if (ROOT/name).is_file() else 'absent')
    # Consumers must hash the exact new helper as well as existing modules.
    helpers=[str(p.relative_to(root)) for p in (root/'02_BACKEND/semantic_runtime/legal_agent').glob('*.py') if not (ROOT/p.relative_to(root)).exists()]
    for p in sorted((root/'02_BACKEND/ENGINES').rglob('*.json')):
        d=read(p);files=d.get('files')
        if not isinstance(files,dict):continue
        if '02_BACKEND/semantic_runtime/legal_agent/gateway.py' in files:
            for name in helpers:files[name]=sha(root/name)
        for name in files:files[name]=sha(root/name)
        d['files']=dict(sorted(files.items()));save(p,d)
    p=root/'00_SYSTEM/PIPELINE.json';d=read(p)
    for engine in d['engines'].values():engine['sha256']=sha(root/engine['manifest'])
    def visit(v):
        if isinstance(v,dict):
            if isinstance(v.get('path'),str) and 'sha256' in v and (root/v['path']).is_file():v['sha256']=sha(root/v['path'])
            for key,value in list(v.items()):
                if key.endswith('_path') and isinstance(value,str) and key[:-5]+'_sha256' in v and (root/value).is_file():v[key[:-5]+'_sha256']=sha(root/value)
                visit(value)
        elif isinstance(v,list):
            for x in v:visit(x)
    visit(d);save(p,d);candidate.refresh(directory)
    if freeze:candidate.freeze(directory)
    errors=candidate.validate(directory)
    unexpected=[e for e in errors if freeze or e != 'frozen revision required']
    if unexpected:raise ValueError(unexpected)
    print(json.dumps({'candidate':str(directory.relative_to(ROOT)),'files':len(read(directory/'candidate.json')['files']),'validation':errors,'frozen':freeze},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('--freeze',action='store_true');a=p.parse_args();stage(a.candidate,a.freeze)
