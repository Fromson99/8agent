"""Bind each additional source action to an explicit request and missing need.

This checks provenance, not semantic relevance. Existing exact-operation and
failed-route guards still decide whether the selected tool may execute.
"""
from . import output_contract as output
from . import completion_contracts as cc

PROMPT = """추가 조사에는 각 targets별 exploration 한 행을 작성한다. issue_id는 원래 사용자 요구,
request_quote는 그 요구의 정확한 연속 인용, missing_need는 아직 받은 원문으로 답하지 못하는 내용이다.
DIRECT는 사용자가 직접 요구한 범위다. source_quote는 빈 문자열로 둔다. 추가 메모가 있어도 원문 근거나 범위 확장의 권한으로 사용하지 않는다. 단순 배경을 조사 과제로 늘리지 않는다.
DEPENDENCY는 요구를 답하는 데 꼭 필요한 원문의 명시 참조·조건·예외다. source_ref 선택지가 있으면 현재 sources의 id 하나를 선택하고 source_quote는 빈 문자열로 둔다. 서버가 실제 전달한 원문 ID인지 확인하므로 원문을 다시 쓰지 않는다. source_ref가 없는 구 계약에서는 현재 sources에서 실제 확인한 source_quote를 정확히 적는다.
참고할 만하다는 이유만으로 모든 참조나 상위 조문을 읽지 않는다. 배치 읽기는 대상별로 필요한 이유를 적는다.
이미 받은 원문으로 요구를 답할 수 있으면 FINISH로 채택하고 종료한다. 검색 실패는 부재 증명이 아니며 제시된 다른 경로를 고른다."""

def enabled(view):return view.get('completion_contract')in (cc.V6,cc.V7,cc.V8)


def delivered_sources(view):
    """Use only the original pages in this immutable model view, never previews."""
    return [s for s in view.get('sources', []) if s.get('text', '').strip()]


def schema(view, targets):
    originals = delivered_sources(view)
    out = {'type':'array','minItems':1,'maxItems':8,'items':cc.obj({
      'target':{'type':'string',**({'enum':sorted(targets)} if targets else {})},
      'issue_id':{'type':'string','enum':[r['id'] for r in view['issues']]},
      'request_quote':{'type':'string','minLength':1,'maxLength':2000},
      'missing_need':{'type':'string','minLength':1,'maxLength':512},
      'relation':{'enum':['DIRECT','DEPENDENCY'] if originals else ['DIRECT']},
      'source_quote':{'type':'string','maxLength':2000,'description':'DEPENDENCY requires an exact delivered original quote. DIRECT uses the user request as authority; send an empty string, any extra annotation is unused as evidence or authorization.'}})}
    if view.get('completion_contract') == cc.V8:
        ids = [s['id'] for s in originals if isinstance(s.get('id'), str)]
        out['items']['properties']['source_ref'] = {
            'type': ['string', 'null'], 'enum': [None] + sorted(set(ids)),
            'description': 'DEPENDENCY: select a currently delivered sources.id and leave source_quote empty. DIRECT: null. Exact quote is legacy fallback only.'}
        out['items']['properties']['source_quote']['description'] = (
            'Empty with selected source_ref or DIRECT. Without source_ref, DEPENDENCY requires an exact delivered original quote.')
        # Optional for saved clients and existing exact-quote decisions.
    return out


def annotate(view, request):
    if enabled(view):
        view['investigation_scope']={'request':request,
          'rule':'Only explicit request needs or necessary original-text dependencies; each target requires exploration provenance.'}

def validate(value,view):
    if not enabled(view) or not value.get('targets'):return
    rows=value.get('exploration',[])
    errors=[];messages=[]
    def problem(code,path,message,*,related=(),expected=None):
        errors.append(output.issue(code,path,related=related,expected=expected))
        messages.append(message)
    if not isinstance(rows,list):
        raise output.OutputContractError('exploration must be an array',
            [output.issue('EXPLORATION_SHAPE_INVALID','/exploration')])
    targets=value['targets'];seen={}
    row_targets=[r.get('target') for r in rows if isinstance(r,dict) and isinstance(r.get('target'),str)]
    if len(rows)!=len(targets) or set(row_targets)!=set(targets):
        problem('EXPLORATION_TARGET_COVERAGE','/exploration',
            'exploration requires one missing need for every selected target',
            related=['/targets'],expected={'targets':list(targets)})
    issues={r['id']:r for r in view['issues']}
    request=view['investigation_scope']['request']
    originals=delivered_sources(view)
    delivered={s['id']:s for s in originals if isinstance(s.get('id'),str)}
    for n,row in enumerate(rows):
        base='/exploration/'+str(n)
        required=('target','issue_id','request_quote','missing_need','relation','source_quote')
        if not isinstance(row,dict) or any(not isinstance(row.get(k),str) for k in required):
            problem('EXPLORATION_SHAPE_INVALID',base,'exploration fields must have the declared string types')
            continue
        target=row['target']
        if target in seen:
            problem('EXPLORATION_DUPLICATE_TARGET',base+'/target','exploration requires one row per target',
                related=['/exploration/'+str(seen[target])+'/target'],expected={'target':target})
        else:seen[target]=n
        issue=issues.get(row['issue_id'])
        if issue is None:
            problem('EXPLORATION_UNKNOWN_ISSUE',base+'/issue_id','exploration issue must be currently offered',
                expected={'issue_ids':list(issues)})
        if row['issue_id'] not in value.get('issue_refs',[]):
            problem('EXPLORATION_UNSELECTED_ISSUE',base+'/issue_id','exploration issue must be selected in issue_refs',
                related=['/issue_refs'])
        quote=row['request_quote']
        if issue is not None and (not quote.strip() or quote not in issue.get('request_quote',request)):
            problem('EXPLORATION_REQUEST_QUOTE_INVALID',base+'/request_quote',
                'exploration request quote must belong to its explicit issue',
                related=[base+'/issue_id'],expected={'issue_id':row['issue_id']})
        if not row['missing_need'].strip():
            problem('EXPLORATION_MISSING_NEED',base+'/missing_need','exploration requires an unmet request need')
        if row['relation']=='DEPENDENCY':
            ref = row.get('source_ref')
            if not originals:
                problem('DEPENDENCY_WITHOUT_DELIVERED_SOURCE',base+'/relation',
                    'dependency requires an exact currently delivered original clause; no originals are currently delivered',
                    related=[base+'/source_ref',base+'/source_quote'],expected={'allowed_relations':['DIRECT'],'target':target})
            elif view.get('completion_contract') == cc.V8 and ref is not None:
                if not isinstance(ref,str) or ref not in delivered:
                    problem('DEPENDENCY_SOURCE_REF_INVALID',base+'/source_ref',
                        'dependency source_ref must identify a currently delivered original',
                        expected={'source_refs':sorted(delivered),'target':target})
                # This ID is the authority. A model's extra quote annotation is
                # not substituted for, or added to, the delivered source text.
            else:
                quote=row['source_quote']
                if not quote.strip() or not any(quote in s['text'] for s in originals):
                    problem('DEPENDENCY_SOURCE_QUOTE_INVALID',base+'/source_quote',
                        'dependency requires an exact currently delivered original clause',
                        expected={'source_refs':sorted(delivered),'target':target})
        # DIRECT relies exclusively on the selected exact request and missing
        # need. Extra annotation cannot become a dependency or answer evidence;
        # rejecting it would prevent an otherwise valid direct source read.
    if errors:
        raise output.OutputContractError('; '.join(dict.fromkeys(messages)),errors,
            category='EVIDENCE_CONTRACT_INVALID')


def repair_context(view, validation):
    """Targeted guidance for the existing single correction; no proposal changes."""
    if not enabled(view) or not any(r.get('path','').startswith('/exploration')
            for r in validation.get('issues',[])):
        return None
    originals=delivered_sources(view)
    return {'delivered_original_count':len(originals),
        'allowed_relations':['DIRECT','DEPENDENCY'] if originals else ['DIRECT'],
        'source_refs':sorted({s['id'] for s in originals if isinstance(s.get('id'),str)}),
        'instructions':('문제 행의 target과 사용자 요구를 다시 대조한다. 직접 요청된 대상이면 DIRECT로 판단하고 '
            '해당 issue의 request_quote와 missing_need를 정확히 적는다. 직접 요청이 아니면 DIRECT로 바꾸어 우회하지 않는다. '
            'DEPENDENCY는 현재 sources의 원문에 명시된 참조·조건·예외가 있을 때만 가능하다. '
            + ('현재 원문이 없으므로 DEPENDENCY를 선택할 수 없다. 필요한 직접 조사를 선택하거나 그 읽기 대상을 취소한다. '
               if not originals else 'v8은 현재 source_ref를 선택하고 source_quote를 비운다. 구 계약의 인용은 현재 원문의 정확한 연속 문구만 쓴다. ')
            + '원문·사용자 사실·조사 필요성을 만들어 넣지 않는다. 다른 행의 독립 오류도 함께 고친다.')}
