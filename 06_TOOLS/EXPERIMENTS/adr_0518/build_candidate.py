from pathlib import Path
R=Path(__file__).resolve().parents[3]
old=R/'02_BACKEND/lawrag/research/candidates/adr_0517/selection/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/source_selection.py'
out=R/'02_BACKEND/lawrag/research/candidates/adr_0518/selection/snapshot/02_BACKEND/semantic_runtime/legal_agent/source_selection.py'
out.parent.mkdir(parents=True,exist_ok=True)
text=old.read_text().split('def select_sources(')[0]
text=text[:text.index('POLICY =')]+text[text.index('def digest('):]
out.write_text(text)
