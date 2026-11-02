"""Account for the full request in the existing ASSESS call, without legal inference.

The server binds text parts, evidence and gaps. The model still judges semantic
necessity and applicability; a reviewed row is not proof of legal completeness.
"""
from copy import deepcopy
import re
from jsonschema import validate
from ..contracts import digest
from .completion_contracts import obj, refs
from .errors import ContractError
from .output_contract import OutputContractError, issue

VERSION = 'request-requirement-coverage-v1'
FIELD = 'requirement_review'
LINK_RULE = 'PRESERVE_UNLINKED_MATERIAL_GAPS_BY_REFERENCE_V2'
PROMPT = '''requirement_context는 초기 쟁점 목록과 별개로 사용자 질문 전체를 보존한 검토 대상이다. 이 ASSESS 응답의 requirement_review에서 질문이 실제로 요구한 주체·대상·조건·절차·예외를 의미별로 나누고, 각 요구를 현재 원문과 대조한다. request_parts의 R번호는 문장/문단 위치이며 법률 쟁점의 정답 목록이 아니다. 한 문장에 여러 요구가 있으면 여러 행으로 나눈다. 초기 issues에 빠진 요구도 생략하지 말고 가장 관련된 기존 issue_refs에 연결한다. 단순 관련 규정이나 모든 예외를 새 필수 요구로 만들지 않는다.
모든 request_parts와 issues를 적어도 한 번 연결한다. SATISFIED는 실제 claims의 claim_refs와 같은 현재 evidence_options의 basis_refs가 필요하다. 읽었다는 사실이나 제목·위임 위치만으로 구체 내용까지 충족했다고 하지 않는다. EXCLUDED는 요청 밖이라는 의견과 원문 basis_refs 또는 사용자가 직접 범위를 한정한 현재 발언 scope_quote가 필요하며 이유만으로 제외하지 않는다. 요청 문구를 인용했다는 사실만으로 제외가 맞다는 뜻은 아니다.
필요한 원문이나 사실을 확인하지 못했다면 UNRESOLVED로 쓰고 같은 응답 gaps의 material=true 항목에 gap_indices로 연결한다(배열의 첫 항목은1). 새로 필요한 본문·위임·예외도 기존 gaps에 기록한다. gap.kind와 suggested_action은 기존 원문 조사/실제 사실 구분을 따른다. 알려진 위치만 missing_target에 쓰고 모르면 빈 문자열과 구체적인 부족 이유를 쓴다. 이미 확보한 claims는 유지한다. 같은 요구의 일부만 충족되면 충족 부분과 미해결 부분을 따로 쓴다. 의미상 불확실성만으로 불필요한 조사나 사용자 사실 질문을 만들지 않는다.'''

def enabled(profile):
    return profile.get('candidate_navigation', {}).get('requirement_coverage', False)

def context(question, issues, options):
    # Exact contiguous text, including punctuation and whitespace. Long requests
    # are grouped, never truncated. These are text positions, not inferred needs.
    chunks = question.splitlines(keepends=True) or [question]
    step = max(1, (len(chunks) + 31) // 32)
    parts = [{'id':'R'+str(i//step+1),'text':''.join(chunks[i:i+step])}
             for i in range(0,len(chunks),step)]
    data = {'version':VERSION,'request_parts':parts,'issues':deepcopy(issues),
            'evidence_hash':digest(options),'semantic_completeness_certified':False}
    return {**data,'binding_hash':digest(data)}

def review_schema(ctx, options):
    base = {'request_refs':refs([p['id'] for p in ctx['request_parts']],1),
        'issue_refs':refs([i['id'] for i in ctx['issues']],0),
        'requirement':{'type':'string','minLength':1,'maxLength':500},
        'reason':{'type':'string','minLength':1,'maxLength':600},
        'basis_refs':refs([o['id'] for o in options],0),
        'claim_refs':{'type':'array','uniqueItems':True,'maxItems':12,'items':{'type':'string','pattern':'^C[1-9][0-9]*$'}},
        'gap_indices':{'type':'array','uniqueItems':True,'items':{'type':'integer','minimum':1}},
        'scope_quote':{'type':'string'}}
    branches=[]
    for status in ('SATISFIED','EXCLUDED','UNRESOLVED'):
        row=deepcopy(base);row['status']={'const':status}
        if status=='SATISFIED':
            for field in ('issue_refs','basis_refs','claim_refs'):row[field]['minItems']=1
            row['gap_indices']['maxItems']=0;row['scope_quote']={'const':''}
        elif status=='EXCLUDED':
            row['claim_refs']['maxItems']=0;row['gap_indices']['maxItems']=0
        else:
            row['issue_refs']['minItems']=1;row['gap_indices']['minItems']=1
            row['claim_refs']['maxItems']=0;row['scope_quote']={'const':''}
        branches.append(obj(row))
    return {'type':'array','minItems':1,'maxItems':64,'items':{'anyOf':branches}}

def attach(schema, ctx, options):
    result=deepcopy(schema);result['properties'][FIELD]=review_schema(ctx,options)
    result['required'].append(FIELD);return result

def core(value, schema):
    value,schema=deepcopy(value),deepcopy(schema)
    value.pop(FIELD,None);schema['properties'].pop(FIELD,None)
    schema['required']=[k for k in schema['required'] if k!=FIELD]
    return value,schema

def validate_review(value, ctx, options):
    if digest({k:v for k,v in ctx.items() if k!='binding_hash'})!=ctx['binding_hash'] or digest(options)!=ctx['evidence_hash']:
        raise ContractError('requirement review context/evidence changed')
    review=value.get(FIELD)
    validate(review,review_schema(ctx,options))
    errors=[]
    def fail(code,path,expected):errors.append(issue(code,path,expected=expected))
    for field,expected in (('request_refs',{p['id'] for p in ctx['request_parts']}),
                           ('issue_refs',{i['id'] for i in ctx['issues']})):
        seen={ref for row in review for ref in row[field]}
        if seen!=expected:fail('REQUIREMENT_COVERAGE_MISSING','/'+FIELD,{'field':field,'missing':sorted(expected-seen),'allowed':sorted(expected)})
    claims={c['claim_id']:c for c in value.get('claims',[])};gaps=value.get('gaps',[])
    parts={p['id']:p['text'] for p in ctx['request_parts']};seen_gaps=set()
    for n,row in enumerate(review):
        path='/'+FIELD+'/'+str(n)
        if not row['requirement'].strip() or not row['reason'].strip():fail('REQUIREMENT_REASON_EMPTY',path,'nonblank requirement and reason')
        if row['status']=='SATISFIED':
            selected=[claims[c] for c in row['claim_refs'] if c in claims]
            valid=(len(selected)==len(row['claim_refs']) and bool(selected)
                and all(set(c['issue_refs'])&set(row['issue_refs']) for c in selected)
                and set(row['issue_refs'])<=set().union(*(set(c['issue_refs']) for c in selected))
                and set(row['basis_refs'])<=set().union(*(set(c['evidence_refs']) for c in selected)))
            if not valid:fail('REQUIREMENT_CLAIM_EVIDENCE',path,{'claim_refs':list(claims),'rule':'actual same-issue claims and their selected current evidence'})
        elif row['status']=='EXCLUDED':
            quote=row['scope_quote']
            if quote and (not quote.strip() or not any(quote in parts[r] for r in row['request_refs'])):
                fail('REQUIREMENT_SCOPE_QUOTE',path+'/scope_quote','literal current-user scope text in selected request parts')
            if not row['basis_refs'] and not quote.strip():fail('REQUIREMENT_EXCLUSION_BASIS',path,'current original evidence or literal current-user scope quote; prose alone cannot exclude')
        else:
            selected=[gaps[i-1] for i in row['gap_indices'] if 1<=i<=len(gaps)]
            valid=(len(selected)==len(row['gap_indices']) and bool(selected)
                and all(g['material'] and g['issue_id'] in row['issue_refs'] for g in selected)
                and set(row['issue_refs'])<={g['issue_id'] for g in selected})
            if not valid:fail('REQUIREMENT_MATERIAL_GAP',path,{'allowed_gap_indices':list(range(1,len(gaps)+1)),'rule':'same-issue material gaps; do not drop unmet requirements'})
            seen_gaps.update(row['gap_indices'])
    missing=[i for i,g in enumerate(gaps,1) if g['material'] and i not in seen_gaps]
    if missing:fail('REQUIREMENT_GAP_COVERAGE','/'+FIELD,{
        'unreviewed_material_gap_indices':missing,
        'gaps':[{'gap_index':i,'issue_id':gaps[i-1]['issue_id'],'kind':gaps[i-1]['kind'],
                 'reason_path':'/gaps/'+str(i-1)+'/reason'} for i in missing],
        'rule':'Preserve each material gap and explicitly link an UNRESOLVED request row; do not erase the gap or infer fulfillment.'})
    if errors:raise OutputContractError('Requirement coverage must bind actual claims, exclusions and material gaps',errors,category='REQUIREMENT_REVIEW_INVALID')

def retain(result, value, ctx, options, *, reconciliation=None):
    validate_review(value,ctx,options)
    receipt={'version':VERSION,'binding_hash':ctx['binding_hash'],'rows':deepcopy(value[FIELD]),
             'semantic_completeness_certified':False}
    if reconciliation:receipt['reconciliation']=deepcopy(reconciliation)
    receipt['receipt_hash']=digest(receipt);result[FIELD]=receipt

def verify_saved(result, ctx, options):
    receipt=result.get(FIELD,{})
    if (receipt.get('version')!=VERSION or receipt.get('binding_hash')!=ctx['binding_hash']
            or receipt.get('receipt_hash')!=digest({k:v for k,v in receipt.items() if k!='receipt_hash'})):
        raise ContractError('saved requirement review missing, stale or changed')
    validate_review({**result,FIELD:receipt['rows']},ctx,options)

def limit_unreviewed(result):
    """Exceptional output-limit fallback keeps originals but cannot certify coverage."""
    if result.get(FIELD):return
    result['disposition']='LIMITED_ANSWER'
    if result.get('answer_coverage')=='COVERED':result['answer_coverage']='PARTIAL'
    row={'id':'L-requirement-review','kind':'EXECUTION_LIMIT','issue_id':None,
         'text':'질문 전체의 요구별 원문 충족 검토를 완료하지 못했습니다. 확인한 원문 범위만 제공합니다.'}
    result['limitation_items'].append(row)
    result['limitations']=list(dict.fromkeys([*result['limitations'],row['text']]))


def reconcile_material_gaps(value, ctx, options):
    """Bind existing material gaps without changing claims, gaps or legal opinions.

    Only an otherwise valid review with missing gap links is eligible. The
    original proposal and both hashes survive; the ordinary validator runs again.
    Ambiguous request-part mappings remain model-owned repair failures.
    """
    try:
        validate_review(value,ctx,options)
        return value,None
    except OutputContractError as exc:
        # OutputContractError exposes the normalized issue list directly.
        entries=exc.issues
        if not entries or any(e['code']!='REQUIREMENT_GAP_COVERAGE' for e in entries):raise
    result=deepcopy(value);rows=result[FIELD];added=[]
    linked={g for r in rows if r['status']=='UNRESOLVED' for g in r['gap_indices']}
    for index,gap in enumerate(value.get('gaps',[]),1):
        if not gap['material'] or index in linked:continue
        matches=[r for r in rows if gap['issue_id'] in r['issue_refs']]
        requests={tuple(r['request_refs']) for r in matches}
        if len(requests)!=1 or len(rows)>=64 or not gap['reason'].strip():
            validate_review(value,ctx,options)  # Existing repair, no guessed mapping.
        row={'request_refs':list(next(iter(requests))),'issue_refs':[gap['issue_id']],
            # These are explicit references, not a shortened/summarized reason.
            # The full model-authored reason stays exclusively in gaps[index-1].
            'requirement':'미확인 사항 gap '+str(index),
            'reason':'gap '+str(index)+'의 전체 사유와 미확인 상태를 유지합니다.', 'status':'UNRESOLVED',
            'basis_refs':[],'claim_refs':[],'gap_indices':[index],'scope_quote':''}
        rows.append(row);added.append(index)
    validate_review(result,ctx,options)
    receipt={'rule':LINK_RULE,'original_proposal':deepcopy(value),
        'original_hash':digest(value),'reconciled_hash':digest(result),'gap_indices':added,
        'gap_references':[{'gap_index':i,'path':'/gaps/'+str(i-1),
                           'gap_hash':digest(value['gaps'][i-1])} for i in added],
        'claims_unchanged':result.get('claims')==value.get('claims'),
        'gaps_unchanged':result.get('gaps')==value.get('gaps'),'semantic_completeness_certified':False}
    return result,receipt
