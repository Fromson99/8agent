from pathlib import Path
import json,hashlib,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0797-workflow-adopted-evidence'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=json.loads((A/'실험/manifest.json').read_text())
by={a:{'status':'complete','handoff':json.loads((A/('artifacts/replay/'+a+'.json')).read_text())} for a in ('baseline','optimized')}
by['optimized'].update(contract_passed=187,actual_compare_rows=0,technical_integrity_qualified=False)
r={'status':'complete','strict_success':False,'checks':{'contracts_pass':True,'handoff_within_limit':True,'actual_comparison_reached':False},'by_arm':by,'known_case_in_sample':True,'reason':'Both child request entries repeated nonliteral request quotes; no retrieval or comparison rows.','usage':{'product_model_calls':6,'offline_evaluator_calls':0}}
put(A/'artifacts/run-001/result.json',r)
m['design']['code_isolation']['reason']=None
m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
m['results'].update(status='complete',by_arm=by,usage=r['usage'],latency={'known_observation_seconds':147.37749652},error_taxonomy=['REQUEST_QUOTE_NONLITERAL','REPEATED_INVALID_PROPOSAL'])
m['decision_eligible']=False;put(A/'실험/manifest.json',m)
headings=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
body=['Rejected. 계약187건과 전달 최적화는 통과했으나 실제 비교0행. MAIN 미반영.',
 'MAIN73은 자식 전체 열람94근거를 대사로 복사해 입력 한도를 넘겼다.',
 '후보 수정 전 design/criteria.json 동결. 정확 원문·채택·revision·표시·복구·실제 비교를 확인한다.',
 'MAIN73 기준 및 rev005 후보. 합성 기술187계약, 알려진 같은 자식 기록 전달 재생, 실제 유동성 질문1회.',
 '원문/최신선택/정의연결 유지. Qwen3.8/Parasail FP8/reasoning none/no fallback. ExperimentClient 사용.',
 '187 tests passed. 재생94→16근거,45088→1132원문자,128976→26301입력자. 실제 실행 partial, 비교0행.',
 '내규 context_quotes의 생략 부호, 외규 request_quote의 비연속 합성이 검증에서 거부됐다. 수정에서도 같은 인용을 반복했다. 양쪽8항목을 자식 질문에 길게 반복 전달한 구성이 실패에 기여했다.',
 '모델6회,147.38초. STATUS/중복 동일, 추가모델0. 원문 요청·응답·실패는 artifacts/live/raw와 journal 보존.',
 '전달량 개선과 실제 비교 성공을 구분한다. 전달 추출에는 추가 모델0회.',
 '알려진 사례는 일반화 평가가 아니다. 적용 판본·의미 정답률 미인증.',
 'MAIN73 유지. 실패 후보와 원시 기록 보존. 후속 ADR에서 자식 질문을 간소화한다.',
 '06_TOOLS/EXPERIMENTS/adr_0797의 freeze/run_tests/replay/live. 완료 호출은 덮어쓰지 않는다.']
meta=f"---\nadr_id: ADR-0797\ntitle: 대사 채택 근거 전달과 제한 입력 처리\nstatus: Rejected\ndecision_date: 2026-10-15\nphase: audit\nin_sample: false\ndecision_eligible: false\nmain_wiring: unchanged\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n\n"
(A/'README.md').write_text(meta+'\n\n'.join(f'## {i}. {h}\n\n{b}' for i,(h,b) in enumerate(zip(headings,body),1))+'\n')
(A/'실험/README.md').write_text('# 전달 경계 감사\n\n[알려진 K01 재생·실제 실패](질문-001-K01.md). 기술계약과 의미 결과를 분리한다.\n')
subprocess.run(['.venv/bin/python','06_TOOLS/run_tool.py','adr_structure.py','status','--path',str(A),'--status','completed','--note','Rejected child quote failure; MAIN73 unchanged; preserve all records'],check=True)
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and 'runtime' not in p.parts]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0797','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Technical audit and failed live observation','contains_raw_prompts_and_outputs':'raw' in p.parts} for p in files]})
