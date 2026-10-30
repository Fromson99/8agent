from common import *
import shutil,ast,sys
T=Path(__file__).parent
# Full existing framework contracts and native API fixtures, fixed before run.
for p in (ROOT/'06_TOOLS/EXPERIMENTS/adr_1152').glob('test_*.py'):shutil.copyfile(p,T/p.name)
shutil.copyfile(ROOT/'06_TOOLS/EXPERIMENTS/adr_1152/api_fixture_integrated.py',T/'api_fixture_integrated.py')
shutil.copyfile(ROOT/'04_EXPERIMENTS/ADR/ADR-1152-ontology-selection-main-integration/artifacts/design/test-support.json',DES/'test-support.json')
s=(T/'test_scenario_native.py').read_text().replace("['normal','multi','repair','conditional','reselect','no_match','still_insufficient','empty_catalog','twice_invalid','off','on_empty']","['normal','multi','off','on_empty']")
s=s.replace('def test_native_scenario_choice_and_publication','def test_database_native_scenario_choice_and_publication')
needle="    monkeypatch.setattr(sc,'compile_package'"
pos=s.index(needle)
s=s[:pos]+'''    from semantic_runtime.ontology_work.repository import Repository
    from semantic_runtime.ontology_work.workflow import Workflow
    from semantic_runtime.ontology_work.store import LocalFolderStore
    from semantic_runtime.ontology_work import runtime as db_runtime
    repo=Repository(lambda:sqlite3.connect(tmp_path/'ontology.sqlite'));repo.initialize()
    work={'version':'ontology-work-v1','concept':'합성 승인 기준','originals':[
        {'id':'P'+str(n+1),'anchor':provision['anchor'],'text':provisions[n][1]}
        for n,provision in enumerate(bundle_value['provisions'])], 'judgments':[], 'origin':{'run_id':'synthetic-native'}}
    w=Workflow(repo,LocalFolderStore(tmp_path/'ontology-work'),actor='native-reviewer',
        source_reader=lambda a:next((r['text'] for r in work['originals'] if r['anchor']==a),None))
    proposal={k:recipe[k] for k in ('components','paths','unused_components')}
    if mode!='on_empty':
        row=w.save(work,proposal,bundle_id=bundle_value['bundle_id'])
        w.review(row['bundle_id'],1,row['work_hash'],True,'합성 조건·경로 확인')
        w.publish(row['bundle_id'],1,row['work_hash'],0)
        package=repo.lookup(work['originals'][0]['anchor'],{'d'})[0]['context']['scenario_package']
    profile['candidate_navigation']['ontology_context']={'mode':'DB'}
    monkeypatch.setattr(db_runtime,'repository',lambda:repo)
''' +s[pos:]
s=s.replace("if mode=='on_empty':profile['candidate_navigation']['ontology_context']={'mode':'A0'}","if mode=='on_empty':assert profile['candidate_navigation']['ontology_context']=={'mode':'DB'}")
(T/'test_database_native.py').write_text(s)
# Fix authenticated Dataiku browser identity per official security documentation.
p=S/'02_BACKEND/semantic_runtime/ontology_work/ui.py';s=p.read_text().replace("auth=dataiku.api_client().get_auth_info(with_secrets=False)","import streamlit as st\n    auth=dataiku.api_client().get_auth_info_from_browser_headers(dict(st.context.headers),with_secrets=False)");p.write_text(s)
put(DES/'api-sources.json',{'dataiku_browser_identity':'https://doc.dataiku.com/dss/latest/webapps/security.html','method':'get_auth_info_from_browser_headers(dict(st.context.headers),with_secrets=False)','inspected':'2026-10-28'})
# Refresh all pins after final source edits, register new inventory.
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
pipe=read(S/'00_SYSTEM/PIPELINE.json')
for ref in pipe['engines'].values():
 p=S/ref['manifest'];e=read(p)
 for n in e['files']:
  if (S/n).is_file():e['files'][n]=sha(S/n)
 put(p,e);ref['sha256']=sha(p)
put(S/'00_SYSTEM/PIPELINE.json',pipe)
registered={r.get('target_path',r['upstream_path']) for r in read(CAND/'candidate.json')['files']}
for p in S.rglob('*'):
 if p.is_file() and '__pycache__' not in p.parts:
  n=str(p.relative_to(S))
  if n not in registered:ac.register_file(CAND,n,upstream_state='present' if (ROOT/n).is_file() else 'absent')
for p in (S/'02_BACKEND/semantic_runtime/ontology_work').glob('*.py'):ast.parse(p.read_text())
print('Prospective new lifecycle tests and four DB-native request cases prepared')
