from pathlib import Path
import hashlib,json,shutil,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0924-source-lead-parent-handoff';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'merge.json').exists()
put(D/'setup-failure-001.json',{'stage':'candidate snapshot','error':'candidate arm_id must reference role=candidate','product_calls':0,'product_edits':False,'resolution':'Both rebased reference and bridged implementations are registered candidate arms; comparator identity changed before any snapshot/test/model execution.'})
m=read(A/'실험/manifest.json');m['design']['arms'][0].update(id='rebased',role='candidate');m['design']['arms'][1]['derived_from']=['rebased']
m['runs'][0]['arm_ids']=['rebased','bridged']
m['design']['retrieval_stage_plan']['stages_by_arm']['rebased']=m['design']['retrieval_stage_plan']['stages_by_arm'].pop('baseline')
put(A/'실험/manifest.json',m)
release=read(D/'baseline.json')['manifest'];base=R/release['code_root'];previous=R/read(D/'parent-binding.json')['code_root']
files=read(D/'working-before.json');merges=[]
products=['connected_exploration.py','law_navigation.py','decision_projection.py','source_investigation.py','request_repair.py','tool_availability.py','tool_policy.py']
for arm in ('rebased','bridged'):
    for n,h in files.items():assert sha(R/n)==h,n
    cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id',arm,'--experiment-id',m['experiment_id'],'--arm-id',arm,'--run-id','run-001']
    for n in files:cmd+=['--source',n]
    proc=subprocess.run(cmd,capture_output=True,text=True)
    if proc.returncode:raise RuntimeError(proc.stdout+proc.stderr)
    C=R/'02_BACKEND/lawrag/research/candidates/adr_0924'/arm;S=C/'snapshot'
    for name in products:
        rel='02_BACKEND/semantic_runtime/legal_agent/'+name;dest=S/rel
        if not (R/rel).exists():
            shutil.copy2(previous/rel,dest)
            proc=subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',rel,'--upstream-state','absent'],capture_output=True,text=True)
            assert proc.returncode==0,proc.stderr
            method='new-from-parent'
        else:
            proc=subprocess.run(['git','merge-file','-p',str(R/rel),str(base/rel),str(previous/rel)],capture_output=True)
            assert proc.returncode==0,(rel,proc.stderr.decode(),proc.stdout.decode())
            dest.write_bytes(proc.stdout);method='three-way-current-active-parent'
        merges.append({'arm':arm,'path':rel,'method':method,'merged_sha256':sha(dest),'working_sha256':sha(R/rel) if (R/rel).exists() else None,'parent_sha256':sha(previous/rel)})
put(D/'merge.json',merges)
put(D/'serving-files.json',sorted(set(files)|{'02_BACKEND/semantic_runtime/legal_agent/connected_exploration.py'}))
print('Created rebased/bridged snapshots; current changes preserved by three-way merge.')
