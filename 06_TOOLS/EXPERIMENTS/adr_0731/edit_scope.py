from pathlib import Path
R=Path(__file__).resolve().parents[3]
C=R/'02_BACKEND/lawrag/research/candidates/adr_0731/integrated/snapshot'
L=C/'02_BACKEND/semantic_runtime/legal_agent'
(L/'investigation_scope.py').write_text('''"""Bind each additional source action to an explicit request and missing need.

This checks provenance, not semantic relevance. Existing exact-operation and
failed-route guards still decide whether the selected tool may execute.
"""
from .errors import ProposalError
from . import completion_contracts as cc

PROMPT = """추가 조사에는 각 targets별 exploration 한 행을 작성한다. issue_id는 원래 사용자 요구,
request_quote는 그 요구의 정확한 연속 인용, missing_need는 아직 받은 원문으로 답하지 못하는 내용이다.
DIRECT는 사용자가 직접 요구한 범위다. 단순 배경을 조사 과제로 늘리지 않는다.
DEPENDENCY는 요구를 답하는 데 꼭 필요한 원문의 명시 참조·조건·예외이며, 현재 sources에서 실제 확인한 source_quote를 적는다.
참고할 만하다는 이유만으로 모든 참조나 상위 조문을 읽지 않는다. 배치 읽기는 대상별로 필요한 이유를 적는다.
이미 받은 원문으로 요구를 답할 수 있으면 FINISH로 채택하고 종료한다. 검색 실패는 부재 증명이 아니며 제시된 다른 경로를 고른다."""

def enabled(view):return view.get('completion_contract')==cc.V6

def schema(view, targets):
    return {'type':'array','minItems':1,'maxItems':8,'items':cc.obj({
      'target':{'type':'string','enum':sorted(targets)},
      'issue_id':{'type':'string','enum':[r['id'] for r in view['issues']]},
      'request_quote':{'type':'string','minLength':1,'maxLength':2000},
      'missing_need':{'type':'string','minLength':1,'maxLength':512},
      'relation':{'enum':['DIRECT','DEPENDENCY']},
      'source_quote':{'type':'string','maxLength':2000}})}

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
            quote=row['source_quote']
            if not quote.strip() or not any(quote in s.get('text','') for s in view.get('sources',[])):
                raise ProposalError('dependency requires an exact currently delivered original clause')
        elif row['source_quote']:
            raise ProposalError('DIRECT has no dependency quote; choose DEPENDENCY for a source dependency')
''')
p=L/'law_navigation.py';s=p.read_text()
s=s.replace("    for kind in sorted({a['action'] for a in actions.values()}) + sorted(terminal_actions):", "    from . import investigation_scope as scope\n    if scope.enabled(view):\n        base['properties']['exploration']=scope.schema(view,set(actions))\n        base['properties']['exploration']['minItems']=0\n    for kind in sorted({a['action'] for a in actions.values()}) + sorted(terminal_actions):")
s=s.replace("        if kind == 'SEARCH_STRUCTURE':\n            branch['properties']['queries']['minItems'] = 0", "        if scope.enabled(view):\n            branch['properties']['exploration']=scope.schema(view,{a['id'] for a in actions.values() if a['action']==kind})\n            if terminal:branch['properties']['exploration'].update(minItems=0,maxItems=0)\n            else:\n                branch['required'].append('exploration')\n                branch['properties']['issue_refs']['minItems']=1\n        if kind == 'SEARCH_STRUCTURE':\n            branch['properties']['queries']['minItems'] = 0")
s=s.replace("        data['presentation_id']=lc.token(self.s,'P',digest(data));self.save()", "        from . import investigation_scope\n        investigation_scope.annotate(data,self.question)\n        data['presentation_id']=lc.token(self.s,'P',digest(data));self.save()")
# self.question is not assumed: constructor stores the request in self.q.
s=s.replace('investigation_scope.annotate(data,self.question)','investigation_scope.annotate(data,self.q)')
s=s.replace("        schema_validate(value, decision_schema(data, actions, set(self.p['groups'])))", "        schema_validate(value, decision_schema(data, actions, set(self.p['groups'])))\n        from . import investigation_scope\n        investigation_scope.validate(value,data)")
s=s.replace("        with latency.span('law.select.model_prepare', phase=phase) as metrics:", "        from . import investigation_scope\n        if investigation_scope.enabled(data):system+='\\n'+investigation_scope.PROMPT\n        with latency.span('law.select.model_prepare', phase=phase) as metrics:")
p.write_text(s)
p=L/'navigation_input.py';p.write_text(p.read_text().replace('article_refs는 articles의 같은 id 카드, card_ref는 shared_cards의 같은 이름 카드다.', 'article_refs는 articles의 같은 id 카드다.'))
