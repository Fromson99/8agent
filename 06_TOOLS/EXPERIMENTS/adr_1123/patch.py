from pathlib import Path
p=Path(__file__).resolve().parents[3]/'02_BACKEND/lawrag/research/candidates/adr_1123/integrated-r1/snapshot/02_BACKEND/semantic_runtime/legal_agent/read_judgment_final.py';t=p.read_text();a=t.index('def validate_review(');b=t.index('\n\ndef retain(',a)
t=t[:a]+'''def validate_review(value, ctx, options):
    from .output_contract import OutputContractError, issue
    review = value[FIELD]
    validate(review, review_schema(ctx, options))
    by_ref = {o['id']: o for o in options}
    problems = []; diagnostics = []
    def fail(code, path, message, expected):
        problems.append(message); diagnostics.append(issue(code, path, expected=expected))
    for field in ('judgments', 'needs', 'conflicts'):
        ids = [r['id'] for r in review[field]]; expected={r['id'] for r in ctx[field]}
        if len(ids) != len(set(ids)) or set(ids) != expected:
            fail('FINAL_REVIEW_ID_COVERAGE','/'+FIELD+'/'+field,
                'final review must account for every retained '+field,
                {'missing_ids':sorted(expected-set(ids)), 'duplicate_ids':sorted({x for x in ids if ids.count(x)>1}), 'expected_ids':sorted(expected)})
        for i,row in enumerate(review[field]):
            if not row['reason'].strip():
                fail('FINAL_REVIEW_REASON','/'+FIELD+'/'+field+'/'+str(i)+'/reason',
                    'final disposition requires reason',{'id':row['id'],'nonempty':True})
    heads = {r['id']: r for r in ctx['judgments']}
    claims = {c['claim_id']: c for c in value['claims']}
    for i,row in enumerate(review['judgments']):
        head = heads[row['id']];path='/'+FIELD+'/judgments/'+str(i)
        if row['disposition'] in ('USE', 'CONDITIONAL'):
            own = set(row['basis_refs']) & set(head['available_evidence_refs'])
            if not own or not row['claim_refs'] or set(row['claim_refs']) - claims.keys():
                # Report each independent correction together, without choosing
                # a legal opinion, claim, or original on the model's behalf.
                if not own:
                    fail('FINAL_REVIEW_OWN_ORIGINAL',path+'/basis_refs',
                        'used judgment requires its current original',
                        {'judgment_id':row['id'],'available_evidence_refs':head['available_evidence_refs']})
                if not row['claim_refs'] or set(row['claim_refs']) - claims.keys():
                    fail('FINAL_REVIEW_ACTUAL_CLAIM',path+'/claim_refs',
                        'used judgment requires an actual claim; claims가 비어 있으면 USE/CONDITIONAL로 채택할 수 없음. 원문으로 실제 주장을 작성하거나 UNRESOLVED/NOT_USED를 판단하고 claim_refs=[]로 작성',
                        {'judgment_id':row['id'],'actual_claim_ids':list(claims),'claim_count':len(claims),
                         'nonadopting_dispositions':['UNRESOLVED','NOT_USED'],'nonadopting_claim_refs':[]})
            elif any(not (set(claims[c]['evidence_refs']) & own) for c in row['claim_refs']):
                fail('FINAL_REVIEW_SHARED_ORIGINAL',path+'/basis_refs',
                    'judgment and claim must share current original evidence',
                    {'judgment_id':row['id'],'own_evidence_refs':sorted(own),
                     'claim_evidence_refs':{c:claims[c]['evidence_refs'] for c in row['claim_refs']}})
        elif row['claim_refs']:
            fail('FINAL_REVIEW_UNADOPTED_CLAIM',path+'/claim_refs',
                'unresolved/unused judgment cannot claim final adoption',
                {'judgment_id':row['id'],'disposition':row['disposition'],'claim_refs':[]})
    for field in ('needs', 'conflicts'):
        known = {r['id']: r for r in ctx[field]}
        for i,row in enumerate(review[field]):
            if row['status'] != 'RESOLVED':continue
            path='/'+FIELD+'/'+field+'/'+str(i)+'/basis_refs'
            if not row['basis_refs']:
                fail('FINAL_REVIEW_RESOLUTION_ORIGINAL',path,'final resolution requires current original evidence',{'id':row['id'],'nonempty':True})
            if field == 'conflicts':
                selected = [by_ref[r] for r in row['basis_refs']]
                if not all(covered(opinion['basis'], selected) for opinion in known[row['id']]['opinions']):
                    fail('FINAL_REVIEW_CONFLICT_ORIGINALS',path,
                        'final conflict resolution requires the exact originals of both opinions',{'id':row['id'],'requires_both_originals':True})
    if problems:raise OutputContractError('; '.join(dict.fromkeys(problems)),diagnostics,category='FINAL_READ_REVIEW_INVALID')
''' +t[b:];p.write_text(t)
