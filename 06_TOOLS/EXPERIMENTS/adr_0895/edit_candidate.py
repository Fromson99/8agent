from pathlib import Path
R=Path(__file__).resolve().parents[3]
C=R/'02_BACKEND/lawrag/research/candidates/adr_0895/consistent/snapshot'
p=C/'02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py'
s=p.read_text();old="value['limitations'] = [r['text'] for r in value['limitation_items']]"
assert s.count(old)==1
s=s.replace(old,"# Detailed gap identities stay separate; identical display text is emitted once.\n    value['limitations'] = list(dict.fromkeys(r['text'] for r in value['limitation_items']))")
p.write_text(s)
p=C/'02_BACKEND/semantic_runtime/legal_agent/unified_runtime.py';s=p.read_text()
old="limits=list(dict.fromkeys(raw.get('limitations',[])+investigation.get('completion_limitations',[])))"
assert s.count(old)==1
new="""# A completion has already committed its exact limitations with its text.
        # Preserve old duplicate-bearing commits too; normalization belongs before commit.
        limits=(list(raw.get('limitations',[])) if investigation.get('completion_contract') else
                list(dict.fromkeys(raw.get('limitations',[])+investigation.get('completion_limitations',[]))))"""
p.write_text(s.replace(old,new))
print('Canonical public text deduplication and immutable completion response aligned')
