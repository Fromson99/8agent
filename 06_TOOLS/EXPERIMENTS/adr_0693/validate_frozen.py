from pathlib import Path
import subprocess,json,hashlib,concurrent.futures
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0693-main46-display-judgment-integration';D=A/'artifacts/contracts';D.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
runner=R/'06_TOOLS/EXPERIMENTS/adr_0693/run_contracts.py'
common=['test_genos_full_error_log.py','test_main_workflow_display.py','test_standalone_current_judgment.py','test_genos_answer_stream.py','test_rag_flow_svg.py']
def run(arm):
 c=R/'02_BACKEND/lawrag/research/candidates/adr_0693'/arm;v=json.loads((c/'candidate.json').read_text());rev=v['revisions'][-1];s=c/'revisions'/rev['revision_id']/'snapshot'
 files=[str(s/'05_TESTS/CONTRACTS'/p) for p in common]
 if arm=='consistent-judgment':
  files += [str(s/'05_TESTS/CONTRACTS'/p) for p in ['test_judgment_loop_recovery.py','test_investigation_completion_adr0678.py','test_completion_boundary_adr0679.py']]
  files += [str(R/'06_TOOLS/EXPERIMENTS/adr_0693/test_completion_v4.py'), str(R/'06_TOOLS/EXPERIMENTS/adr_0689/test_review_repairs.py')]
 cmd=[str(R/'.venv/bin/python'),str(runner),str(s),*files,'-k','not test_completion_preserves_correction_table_history_and_experience','--junitxml='+str(D/(arm+'.xml'))]
 with (D/(arm+'.log')).open('w') as out:r=subprocess.run(cmd,cwd=R,stdout=out,stderr=subprocess.STDOUT)
 return {'arm':arm,'exit_code':r.returncode,'code_root':str(s.relative_to(R)),'manifest_path':str((c/'candidate.json').relative_to(R)),'manifest_sha256':sha(c/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(R)),'runner_sha256':sha(runner)}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(run,['safe-display','consistent-judgment']))
(D/'bindings.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
raise SystemExit(any(r['exit_code'] for r in result))
