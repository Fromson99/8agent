from pathlib import Path
R=Path(__file__).resolve().parents[3];O=R/'06_TOOLS/EXPERIMENTS/adr_0719'
s=(R/'06_TOOLS/EXPERIMENTS/adr_0712/run_case.py').read_text().replace('ADR-0712-compact-direct-read-context','ADR-0719-request-repair-public-qualification').replace("'compact'","'repaired'").replace('adr0712','adr0719')
(O/'run_case.py').write_text(s)
