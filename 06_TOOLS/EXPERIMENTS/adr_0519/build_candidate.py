from pathlib import Path
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0519/selection/snapshot';P=R/'02_BACKEND/lawrag/research/candidates/adr_0518/selection/revisions/rev-003/snapshot'
s=(P/'02_BACKEND/semantic_runtime/legal_agent/source_selection.py').read_text();s=s[:s.index('POLICY =')]
p=C/'02_BACKEND/semantic_runtime/legal_agent/source_selection.py';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s)
p=C/'02_BACKEND/lawrag/research/experiment_client.py';p.write_text((P/'02_BACKEND/lawrag/research/experiment_client.py').read_text().replace('ADR-0518-five-source-replacement-loop','ADR-0519-root-selection-protected-relations').replace("'ADR-0518'","'ADR-0519'"))
