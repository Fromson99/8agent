from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];S=R/'02_BACKEND/lawrag/research/candidates/adr_0773/successful-publication/snapshot'
def change(name,before,after):
 p=S/name;t=p.read_text();assert t.count(before)==1,(name,before[:90]);p.write_text(t.replace(before,after))
B='02_BACKEND/semantic_runtime/';L=B+'legal_agent/'
change(L+'unified_runtime.py',"    except BaseException as exc:\n        if cases.model_resource.session is not None:","    except BaseException as exc:\n        if hasattr(cases,'shortcut'):\n            from .successful_answer import fail\n            fail(cases,principal)\n        if cases.model_resource.session is not None:")
change(L+'unified_runtime.py',"                from .core_evidence_route import finalize\n                finalize(cases,result,principal)","                finish_shortcut(cases,result,principal,envelope,repo)")
change(L+'unified_runtime.py',"    from .core_evidence_route import finalize\n    finalize(cases,result,principal)","    finish_shortcut(cases,result,principal,envelope,session.work)")
change(L+'unified_runtime.py',"def procedure_replayable(cases,result):",'''def finish_shortcut(cases,result,principal,envelope,work):
    if not hasattr(cases,'shortcut'):return
    from .successful_answer import record
    from .core_evidence_route import finalize
    # The receipt cannot become visible if core validation/finalization fails.
    with cases.transaction():
        if record(cases,result,principal,envelope,work):finalize(cases,result,principal)


def procedure_replayable(cases,result):''')
change(L+'core_evidence_route.py',"    parts = cases.parts(gid)\n", "    from .successful_answer import require\n    require(repo,cases.active_case,goal=gid)\n    parts = cases.parts(gid)\n")
change(L+'core_evidence_route.py',"    goal = repo.db.execute('SELECT * FROM goal WHERE id=?', (path['goal_id'],)).fetchone()", "    from .successful_answer import require\n    require(repo,path['origin']['investigation_id'],goal=path['goal_id'])\n    goal = repo.db.execute('SELECT * FROM goal WHERE id=?', (path['goal_id'],)).fetchone()")
change(L+'shortcut_repository.py',"    def enqueue(self, scope, consumer, aggregate, revision):\n", "    def enqueue(self, scope, consumer, aggregate, revision):\n        if consumer == 'wiki':\n            from .successful_answer import eligible\n            if not eligible(self,aggregate):return\n")
change(L+'shortcut_repository.py',"    def compiler_input(self, ident, principal):\n        case=self.investigation(ident,principal)","    def compiler_input(self, ident, principal):\n        from .successful_answer import require\n        require(self,ident)\n        case=self.investigation(ident,principal)")
change(L+'shortcut_repository.py',"        if value.get('core_evidence_route'):\n", "        from .successful_answer import check_knowledge\n        check_knowledge(self,value)\n        if value.get('core_evidence_route'):\n")
change(B+'ad_backend.py',"            value=dict(r);value['kind']=kind\n", "            value=dict(r);value['kind']=kind\n            if kind=='shortcut' and not trash:\n                from .legal_agent.successful_answer import eligible\n                if not eligible(self.repo,value['id']):continue\n")
change(B+'ad_mode.py',"| 목록·검색 | shortcut 전체 보여줘 / 위키 목록 / 위키 검색 상장 |", "| 정상 완료 목록·검색 | shortcut 전체 보여줘 / 위키 목록 / 위키 검색 상장 |")
change(B+'ad_mode.py',"숏컷 보여줘 / 1번 보여줘", "shortcut 목록에는 최종 답변 게시까지 성공한 현재 기록만 표시합니다. 실패·진행 중 원장은 전체 테이블에서 조회할 수 있습니다.\n숏컷 보여줘 / 1번 보여줘")
P='02_BACKEND/lawrag/pipeline/legal_wiki_compiler.py'
change(P,"def _check_inputs(repo,principal,snapshots):\n", "def _check_inputs(repo,principal,snapshots):\n    from semantic_runtime.legal_agent.successful_answer import compiler_binding\n    compiler_binding(repo,snapshots)\n")
change(P,"    segments,sources,records=offered(snapshots)","    from semantic_runtime.legal_agent.successful_answer import compiler_binding,compiler_records\n    success_bindings=compiler_binding(repo,snapshots)\n    admitted,excluded_records=compiler_records(repo,snapshots)\n    segments,sources,records=offered(admitted)")
change(P,"        _check_inputs(repo,principal,snapshots)\n", "        _check_inputs(repo,principal,snapshots)\n        if compiler_binding(repo,snapshots)!=success_bindings:raise Conflict('successful answer changed during wiki compilation')\n")
change(P,"        for value in units:\n", "        for value in units:\n            value['successful_publications']={key:success_bindings[key] for key in value['input_cases']}\n")
change(P,"    with repo.transaction():\n        if commit_guard:commit_guard()", "    manifest['successful_publications']=success_bindings\n    manifest['excluded_unsuccessful_records']=excluded_records\n    with repo.transaction():\n        if commit_guard:commit_guard()")
# Rebind just the candidate's complete pinned code and append the new authority.
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=S/'00_SYSTEM/PIPELINE.json';c=json.loads(p.read_text())
for entry in c['engines'].values():
 ep=S/entry['manifest'];e=json.loads(ep.read_text())
 if L+'core_evidence_route.py' in e['files']:e['files'][L+'successful_answer.py']=sha(S/L/'successful_answer.py')
 e['files']={n:sha(S/n) for n in e['files']}
 ep.write_text(json.dumps(e,ensure_ascii=False,indent=2)+'\n');entry['sha256']=sha(ep)
p.write_text(json.dumps(c,ensure_ascii=False,indent=2)+'\n')
print('Candidate wiring and engine pins updated')
