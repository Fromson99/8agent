from pathlib import Path
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0892/verified/snapshot/02_BACKEND/semantic_runtime/legal_agent';P=R/'02_BACKEND/lawrag/research/candidates/adr_0891/continuity/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent'
s=(P/'completion_execution.py').read_text();old='            model_sources,model_options=assessment_original_view(model_sources,options)\n';assert old in s;(C/'completion_execution.py').write_text(s.replace(old,''))
(C/'bounded_source_session.py').write_bytes((P/'bounded_source_session.py').read_bytes())
p=C/'gateway.py';s=(P/'gateway.py').read_text();old="        if exact and all(option_carries(card) for card in exact):\n            result.pop('exact_evidence')\n";assert old in s
s=s.replace(old,old+'''        if result.get('input_projection')=='compact-selection-source-v3':
            # Both the sender and durable wire-receipt verifier call this exact
            # projection, after canonical source/span/ACL verification. Persisted
            # evidence keeps its coordinates; models see exact text and IDs once.
            from .completion_execution import assessment_original_view
            result['sources'], result['evidence_options'] = assessment_original_view(
                result.get('sources',[]),result.get('evidence_options',[]))
''',1);p.write_text(s)
print('Canonical verification preserved; one shared sender/receipt wire projection')
