from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];AG=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1107/stable-judgment-r1/snapshot/02_BACKEND/semantic_runtime/legal_agent'
def edit(n,a,b):
 p=AG/n;t=p.read_text();assert t.count(a)==1,(n,a[:80],t.count(a));p.write_text(t.replace(a,b))
edit('read_judgment.py',"WIRE_VERSION = 'read-judgment-delta-v2'", "WIRE_VERSION = 'read-judgment-delta-v2'\nNEW_WIRE_VERSION = 'read-judgment-new-entries-v3'\nNEW_PROMPT = '''D/J/E 번호는 이 조사 동안 고정된다. read_judgments.new_review_ids의 새 판단만 read_review.new_reviews의 J번호 키에 작성한다. 이미 있는 판단은 다시 쓰지 않는다. 실제 수정할 때만 revisions의 J번호 키에 operation과 변경 이유·근거를 쓴다. CORE/SUPPORT/CONDITIONAL/DEFER/EXCLUDE는 이번 답에 사용할 역할이다. finding은 실제 원문과 질문을 대조한 판단, basis_refs는 그 J번호에 연결된 source_refs다. 다른 J의 원문으로 대신하지 않는다.\n작성하지 않은 새 판단은 미완료로 남는다. 판단이 미완료여도 독립된 필요한 원문을 READ할 수 있다. DIRECT의 judgment_refs는 실제 의존하는 기존/새 판단이 있을 때만 쓴다. 판단을 근거로 하지 않은 직접 조사에는 []다. DEPENDENCY는 현재 원문과 유효한 판단을 연결한다. missing_need에는 이번 읽기로 확인할 내용을 쓴다.\n기존 판단·부족·충돌은 생략해도 보존된다. need_updates/conflict_updates는 실제 상태를 수정할 때만 작성한다. RESOLVED는 원문 근거가 필요하다. 충돌은 양쪽 근거를 보존하고 CONFLICT로 명시한다. 오류 안내의 위치·기대 근거를 고쳐 한 번 보완한다. 근거 없는 판단은 채택하지 않는다.'''\n")
edit('read_judgment.py',"    return {'version': VERSION, 'request_key': request_key(inv, data),", "    extra=({'wire_version':NEW_WIRE_VERSION,'new_review_ids':[j for j in visible if j not in heads],\n        'issue_ids':[i['id'] for i in data['issues']]} if inv.policy.get('new_read_reviews') else {})\n    return {**extra,'version': VERSION, 'request_key': request_key(inv, data),")
edit('read_judgment.py',"target['properties']['judgment_refs'] = strings(ids, minimum=1 if ids else 0)", "target['properties']['judgment_refs'] = strings(ids, minimum=0 if ctx.get('wire_version')==NEW_WIRE_VERSION else (1 if ids else 0))")
edit('read_judgment.py',"    schema = review_schema(ctx, current, issues)\n    row = schema['properties']['judgments']['items']", "    if ctx.get('wire_version')==NEW_WIRE_VERSION:\n        return new_review_schema(ctx,current,issues)\n    schema = review_schema(ctx, current, issues)\n    row = schema['properties']['judgments']['items']")
# Insert canonical normalization before the retained-head reconstruction.
edit('read_judgment.py',"    result = deepcopy(value); changes = []\n    old = {r['id']:r for r in ctx['judgments']}", "    result = deepcopy(value); changes = []\n    if ctx.get('wire_version')==NEW_WIRE_VERSION and 'new_reviews' in result['read_review']:\n        wire=result['read_review'];rows=[]\n        for kind in ('new_reviews','revisions'):\n            for jid,raw in wire.get(kind,{}).items():\n                row=deepcopy(raw);row.update(judgment_id=jid)\n                if kind=='new_reviews':row['operation']='SET'\n                for name,fixed in (('missing',[]),('conflicts_with',[])):\n                    row.setdefault(name,deepcopy(fixed))\n                if len(ctx['issue_ids'])==1:row.setdefault('issue_refs',list(ctx['issue_ids']))\n                rows.append(row)\n        result['read_review']={'judgments':rows,'need_updates':deepcopy(wire.get('need_updates',[])),\n            'conflict_updates':deepcopy(wire.get('conflict_updates',[]))}\n        changes.append({'rule':'KEYED_NEW_OR_EXPLICIT_REVISION','new_ids':list(wire.get('new_reviews',{})),\n            'revision_ids':list(wire.get('revisions',{})),'automatic_finding':False})\n    old = {r['id']:r for r in ctx['judgments']}")
# A default new_reviews object is always required, so its presence signals the version unambiguously.
insert='''def new_review_schema(ctx,current,issues):
    schema=review_schema(ctx,current,issues);template=schema['properties']['judgments']['items']
    def row(prior=False):
        r=deepcopy(template);r['properties'].pop('judgment_id');r['required'].remove('judgment_id')
        if not prior:
            r['properties'].pop('operation');r['required'].remove('operation')
        for name in ('missing','conflicts_with'):
            r['required'].remove(name)
        if len(issues)==1:r['required'].remove('issue_refs')
        return r
    fresh={jid:row() for jid in ctx['new_review_ids']}
    revised={}
    for head in ctx['judgments']:
        options=[]
        for op in ('SET','CONFLICT','KEEP','WITHDRAW'):
            r=row(True);r['properties']['operation']={'const':op}
            if op in ('KEEP','WITHDRAW'):
                for name in ('use','finding','issue_refs','missing','conflicts_with'):
                    r['properties'].pop(name,None)
                    if name in r['required']:r['required'].remove(name)
            options.append(r)
        revised[head['id']]={'anyOf':options}
    result=obj({'new_reviews':{'type':'object','properties':fresh,'additionalProperties':False},
        'revisions':{'type':'object','properties':revised,'additionalProperties':False},
        'need_updates':schema['properties']['need_updates'],'conflict_updates':schema['properties']['conflict_updates']})
    result['required']=['new_reviews']
    return result


def review_diagnostics(value,ctx):
    from .output_contract import OutputContractError,issue
    review=value.get('read_review',{});rows=review.get('judgments',[]);seen={};errors=[];messages=[]
    visible={r['id']:r for r in ctx['current_originals']};new=ctx.get('wire_version')==NEW_WIRE_VERSION
    def path(index,jid):
        if new:return '/read_review/'+('new_reviews' if jid in ctx['new_review_ids'] else 'revisions')+'/'+jid
        return '/read_review/judgments/'+str(index)
    for i,row in enumerate(rows):
        jid=row.get('judgment_id');where=path(i,jid)
        if jid in seen:
            before=seen[jid];errors.append(issue('READ_JUDGMENT_DUPLICATE',where+'/judgment_id',related=[path(before,jid)+'/judgment_id'],expected={'judgment_id':jid,'rows':[before+1,i+1],'occurrences':1}))
            messages.append(f'{before+1}·{i+1}행의 {jid}가 중복')
        else:seen[jid]=i
        if jid in visible and not set(row.get('basis_refs',[]))&set(visible[jid]['source_refs']):
            errors.append(issue('READ_JUDGMENT_WRONG_ORIGINAL',where+'/basis_refs',expected={'judgment_id':jid,'allowed_source_refs':visible[jid]['source_refs']}))
            messages.append(f"{jid}의 basis_refs는 {visible[jid]['source_refs']} 중 실제 사용한 원문이어야 함")
    if not new:
        missing=[jid for jid in ctx['required'] if jid not in seen]
        if missing:
            errors.append(issue('READ_JUDGMENT_MISSING','/read_review/judgments',expected={'missing_judgment_ids':missing}));messages.append('새 판단 '+', '.join(missing)+'이 빠짐 (omitted)')
    if errors:raise OutputContractError('; '.join(messages),errors,category='READ_JUDGMENT_INVALID')


'''
p=AG/'read_judgment.py';t=p.read_text();p.write_text(t.replace('def normalize_review(value, ctx):',insert+'def normalize_review(value, ctx):'))
edit('read_judgment.py',"    review = value['read_review']\n    schema = review_schema(ctx, current, issues)", "    review = value['read_review']\n    review_diagnostics(value,ctx)\n    schema = review_schema(ctx, current, issues)")
edit('read_judgment.py',"    if set(ctx['required']) - set(ids):", "    if ctx.get('wire_version')!=NEW_WIRE_VERSION and set(ctx['required']) - set(ids):")
edit('read_judgment.py',"            if (old or visible) and not refs or set(refs) - (set(old) | set(ids)):", "            independent=(ctx.get('wire_version')==NEW_WIRE_VERSION and action.get('relation')=='DIRECT')\n            if ((old or visible) and not refs and not independent) or set(refs) - (set(old) | set(ids)):")
# Track pending material rather than creating a judgment. Final provenance validation remains unchanged.
edit('read_judgment.py',"    ns['receipts'][key] = receipt", "    if ctx.get('wire_version')==NEW_WIRE_VERSION:\n        pending=ns.setdefault('pending',{})\n        for jid,bundle in visible.items():\n            unseen=set(bundle['material'])-set(ns['heads'].get(jid,{}).get('seen_material',[]))\n            if unseen:pending[jid]={'judgment_id':jid,'document_id':bundle['document_id'],'source_id':bundle['source_id'],\n                'material':sorted(unseen),'status':'PENDING','reason':'NO_VALID_REVIEW_SUBMITTED'}\n            else:pending.pop(jid,None)\n    ns['receipts'][key] = receipt")
edit('read_judgment.py',"receipt.update(wire_version=WIRE_VERSION", "receipt.update(wire_version=ctx.get('wire_version',WIRE_VERSION)")
edit('decision_projection.py',"prompt = (judgment.PROMPT+'\\n' if judgment_context is not None else '')", "prompt = ((judgment.NEW_PROMPT if judgment_context.get('wire_version')==judgment.NEW_WIRE_VERSION else judgment.PROMPT)+'\\n' if judgment_context is not None else '')")
for p in AG.glob('*.py'):compile(p.read_text(),str(p),'exec')
print('New judgments, explicit revisions and pending source state staged')
