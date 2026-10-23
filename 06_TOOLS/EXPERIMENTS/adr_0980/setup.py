from common import *
import sys,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-0978-unified-scope-main-qualification';s=read(parent/'artifacts/stage.json');PC=ROOT/s['roots']['candidate'];prev=read(ROOT/s['candidate_dir']/'candidate.json');m=read(ADR/'실험/manifest.json')
paths=[r['target_path'] for r in prev['files'] if (ROOT/r['target_path']).exists()]
D=ac.snapshot(ADR,'candidate',paths,experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001']);C=D/'snapshot'
for row in prev['files']:
 n=row['target_path'];p=C/n;absent=not p.exists();p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PC/n,p)
 if absent:ac.register_file(D,n,upstream_state='absent')
save(ART/'stage.json',{**s,'parent_probe':str(parent.relative_to(ROOT)),'roots':{'baseline':s['roots']['baseline'],'candidate':str(C.relative_to(ROOT))},'candidate_dir':str(D.relative_to(ROOT)),
 'working_baseline':{r['target_path']:sha(ROOT/r['target_path']) if (ROOT/r['target_path']).exists() else None for r in prev['files']}})
p=C/'02_BACKEND/semantic_runtime/legal_agent/request_entry.py';t=p.read_text()
old='queries는 최대4개다. 첫 검색어는 업무 문맥을 포함한 주체·핵심 행위 중심으로 짧게 만든다. 기간·비율·연장 같은 일반 낱말만 따로 추가하면 다른 제도가 섞이므로 핵심 주체·행위를 유지한다. 모르는 법령 이름을 만들어 검색하지 않는다. 문서명·조문·법령 약칭 등 실제 단서를 보존한다. 문서 ID·실제 법률 결론을 추측하지 않는다.'
new='queries는 최대4개다. 전체 질문과 쟁점은 별도로 보존되므로 검색어는 찾으려는 규칙을 구별하는 핵심 표현으로 만든다. 법령명은 scope_decision에 결속된다. 본문 검색어에 그 법령명과 질문 전체를 반복하면 넓은 일반 단어가 검색 결과를 지배하므로, 먼저 핵심 법률 표현을 검색하고 읽은 원문에서 주체·행위·조건이 맞는지 판단한다. 조사할 내용이 같은 일반 단어를 여러 검색어로 늘리지 않는다. 알려진 조문번호가 사용자 원문이나 실제 조회 결과에 없으면 기억으로 번호·제목을 만들어 조회하지 않는다. 문서 ID·법률 결론을 추측하지 않는다.'
assert old in t;t=t.replace(old,new)
old='search.mode는 STRUCTURE(법령/목차/조문 부근의 단서로 위치 조회) 또는 FULLTEXT(세부 내용/문구로 본문 검색)다. FULLTEXT 전에 STRUCTURE를 반드시 거칠 필요가 없다.'
new='search.mode와 queries는 scope_decision과 함께 하나의 검색 계획이다. 사용자에게 실제 조문번호가 주어졌거나 목차 자체·특정 제목 위치를 요청하면 STRUCTURE로 저장 위치를 조회한다. 법령명만 지정하고 요건·기준·의무 등 내용을 물었으며 해당 조문 위치가 아직 확인되지 않았다면 FULLTEXT로 핵심 내용 표현을 찾는다. 문서명이 명시되었다는 이유만으로 STRUCTURE를 고르지 않는다. FULLTEXT도 지정 문서·구조 범위 안에서 실행된다.'
assert old in t;t=t.replace(old,new);p.write_text(t)
p=C/'02_BACKEND/semantic_runtime/legal_agent/decision_projection.py';t=p.read_text()
t=t.replace('def read_candidate_rows(data, candidates):','def read_candidate_rows(data, candidates, matcher=None):')
t=t.replace("hint_fields = ('article', 'heading', 'preview', 'coordinate', 'title', 'surface')", "hint_fields = ('article', 'heading', 'preview', 'coordinate', 'title', 'surface', 'path')")
needle='    return list(rows.values())\n\n\ndef navigation_option'
replacement='''    if matcher is not None:
        from .structure_query import node_path
        for target, action in candidates.items():
            identity=action['identity'];did=identity.get('document_id');uid=identity.get('unit_id')
            source=getattr(matcher,'sources',{}).get(identity.get('source_id')) if identity.get('source_id') else None
            if source:
                if did is not None and did != source['document_id']:
                    raise ContractError('read candidate source document differs from offered action')
                did=source['document_id']
                if uid is None:uid=source.get('unit_id')
            if did is not None and uid is not None and (did,str(uid)) in matcher.units:
                add(target, {'path':node_path(matcher,did,str(uid))})
    return list(rows.values())


def navigation_option'''
assert needle in t;t=t.replace(needle,replacement).replace('rows=read_candidate_rows(data,candidates)','rows=read_candidate_rows(data,candidates,getattr(inv.s,\'matcher\',None))')
needle='READ는 read_candidates에서 필요한 본문 최대4개를 읽는다.'
assert needle in t;t=t.replace(needle,needle+' 후보의 path는 저장된 편·장·절·관·조의 제목 문맥이다. 같은 제목이라도 회사 종류·대상 주체가 다르면 별개 조문이므로 이 문맥과 질문을 함께 보고 읽을 대상을 고른다. 번호를 추측해 반복 조회하지 않는다. 이미 읽은 원문에 요청한 규칙이 없으면 SEARCH_BODY로 현재 지정 범위 안에서 핵심 표현을 검색하거나 다음 후보를 확인한다.')
p.write_text(t)
print(C)
