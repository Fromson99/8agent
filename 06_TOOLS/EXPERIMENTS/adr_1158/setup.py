from pathlib import Path
import json,sys,shutil,hashlib
ROOT=Path(__file__).resolve().parents[3];P=ROOT/'04_EXPERIMENTS/ADR/ADR-1157-ontology-workflow-sql-binding';A=ROOT/'04_EXPERIMENTS/ADR/ADR-1158-ontology-workflow-consumer-check';T=Path(__file__).parent
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for p in (ROOT/'06_TOOLS/EXPERIMENTS/adr_1157').glob('*.py'):
 if p.name in ('setup.py','finish_failure.py'):continue
 s=p.read_text().replace('ADR-1157-ontology-workflow-sql-binding','ADR-1158-ontology-workflow-consumer-check').replace('adr_1157','adr_1158')
 if p.name=='check.py':s=s.replace('import pytest\nfiles=',"if mode=='ui':sys.path.insert(0,str(ROOT/'90_RUNTIME/streamlit-knowledge-design/python'))\nimport pytest\nfiles=")
 if p.name=='test_database_native.py':s=s.replace("    proposal={k:recipe[k]","    authoring_proposal={k:recipe[k]").replace('w.save(work,proposal,','w.save(work,authoring_proposal,')
 (T/p.name).write_text(s)
D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
for name in ('baseline.json','criteria.json','test-support.json','api-sources.json'):shutil.copyfile(P/'artifacts/design'/name,D/name)
criteria=read(D/'criteria.json');criteria['hypothesis']='Preserve1157 runtime and validate repaired fixtures, real existing-screen operations, agent source capture, Dataiku enqueue recipe, isolated Oracle transactions and final shipped schema.';put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');old=read(P/'실험/manifest.json')
for k in ('design','dataset','retrieval_accounting'):m[k]=old[k]
m['design']['code_isolation']['candidates']=[];m['design']['hypothesis']=criteria['hypothesis'];m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design']['arms'][0]['derived_from']=['ADR-1157-experiment-v1/connected'];m['design']['arms'][1]['changes']='Repair test variables/import path; existing UI connected-state text; Dataiku ingestion adapter. Same runtime behavior.'
m['dataset'].update(frozen_source=str((D/'criteria.json').relative_to(ROOT)),sha256=sha(D/'criteria.json'),version='1158-v1')
m['runs'][0].update(arm_ids=['connected'],selection_rule='Prior19workflow+216regression+4DBHTTP and realUI; Oracle/delivery/capture checks as prospectively specified',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(ROOT)));m['llm_policy']['llm_calls']=[];put(A/'실험/manifest.json',m)
f=read(P/'artifacts/design/freeze.json');sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(A,'connected-r1',[n for n in f['files'] if (ROOT/n).is_file()],experiment_id=m['experiment_id'],arm_id='connected',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 dst=S/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/f['code_root']/n,dst)
 if not (ROOT/n).exists():ac.register_file(C,n,upstream_state='absent')
p=S/'03_FRONTEND/APPS/legal-knowledge-streamlit/app.py';s=p.read_text()
s=s.replace("        html('<div class=\"side-foot\">DATAIKU · ORACLE<br>개발 미리보기 / 운영 API 미연결<br>예시를 수정해 화면 흐름을 확인하세요.</div>')","        if os.environ.get('GENOS_RAG_ONTOLOGY_CONFIG'):\n            html('<div class=\"side-foot\">DATAIKU · ORACLE<br>온톨로지 관리·시뮬레이션 연결 모드<br>다른 메뉴는 설계 미리보기입니다.</div>')\n        else:\n            html('<div class=\"side-foot\">DATAIKU · ORACLE<br>설계 미리보기 / 실제 승인 미연결</div>')")
s=s.replace("            st.caption('중계서버·배치·승인·위키·온톨로지·시뮬레이션의 실제 API는 미연결입니다.')","            st.caption('온톨로지: 설정된 DB·작업 폴더 연결 사용. 나머지 메뉴는 기존 시안입니다.' if os.environ.get('GENOS_RAG_ONTOLOGY_CONFIG') else '온톨로지 설정이 없어 시안 데이터를 표시합니다.')")
p.write_text(s)
print('Prepared1158 baseline and fixture repairs')
