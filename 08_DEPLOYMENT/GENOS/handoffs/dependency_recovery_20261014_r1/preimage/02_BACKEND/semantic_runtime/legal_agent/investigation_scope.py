"""Bind each additional source action to an explicit request and missing need.

This checks provenance, not semantic relevance. Existing exact-operation and
failed-route guards still decide whether the selected tool may execute.
"""
from .errors import ProposalError
from . import completion_contracts as cc

PROMPT = """추가 조사에는 각 targets별 exploration 한 행을 작성한다. issue_id는 원래 사용자 요구,
request_quote는 그 요구의 정확한 연속 인용, missing_need는 아직 받은 원문으로 답하지 못하는 내용이다.
DIRECT는 사용자가 직접 요구한 범위다. source_quote는 빈 문자열로 둔다. 추가 메모가 있어도 원문 근거나 범위 확장의 권한으로 사용하지 않는다. 단순 배경을 조사 과제로 늘리지 않는다.
DEPENDENCY는 요구를 답하는 데 꼭 필요한 원문의 명시 참조·조건·예외다. source_ref 선택지가 있으면 현재 sources의 id 하나를 선택하고 source_quote는 빈 문자열로 둔다. 서버가 실제 전달한 원문 ID인지 확인하므로 원문을 다시 쓰지 않는다. source_ref가 없는 구 계약에서는 현재 sources에서 실제 확인한 source_quote를 정확히 적는다.
참고할 만하다는 이유만으로 모든 참조나 상위 조문을 읽지 않는다. 배치 읽기는 대상별로 필요한 이유를 적는다.
이미 받은 원문으로 요구를 답할 수 있으면 FINISH로 채택하고 종료한다. 검색 실패는 부재 증명이 아니며 제시된 다른 경로를 고른다."""

def enabled(view):return view.get('completion_contract')in (cc.V6,cc.V7,cc.V8)

def schema(view, targets):
    out = {'type':'array','minItems':1,'maxItems':8,'items':cc.obj({
      'target':{'type':'string',**({'enum':sorted(targets)} if targets else {})},
      'issue_id':{'type':'string','enum':[r['id'] for r in view['issues']]},
      'request_quote':{'type':'string','minLength':1,'maxLength':2000},
      'missing_need':{'type':'string','minLength':1,'maxLength':512},
      'relation':{'enum':['DIRECT','DEPENDENCY']},
      'source_quote':{'type':'string','maxLength':2000,'description':'DEPENDENCY requires an exact delivered original quote. DIRECT uses the user request as authority; send an empty string, any extra annotation is unused as evidence or authorization.'}})}
    if view.get('completion_contract') == cc.V8:
        ids = [s['id'] for s in view.get('sources', [])
               if isinstance(s.get('id'), str) and s.get('text', '').strip()]
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
    if len(rows)!=len(value['targets']) or {r['target'] for r in rows}!=set(value['targets']):
        raise ProposalError('exploration requires one missing need for every selected target')
    issues={r['id']:r for r in view['issues']}
    request=view['investigation_scope']['request']
    for row in rows:
        issue=issues[row['issue_id']]
        if row['issue_id'] not in value['issue_refs']:
            raise ProposalError('exploration issue must be selected in issue_refs')
        quote=row['request_quote']
        if not quote.strip() or quote not in issue.get('request_quote',request):
            raise ProposalError('exploration request quote must belong to its explicit issue')
        if not row['missing_need'].strip():raise ProposalError('exploration requires an unmet request need')
        if row['relation']=='DEPENDENCY':
            ref = row.get('source_ref')
            if view.get('completion_contract') == cc.V8 and ref is not None:
                delivered = {s.get('id'): s for s in view.get('sources', [])
                             if s.get('text', '').strip()}
                if ref not in delivered:
                    raise ProposalError('dependency source_ref must identify a currently delivered original')
                # This ID is the authority. A model's extra quote annotation is
                # not substituted for, or added to, the delivered source text.
            else:
                quote=row['source_quote']
                if not quote.strip() or not any(quote in s.get('text','') for s in view.get('sources',[])):
                    raise ProposalError('dependency requires an exact currently delivered original clause')
        # DIRECT relies exclusively on the selected exact request and missing
        # need. Extra annotation cannot become a dependency or answer evidence;
        # rejecting it would prevent an otherwise valid direct source read.
