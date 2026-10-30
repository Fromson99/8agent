"""Close preserved fixture failures without altering their frozen product/results."""
from pathlib import Path
import json,hashlib,subprocess
R=Path(__file__).resolve().parents[3]
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for number,slug,cause in [(1100,'main106-ontology-direct','모의 bundle_id에서 cb- 접두사를 빠뜨려 HTTP 구성 단계 실패'),(1103,'main106-ontology-live','모의 응답기가 compact 입력에서 생략한 빈 current_originals를 가정하여 실패'),(1104,'main106-ontology-wire','직접 답변 HTTP 성공; gap 경로 모의 응답기가 생략된 빈 dependency_cards를 가정하여 실패')]:
 A=R/f'04_EXPERIMENTS/ADR/ADR-{number}-{slug}';x=read(A/'artifacts/check-001.json');m=read(A/'실험/manifest.json')
 for c in m['integration']['conflicts']:c.update(id='main106-schema-preservation',between=m['integration']['parent_refs'],chosen_from='ADR-1092-experiment-v1/serving',rationale=c['resolution'])
 m['runs'][0].update(status='complete',selection_rule='Declared synthetic gates attempted; live cells not dispatched because fixture failed',artifact_path=str((A/'artifacts/check-001.json').relative_to(R)),sha256=sha(A/'artifacts/check-001.json'))
 m['results'].update(status='complete',by_arm={'baseline':{'status':'not_run','reason':'Live gate not passed'},'ontology':{'status':'failed','synthetic_passed':x['passed'],'synthetic_failed':x['failed'],'quality_certified':False}},usage={'new_model_calls':0,'input_tokens':0,'output_tokens':0,'cost_usd':0},latency={'synthetic_seconds':x['seconds']},error_taxonomy=[{'class':'TEST_FIXTURE','detail':cause}])
 m['retrieval_accounting'].update(changed=False,not_applicable_reason='Only synthetic interface gates executed; no real corpus retrieval or live cell dispatched')
 m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',summary_run_id=None,artifact_path=None,sha256=None,not_applicable_reason=m['retrieval_accounting']['not_applicable_reason'])
 m['llm_policy']['llm_calls']=[];put(A/'실험/manifest.json',m)
 header=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected')
 sections=[('결정 요약',f"합성{x['passed']}통과·{x['failed']}실패. {cause}. 외부 모델0회; 실패 보존."),('문제와 변경 전 구조','최신 MAIN106에는 온톨로지 직접 판단이 연결되지 않았다.'),('가설과 사전 판정 기준','[동결 기준](artifacts/criteria.json). 원문 확보 직후 기존 ASSESS에서 온톨로지와 원문을 함께 판단한다.'),('실험 설계','MAIN106 제품429파일 기준으로4제품파일과 온톨로지5모듈·1스키마만 연결했다. 구 후보의 조사·응답 스키마를 가져오지 않았다. [구성](artifacts/composition.json).'),('데이터·모델·재현성','작은 합성 원문·모의 응답기만 실행했다. CM023 실제 실행은 gate 실패로 미시작. [동결](artifacts/freeze.json).'),('결과',f"합성{x['passed']}통과·{x['failed']}실패, import 혼입{len(x['import_leaks'])}, 코드 변경{len(x['changed_files'])}. [검사](artifacts/check-001.json)."),('사례별 오류 분석',cause+' 제품 무결성 검사는 통과했지만 전체 gate는 실패다. 검사 자료를 바꾼 후속은 별도 ADR로 남겼다.'),('비용·지연·회수 규모',f"검사{x['seconds']:.3f}초, 모델·비용0. 실제 질의 시간 및 품질 미측정."),('해석','법률 판단 효과는 이 검사로 주장하지 않는다.'),('한계와 일반화 가능 범위','합성 검사와 실제 모델의 선택·답변 품질은 별개다.'),('운영 결정·롤백 조건','Rejected 검사 후보. 작업코드·MAIN106·GENOS 미반영. 실패 후보를 완료 부모로 사용하지 않는다.'),('재현 명령',f'동결 실행: `06_TOOLS/EXPERIMENTS/adr_{number}/check.py`. 보관 결과를 덮어쓰는 재실행은 하지 않는다.')]
 (A/'README.md').write_text('---'+header+'---\n\n# MAIN106 온톨로지 검사 실패 보존\n\n'+'\n\n'.join(f'## {i}. {t}\n\n{v}' for i,(t,v) in enumerate(sections,1))+'\n')
 (A/'실험/README.md').write_text('# 실행 기록\n\n'+cause+'\n\n실모델0회. 검사 실패를 보존했다.\n')
 for q in m['questions']:(A/'실험'/q['file']).write_text('# CM023 실행 예정 질문\n\n상장차익 증여의제는 어떤 요건에서 성립하는가?\n\n실제 질문은 미실행; 모의 gate 실패. 정답은 제품 입력에 포함하지 않았다.\n')
 art=read(A/'artifacts/manifest.json');art['files']=[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen design, source binding or preserved synthetic check','contains_raw_prompts_and_outputs':False} for p in (A/'artifacts').iterdir() if p.is_file() and p.name!='manifest.json'];put(A/'artifacts/manifest.json',art)
 for args in [('hash','--path',str(A)),('status','--path',str(A),'--status','completed','--note','Synthetic gate failure preserved; live0; no promotion'),('validate','--path',str(A),'--final')]:
  r=subprocess.run([str(R/'.venv/bin/python'),str(R/'06_TOOLS/run_tool.py'),'adr_structure.py',*args],cwd=R,capture_output=True,text=True);print(number,args[0],r.returncode,r.stdout+r.stderr)
