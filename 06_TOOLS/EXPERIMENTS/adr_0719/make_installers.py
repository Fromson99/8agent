from pathlib import Path
R=Path(__file__).resolve().parents[3];target=R/'06_TOOLS/EXPERIMENTS/adr_0719'
for name in ('install_reviewed.py','stage_release.py','rollback_working.py','verify_active.py'):
 s=(R/'06_TOOLS/EXPERIMENTS/adr_0712'/name).read_text().replace('ADR-0712-compact-direct-read-context','ADR-0719-request-repair-public-qualification').replace('compact-input-20261009-r1','request-repair-20261009-r1').replace('ADR0712','ADR0719').replace('MAIN49','MAIN50')
 if name=='verify_active.py':
  s=s.replace("assert completion.CONTRACT=='investigation-completion-v4'", "assert completion.version(app.state.pipeline.term_agent.profile)=='investigation-completion-v5'")
  s=s.replace("receipt['completion_contract']=completion.CONTRACT", "receipt['completion_contract']=completion.version(app.state.pipeline.term_agent.profile)")
  s=s.replace("'gateway','investigation_chain','law_navigation'", "'gateway','investigation_chain','law_navigation','request_repair','completion_v5'")
 (target/name).write_text(s)
