"""Preserve each frozen run, including failed implementation checks."""
from pathlib import Path
import hashlib,json,sys
R=Path(__file__).resolve().parents[3];number=sys.argv[1];slug=sys.argv[2]
A=R/f'04_EXPERIMENTS/ADR/ADR-{number}-{slug}';D=R/f'06_TOOLS/EXPERIMENTS/adr_{number}'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
x=json.loads((A/'artifacts/check-001.json').read_text());ok=not(x['status'] or x['failed'] or x['import_leaks'] or x['changed_files'])
m=json.loads((A/'실험/manifest.json').read_text());m['runs'][0].update(status='complete',artifact_path=str((A/'artifacts/check-001.json').relative_to(R)),sha256=sha(A/'artifacts/check-001.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','scope':'Inherited exact completed1091; no new baseline model call'},'direct':{'status':'complete' if ok else 'failed','contract_passed':x['passed'],'contract_failed':x['failed'],'quality_certified':False,'decision_eligible':False}},usage={'new_model_calls':0,'input_tokens':0,'output_tokens':0,'cost_usd':0},latency={'synthetic_contract_seconds':x['seconds'],'service_measured':False},error_taxonomy=[{'test':r['test'],'detail':r['error'][-1800:]} for r in x['rows'] if r['status']=='failed'])
put(A/'실험/manifest.json',m)
header=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: '+('Proposed' if ok else 'Rejected'))
outcome=f"합성 {x['passed']}개 통과·{x['failed']}개 실패. " + ('직접 판단·추가 조사·발행 경로의 합성 계약을 확인했다.' if ok else '실패를 보존하고 후속 ADR에서 수정한다. 이 후보는 완료 부모로 사용하지 않는다.')
sections=[('결정 요약',outcome+' 실모델0회·법률 품질 미인증. 작업코드·MAIN106·GENOS 미반영.'),
('문제와 변경 전 구조','승인 온톨로지 원문을 확보한 뒤 조사 메뉴와 별도 판단을 반복했으며 ASSESS에는 온톨로지 구조를 전달하지 않았다. 원문·기존 의견은 보존되어 있었다.'),
('가설과 사전 판정 기준','[사전 기준](artifacts/criteria.json). 기존 ASSESS에서 원문·온톨로지로 답변 내용과 부족을 함께 판단한다. 추가 조사는 기존 gap 경로·한도·담당을 유지한다.'),
('실험 설계','완료1091/integrated를 부모로 삼고 ontology_direct_assessment 선택 설정의 후보를 격리했다. 사용자1번 스키마 변경은 제외. 원문 확보가 충분성·채택·검토 완료를 뜻하지 않도록 pending을 유지한다.'),
('데이터·모델·재현성','작은 합성 원문·승인 묶음과 모의 transport만 사용한다. 실제 HTTP /v1/rag/ask, 전송 compact 입력, 최종 저장·중복 요청 소비자를 검사한다. 단계명만 모의 응답 라우팅에 전달한다. [동결 코드와 검사](artifacts/freeze.json).'),
('결과',outcome+f" import 혼입{len(x['import_leaks'])}·동결파일 변경{len(x['changed_files'])}. [전체 결과](artifacts/check-001.json)."),
('사례별 오류 분석','검사 실패 원문은 check-001.json에 보존한다. '+('통과는 모의 선택기의 경로·자료 보존 증거다.' if ok else (A/'artifacts/failure-summary.txt').read_text())),
('비용·지연·회수 규모',f"합성 검사{x['seconds']:.3f}초. 새 모델0·외부비용0. 서비스 시간·토큰·법률 정답률을 측정하지 않았다. 전체 corpus를 읽지 않았다."),
('해석','묶음 수신 뒤 답변 가능 여부와 답변 내용을 기존 ASSESS 한 번에서 판단한다. structured COMPOSE는 추가 모델 없이 표현을 조립한다. narrative 설정이면 기존 표현용 호출이 남는다. 질문 접수·초기 원문 선택까지 전체 한 호출이라는 뜻은 아니다.'),
('한계와 일반화 가능 범위','실제 모델의 충분성·A1 선택 적절성·법률 품질은 미검증이다. 1번의 스키마 간소화·판단 연결·gap 중요도 수정은 다른 작업 완료 후 확인할 대상이다. 기존 graph의 오류와 본 ADR 검사 결과를 구분한다.'),
('운영 결정·롤백 조건','후보만 작성했다. 선택 MAIN106 및 GENOS를 변경하지 않았다. 원문/권한/해시 불일치는 기존 실패 경로로 차단한다. 불충분 자료는 제한 답변 또는 기존 조사복귀로 남긴다. 복구점은 완료1091이다.'),
('재현 명령',f'`.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_{number}/check.py new-receipt.json`\n\n효과 재비교·변경 후보는 새 ADR에서 동결한다.')]
(A/'README.md').write_text('---'+header+'---\n\n# 온톨로지 직접 판단 전달\n\n'+'\n\n'.join(f'## {i}. {t}\n\n{v}' for i,(t,v) in enumerate(sections,1))+'\n')
(A/'실험/README.md').write_text('# 합성 연결 검사\n\n'+outcome+'\n\n실제 질문·기준답변 없이 모의 계약을 검사했다. [결과](../artifacts/check-001.json).\n')
am=json.loads((A/'artifacts/manifest.json').read_text());am['files']=[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen criteria, code binding, synthetic check and preserved failure','contains_raw_prompts_and_outputs':False} for p in [*list((A/'artifacts').iterdir()),*D.glob('*.py')] if p.is_file() and p.name!='manifest.json'];put(A/'artifacts/manifest.json',am)
print(outcome)
