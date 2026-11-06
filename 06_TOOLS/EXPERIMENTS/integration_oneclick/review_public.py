"""Compare delivered, cited source ranges with the independent R4 reference anchors."""
def review_response(body, anchors):
    term = ((body.get('assembly') or {}).get('term_agent') or {})
    outcome = term.get('accepted_outcome') or {}
    answer = body.get('answer') or {}
    claims = answer.get('claims', []) if isinstance(answer, dict) else []
    cited = {ref for claim in claims for ref in claim.get('source_ids', [])}
    delivered = {(row['document_id'], str(block))
                 for row in term.get('evidence_inventory', []) if row.get('source_id') in cited
                 for scope in row.get('available_scopes', []) if scope.get('delivered_complete')
                 for block in scope.get('block_ids', [])}
    wanted = {(anchor['document_id'], str(block)) for anchor in anchors for block in anchor['block_ids']}
    complete = (outcome.get('disposition'), outcome.get('answer_coverage')) == ('ANSWER','COVERED')
    return {'accepted_complete_answer': complete and bool(claims),
            'expected_blocks': len(wanted), 'matched_blocks': len(wanted & delivered),
            'missing_blocks': sorted(wanted - delivered),
            'claims': [claim['text'] for claim in claims]}
