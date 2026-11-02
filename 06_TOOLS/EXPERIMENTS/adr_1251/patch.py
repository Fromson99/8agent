from pathlib import Path
S=Path('/home/jin/8-AGENT/02_BACKEND/lawrag/research/candidates/adr_1251/generalized/snapshot')
p=S/'02_BACKEND/semantic_runtime/legal_agent/need_continuity.py';s=p.read_text();s=s.replace("VERSION = 'declared-need-continuity-v1'","LEGACY_VERSION = 'declared-need-continuity-v1'\nVERSION = 'declared-need-continuity-v2'")
a=s.index("PROMPT = '''");b=s.index("\n\n\ndef known_needs",a)
s=s[:a]+'''PROMPT = """read_judgments.need_continuity가 있으면 모든 needs와 원문 목표를 명시적으로 검토한다. 확보·전달은 서버 영수증이고 법률 판단 완료가 아니다. 이전 선언·목적은 삭제하거나 최신 ANSWERABLE로 덮지 않는다.
read_judgment_review.scope_reviews에는 targets의 모든 target_id를 한 번씩 넣는다. 각 groups는 그 target의 available_evidence_refs를 빠짐없이 한 번씩 나누어 USE/EXCLUDE/OPEN으로 검토한다. 같은 처리·이유인 근거는 한 그룹으로 묶는다. 표제·다른 항도 자동 제외하지 말고 질문과 원문에 따른 이유를 남긴다.
USE는 해당 부분을 실제 사용하는 claim_refs, 그 주장과 일치하는 issue_refs를 쓴다. 각 근거는 그 claim과 채택 judgment 양쪽에 연결되어야 한다. EXCLUDE는 이번 요청에 쓰지 않는 이유와 해당 원문 basis_refs를 남기고 claim_refs/gap_indices는 비운다. OPEN은 같은 issue의 material=true gap_indices(첫 항목1)를 남기며 그 쟁점을 COVERED로 쓰지 않는다. 원문 미확보나 반대·예외를 확인하지 않은 것을 EXCLUDE로 숨기지 않는다.
needs의 origin이 SOURCE_GOAL/STRUCTURE_SELECTION이면 자료 범위 검토 작업이다. 최초 issue_refs는 읽기를 요청한 이력이며, 그 자료를 다른 쟁점에도 쓸 수 있다. RESOLVED는 전체 확보와 scope_reviews의 검토가 끝난 경우다. claim_refs에는 해당 범위의 USE에 실제 연결한 주장만 넣는다. 모든 부분이 정당하게 제외되었다면 claim_refs=[]도 가능하다. 읽기 작업 완료가 의미 필요의 해결은 아니다.
그 밖의 needs는 의미상의 필요다. RESOLVED는 그 필요의 같은 쟁점에 속하는 실제 주장과 근거를 연결한다. 필요를 해결한 target_refs의 범위 검토도 완료해야 한다. 같은 원문을 읽었다는 이유로 다른 쟁점의 주장을 연결하지 않는다. 한 자료는 여러 필요·쟁점에서 사용할 수 있으며 모든 원문을 모든 주장에 인용할 필요는 없다.
NOT_NEEDED는 정확한 사용자 scope_quote 또는 현재 원문으로 제외 이유를 설명한다. OPEN은 material=true와 해당 쟁점의 실제 핵심 gap_indices를 연결한다. 빠진 내용이 있으면 전체 해결로 표시하지 않는다. 쓰지 않는 배열은 [], scope_quote는 빈 문자열이다. repair_feedback이 있으면 지적된 연결·누락 구간을 모두 고치며 내용과 근거를 임의로 추가하거나 삭제하지 않는다."""'''+s[b:]
s=s.replace("    ctx['need_continuity'] = {'version': VERSION,", "    _verify_scope_originals(targets, options, session)\n    for receipt in ctx.get('previous_final_review', []):\n        prior = receipt.get('need_continuity')\n        if prior and prior.get('version') != VERSION:\n            raise ContractError('final scope review version changed; original request must use its bound runtime')\n    ctx['need_continuity'] = {'version': VERSION,\n        'issue_refs': ids, 'scope_input_hash': digest([targets, options]),")
s=s.replace("    node['required'].extend(fields)","    node['required'].extend(fields)\n    if ctx['need_continuity']['version'] == VERSION:\n        _extend_scope_schema(schema, ctx)")
s=s.replace('def validate_review(value, ctx, options, fail):','def _validate_legacy_review(value, ctx, options, fail):',1)
# Add validated scope dispositions to durable resolution receipt, not inferred source adoption.
s=s.replace("def resolution_links(review):\n    return", "def resolution_links(review):\n    return")
s += '''

def _verify_scope_originals(targets, options, session):
    """Check every reviewed original, including excluded ranges, against source bytes."""
    if session is None:
        return  # Pure validation callers supply already-verified evidence options.
    from .repository import text_hash
    raw = {}
    def original(did, bid):
        key = (did, str(bid))
        if key not in raw:
            raw[key] = session.store.source(*key)['text']
        return raw[key]
    for target in targets:
        for span in target['expected']:
            if span.get('block_hash') and text_hash(original(target['document_id'], span['block_id'])) != span['block_hash']:
                raise ContractError('scope review original version/hash changed')
        for ref in target['available_evidence_refs']:
            option = next(o for o in options if o['id'] == ref)
            text = original(option['document_id'], option['block_id'])
            if (text[option['start_cp']:option['end_cp']] != option['text']
                    or digest(option['text']) != option['text_hash']):
                raise ContractError('scope review original range/hash changed')


def _extend_scope_schema(schema, ctx):
    from .completion_contracts import obj
    continuity = ctx['need_continuity']
    targets = continuity['targets']
    refs = sorted({ref for t in targets for ref in t['available_evidence_refs']})
    group = obj({'basis_refs': rj.strings(refs),
        'disposition': {'enum': ['USE', 'EXCLUDE', 'OPEN']},
        'claim_refs': {'type':'array','uniqueItems':True,'items':{'type':'string'}},
        'issue_refs': rj.strings(continuity['issue_refs']),
        'gap_indices': {'type':'array','uniqueItems':True,'items':{'type':'integer','minimum':1}},
        'scope_quote': {'type':'string'}, 'reason':rj.TEXT})
    group['properties']['basis_refs']['minItems'] = 1
    group['properties']['issue_refs']['minItems'] = 1
    schema['properties']['scope_reviews'] = {'type':'array','minItems':len(targets),'maxItems':len(targets),
        'items':obj({'target_id': {'enum':[t['id'] for t in targets]} if targets else {'type':'string'},
            'groups':{'type':'array','items':group}})}
    schema['required'].append('scope_reviews')


def validate_review(value, ctx, options, fail):
    continuity = ctx.get('need_continuity')
    if continuity is None:
        return
    if continuity.get('version') == LEGACY_VERSION:
        return _validate_legacy_review(value, ctx, options, fail)
    if continuity.get('version') != VERSION or continuity.get('scope_input_hash') != digest([continuity['targets'], options]):
        raise ContractError('scope review input/version binding changed')
    targets = {t['id']:t for t in continuity['targets']}
    claims = {c['claim_id']:c for c in value['claims']}
    review = value['read_judgment_review']
    judgments = {j['id']:j for j in ctx['judgments']}
    issues = set(continuity['issue_refs'])
    statuses = {r['issue_id']:r['status'] for r in value['issue_assessments']}
    gaps = value.get('gaps', [])
    def error(code, path, **expected):
        fail(code, path, 'scope/need review requires valid acquisition, disposition and per-claim evidence links', expected)
    def adopted(cid):
        # Evidence belongs to THIS claim and THIS judgment's actual source.
        return {ref for j in review['judgments'] if j['disposition'] in ('USE','CONDITIONAL')
            and cid in j['claim_refs'] and j['id'] in judgments for ref in j['basis_refs']
            if ref in judgments[j['id']]['available_evidence_refs']}
    def gap_links(indices, linked_issues):
        selected = [gaps[i-1] for i in indices if 1 <= i <= len(gaps)]
        return (bool(selected) and len(selected) == len(indices)
            and all(g['material'] and g['issue_id'] in linked_issues for g in selected)
            and not any(statuses.get(i) == 'COVERED' for i in linked_issues))
    seen_targets = [row['target_id'] for row in review.get('scope_reviews', [])]
    if set(seen_targets) != set(targets) or len(seen_targets) != len(set(seen_targets)):
        error('SCOPE_TARGET_COVERAGE','/read_judgment_review/scope_reviews',
            missing_targets=sorted(set(targets)-set(seen_targets)), duplicate_targets=sorted({t for t in seen_targets if seen_targets.count(t)>1}))
    scoped = {}
    for ti, row in enumerate(review.get('scope_reviews', [])):
        tid = row['target_id']
        if tid not in targets:
            continue
        target = targets[tid]; permitted = set(target['available_evidence_refs']); seen = []; used = {}; open_groups = []
        path = '/read_judgment_review/scope_reviews/'+str(ti)
        for gi, group in enumerate(row['groups']):
            gp = path+'/groups/'+str(gi); refs = set(group['basis_refs']); cis = group['claim_refs']; qis = set(group['issue_refs'])
            seen.extend(group['basis_refs'])
            if not refs or refs-permitted:
                error('SCOPE_FOREIGN_EVIDENCE',gp+'/basis_refs', target_id=tid, invalid_evidence_refs=sorted(refs-permitted), allowed_evidence_refs=sorted(permitted))
            if not group['reason'].strip() or not qis or qis-issues:
                error('SCOPE_REVIEW_REASON_ISSUE',gp, issue_refs=sorted(issues), reason='nonempty reasoning for a declared issue')
            quote = group['scope_quote']
            if quote and quote not in continuity['question']:
                error('SCOPE_QUOTE_INVALID',gp+'/scope_quote',required='exact current user question quote')
            if group['disposition'] == 'USE':
                if not cis or group['gap_indices'] or quote:
                    error('SCOPE_USE_LINK',gp, claim_refs='actual claims',gap_indices=[],scope_quote='')
                supported = set()
                for cid in cis:
                    claim = claims.get(cid)
                    actual = refs & set(claim['evidence_refs']) & adopted(cid) if claim else set()
                    if not claim or not actual or not qis.intersection(claim['issue_refs']):
                        error('SCOPE_CLAIM_EVIDENCE',gp,claim_id=cid,basis_refs=sorted(refs),
                            claim_evidence_refs=claim['evidence_refs'] if claim else [],adopted_evidence_refs=sorted(adopted(cid)),issue_refs=sorted(qis))
                    supported |= actual;used.setdefault(cid,set()).update(actual)
                if refs-supported:
                    error('SCOPE_USE_UNSUPPORTED_RANGE',gp+'/basis_refs',missing_evidence_refs=sorted(refs-supported),
                        required='each USE range must support a linked claim and its adopted judgment; separately review unused ranges')
            elif group['disposition'] == 'EXCLUDE':
                if cis or group['gap_indices']:
                    error('SCOPE_EXCLUSION_LINK',gp,claim_refs=[],gap_indices=[])
            elif group['disposition'] == 'OPEN':
                open_groups.append(group)
                if cis or quote or not gap_links(group['gap_indices'],qis):
                    error('SCOPE_OPEN_GAP',gp,claim_refs=[],scope_quote='',issue_refs=sorted(qis),required='same issue material gaps and non-COVERED status')
        missing = permitted-set(seen); repeated = {ref for ref in seen if seen.count(ref)>1}
        if missing or repeated:
            error('SCOPE_RANGE_COVERAGE',path,missing_evidence_refs=sorted(missing),duplicate_evidence_refs=sorted(repeated),
                required='review every presented target range exactly once, without invented or conflicting ranges')
        scoped[tid] = {'used':used,'open':open_groups,'complete':not missing and not repeated and not open_groups,
                       'all_excluded':bool(row['groups']) and all(g['disposition']=='EXCLUDE' for g in row['groups'])}
    known = {n['id']:n for n in ctx['needs']}
    for ni, row in enumerate(review['needs']):
        if row['id'] not in known:
            continue
        need = known[row['id']];path='/read_judgment_review/needs/'+str(ni)
        source_work = need.get('origin') in ('SOURCE_GOAL','STRUCTURE_SELECTION')
        tids = set(row['target_refs']) | set(need.get('target_refs', []))
        nissues = set(need['issue_refs']); refs=set(row['basis_refs'])
        if row['status'] == 'OPEN':
            open_issues = {i for tid in tids for g in scoped.get(tid,{}).get('open',[]) for i in g['issue_refs']}
            allowed = (open_issues or nissues) if source_work else nissues
            if (not row['material'] or row['claim_refs'] or row['scope_quote'] or not gap_links(row['gap_indices'],allowed)):
                error('NEED_OPEN_GAP',path,issue_refs=sorted(allowed),material=True,required='same-issue material gap; no claims; non-COVERED')
            continue
        if row['gap_indices']:
            error('NEED_CLOSED_GAP',path,gap_indices=[])
        if row['status'] == 'NOT_NEEDED':
            quote = row['scope_quote']; quoted = bool(quote.strip() and quote in continuity['question'])
            if row['claim_refs'] or (quote and not quoted) or (not quoted and not refs):
                error('NEED_EXCLUSION_BASIS',path,required='current originals or exact scope quote; no claim adoption')
            if source_work:
                for tid in tids:
                    sc=scoped.get(tid,{})
                    if not sc.get('all_excluded') and not (quoted and not targets[tid]['available_evidence_refs']):
                        error('NEED_EXCLUSION_SCOPE',path,target_id=tid,required='explicit excluded range review; never silently discard an open/use range')
            continue
        # RESOLVED cannot be obtained merely by a model-supplied status or by reading a heading.
        for tid in tids:
            target=targets[tid]
            if not available(target,options):
                error('SCOPE_ACQUISITION_INCOMPLETE',path,target_id=tid,acquisition_status=target.get('acquisition_status'),
                    expected_ranges=target['expected'],available_evidence_refs=target['available_evidence_refs'])
            if not scoped.get(tid,{}).get('complete'):
                error('SCOPE_REVIEW_INCOMPLETE',path,target_id=tid,required='all presented ranges reviewed, no open material review')
        if row['scope_quote']:
            error('NEED_RESOLVED_QUOTE',path,scope_quote='')
        if source_work:
            available_claims={cid for tid in tids for cid in scoped.get(tid,{}).get('used',{})}
            if set(row['claim_refs']) != available_claims:
                error('SOURCE_WORK_CLAIM_LINKS',path,expected_claim_refs=sorted(available_claims),
                    required='source-work records the actual range uses, independent of its original requesting issue')
            continue
        if not row['claim_refs'] or not refs:
            error('NEED_RESOLUTION_CLAIM',path,required='actual same-issue claim and original evidence')
        for cid in row['claim_refs']:
            claim=claims.get(cid);actual=refs & set(claim['evidence_refs']) & adopted(cid) if claim else set()
            if not claim or not nissues.intersection(claim['issue_refs']) or not actual:
                error('NEED_CLAIM_LINK',path,claim_id=cid,need_issue_refs=sorted(nissues),
                    claim_issue_refs=claim['issue_refs'] if claim else [],basis_refs=sorted(refs),
                    claim_evidence_refs=claim['evidence_refs'] if claim else [],adopted_evidence_refs=sorted(adopted(cid)))
            if tids and not any(actual & scoped.get(tid,{}).get('used',{}).get(cid,set()) for tid in tids):
                error('NEED_TARGET_CLAIM_LINK',path,claim_id=cid,target_refs=sorted(tids),
                    required='the resolved claim must use reviewed evidence in a linked target')
'''
p.write_text(s)
# Retain new range reviews with the existing review receipt hash and immutable prior needs.
p=S/'02_BACKEND/semantic_runtime/legal_agent/read_judgment_final.py';s=p.read_text();s=s.replace("'resolution_links':need_continuity.resolution_links(value[FIELD])}","'resolution_links':need_continuity.resolution_links(value[FIELD]),\n            'scope_reviews':deepcopy(value[FIELD].get('scope_reviews', []))}")
p.write_text(s)
print('Patched generalized v2 contract and durable receipt')
