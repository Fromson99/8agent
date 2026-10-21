from pathlib import Path
R=Path(__file__).resolve().parents[3];T=R/'06_TOOLS/EXPERIMENTS/adr_0835'
s=(R/'06_TOOLS/EXPERIMENTS/adr_0832/run_tests.py').read_text().replace('adr_0832','adr_0835');(T/'run_tests.py').write_text(s)
s=(R/'06_TOOLS/EXPERIMENTS/adr_0818/test_tasks.py').read_text()
s=s.replace("'dependencies':[],'scope_sufficient':bool(values),'missing':", "'missing':")
s=s.replace("scope_sufficient=False,",'')
s=s.replace("'anchor_ids':[loc['origin_evidence_id']],",'')
s=s.replace("'anchor_ids':[loc['origin_evidence_id']],",'')
s=s.replace("def test_conflict_keeps_prior_sources_and_cannot_publish_match", "def test_rewording_keeps_prior_sources_and_model_judgment")
s=s.replace("assert row['internal']['status']=='CONFLICT'", "assert row['internal']['status']=='CONFIRMED'")
s=s.replace("assert row['content_status']=='UNKNOWN' and not row['difference']", "assert row['content_status']=='MATCH' and row['difference']")
s=s.replace("'이전 확인(재검토)'", "'이전 확인'")
(T/'test_workflow.py').write_text(s)
