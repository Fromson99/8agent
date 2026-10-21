from pathlib import Path
R=Path(__file__).resolve().parents[3]
C=R/'02_BACKEND/lawrag/research/candidates/adr_0894/mixed/snapshot'
p=C/'02_BACKEND/semantic_runtime/legal_agent/completion_v6.py'
s=p.read_text();old="(?:한다|하며|하고|할|합니다)'";new="(?:한다|하며|하고|할|합니다|하되)'"
assert s.count(old)==1
p.write_text(s.replace(old,new))
print('One literal obligation connective added; mixed modalities remain UNSPECIFIED')
