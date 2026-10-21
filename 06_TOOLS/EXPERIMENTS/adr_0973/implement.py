"""Create isolated follow-up candidate. Never overwrite working/selected code."""
from common import *
import shutil
P=ROOT/'04_EXPERIMENTS/ADR/ADR-0972-structured-selection-qualification/artifacts';old=read(P/'stage.json')
C=ART/'code-candidate';shutil.copytree(ROOT/old['roots']['candidate'],C)
def edit(name,old,new):
 p=C/'02_BACKEND/semantic_runtime/legal_agent'/name;text=p.read_text();assert old in text,(name,old[:80]);p.write_text(text.replace(old,new,1))
edit('structure_selection.py',"obj({'kind': {'const': 'SINGLE'}, 'value': NUMBER}),", "obj({'kind': {'const': 'SINGLE'}, 'value': NUMBER}),\n    obj({'kind': {'const': 'BOUND'},\n         'operator': {'enum': ['LT', 'LTE', 'GT', 'GTE'],\n                      'description': '번호 비교: LT 미만(<), LTE 이하(<=), GT 초과(>), GTE 이상(>=)'},\n         'value': NUMBER}),")
edit('structure_selection.py',"        start = endpoint(clause['start']) if clause['start'] is not None else 0", """        if clause['kind'] == 'BOUND':
            # Execute the model's explicit comparison; never infer its direction.
            pivot = endpoint(clause['value'])
            operation = clause['operator']
            if operation == 'LT': return set(candidates[:pivot])
            if operation == 'LTE': return set(candidates[:pivot + 1])
            if operation == 'GT': return set(candidates[pivot + 1:])
            return set(candidates[pivot:])
        start = endpoint(clause['start']) if clause['start'] is not None else 0""")
edit('structure_selection.py','"3호 이후/초과/이전/미만"은 문맥에 맞게 한쪽 끝을 null로 둔 RANGE와 inclusive 값으로 표현한다.', '번호의 이상·초과·이하·미만은 {kind:"BOUND",operator:"GTE"|"GT"|"LTE"|"LT",value:{n:번호}}로 직접 비교 방향을 선택한다. GTE는 번호>=값(이상), GT는 번호>값(초과), LTE는 번호<=값(이하), LT는 번호<값(미만)이다. 이하/미만은 작은 번호 쪽이며 이상/초과는 큰 번호 쪽이다. 시작·끝이 있는 구간은 RANGE다. 기존 열린 RANGE에서는 작은 쪽 제한이 없으면 start=null, 큰 쪽 제한이 없으면 end=null이다. 이후·이전은 문맥으로 경계 포함 여부까지 판단한다.')
edit('query_scope.py',"'selection': selection_sets.SCHEMA", "'selection': {'anyOf': [selection_sets.SCHEMA, {'type': 'null'}]}")
edit('query_scope.py',"class UnresolvedScope(ValueError):",'''def model_change_schema():
    """Current models must declare a scope decision; stored legacy commands remain valid."""
    value = deepcopy(CHANGE)
    target = value['properties']['targets']['items']
    target['required'].append('selection')
    target['properties']['structure']['description'] = '번호 집합은 selection에 쓰고 null. 번호 없는 단일 목차 제목 조회에만 문자열.'
    target['properties']['selection']['description'] = '번호의 단일·복수·범위·제외 선택. 문서 전체 또는 번호 없는 목차 제목이면 null.'
    return value


class UnresolvedScope(ValueError):''')
edit('query_scope.py','search_scope_change는 사용자가 직접 지정한 검색 대상', 'search_scope_change는 매 명령에서 반드시 출력하는 검색 범위 판단이다. 새 범위 지정이 없으면 {operation:"KEEP",targets:[],user_quote:""}를 출력한다. 범위·열거·제외를 queries에만 적고 이 판단을 생략하지 않는다. targets마다 selection을 명시하고, 번호 집합은 selection/structure=null, 문서 전체는 selection=null/structure=null, 번호 없는 목차 제목은 selection=null/structure=제목으로 표현한다.\nsearch_scope_change는 사용자가 직접 지정한 검색 대상')
edit('request_entry.py','def schema(scoped=False):','def schema(scoped=False, *, model=False):')
edit('request_entry.py',"    command['properties']['search_scope_change']=deepcopy(SEARCH_SCOPE_CHANGE)","""    command['properties']['search_scope_change']=deepcopy(SEARCH_SCOPE_CHANGE)
    if model:
        from .query_scope import model_change_schema
        command['properties']['search_scope_change']=model_change_schema()
        command['required'].append('search_scope_change')""")
edit('request_entry.py','    request_schema=schema(scoped)','    request_schema=schema(scoped, model=True)')
edit('request_entry.py','    def check(raw):\n        output.validate_shape(raw,request_schema)', '    def check(raw, *, from_host=False):\n        output.validate_shape(raw,schema(scoped) if from_host else request_schema)')
edit('request_entry.py','        check(host_entry)','        check(host_entry, from_host=True)')
edit('corrected_memory.py',"        closed=json.loads(encoded(COMMAND))", """        closed=json.loads(encoded(COMMAND))
        from .query_scope import model_change_schema
        closed['properties']['search_scope_change']=model_change_schema()
        closed['required'].append('search_scope_change')""")
edit('source_query_planning.py','def catalogue_schema(names):','def catalogue_schema(names, *, model=False):')
edit('source_query_planning.py',"    return {'type': 'object', 'properties': props, 'required': required, 'additionalProperties': False}","    if model:required.append('structure_selections')\n    return {'type': 'object', 'properties': props, 'required': required, 'additionalProperties': False}")
edit('bounded_source_session.py','source_query_planning.catalogue_schema(names),','source_query_planning.catalogue_schema(names, model=True),')
# Re-pin only code manifests and the enclosing pipeline; no data mutation.
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
    v=read(p)
    if 'files' in v:
        for n in v['files']:v['files'][n]=sha(C/n)
        save(p,v)
def pins(v):
 if isinstance(v,dict):
    if v.get('manifest') and 'sha256' in v and (C/v['manifest']).is_file():v['sha256']=sha(C/v['manifest'])
    for x in v.values():pins(x)
 elif isinstance(v,list):
    for x in v:pins(x)
p=C/'00_SYSTEM/PIPELINE.json';v=read(p);pins(v);save(p,v)
files={n:sha(C/n) for n in old['files']['candidate']}
save(ART/'stage.json',{**old,'roots':{**old['roots'],'candidate':str(C.relative_to(ROOT))},'files':{**old['files'],'candidate':files}})
save(ART/'integration-delta.json',{'against_main98':[n for n,h in files.items() if old['files']['baseline'].get(n)!=h], 'followup_changes':[n for n,h in files.items() if old['files']['candidate'].get(n)!=h], 'parent_observation':{'path':str((P/'trials/set-12/candidate/result.json').relative_to(ROOT)),'sha256':sha(P/'trials/set-12/candidate/result.json')},'working_unchanged':True})
print('Isolated candidate created; working and MAIN98 unchanged')
