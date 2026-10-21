from pathlib import Path
import json,hashlib,subprocess
R=Path.cwd();A=R/'04_EXPERIMENTS/ADR/ADR-0810-evidence-completeness-comparison'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=json.loads((A/'실험/manifest.json').read_text())
result={'status':'complete','strict_success':False,'checks':{'unit_boundaries':True,'actual_workflow_entry':False},'tests':{'passed':76,'failed':17},'model_calls':0,'reason':'Frozen candidate workflow manifest advanced to1.2.0 but ingress default remains1.1.0; all17 native API tests fail WORKFLOW_NOT_REGISTERED. Model probe cancelled before any call. No MAIN integration.', 'quality_certified':False}
put(A/'artifacts/run-001/result.json',result)
m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','basis':'Selected MAIN75 preserved; no new model execution'},'connected':{'status':'complete','strict_success':False,'checks':result['checks']}},usage={'product_model_calls':0,'offline_evaluator_calls':0},error_taxonomy=[{'kind':'other','detail':result['reason']}])
put(A/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['Rejected: 신규 경계76통과, 실제 API17실패. 실행 버전 배선 보정이 필요하다. MAIN75 불변.',
'별표 위치 거부, 정의 최초8개 제한, 쟁점ID 재추측, 고정글자수 절단, 수치차이 판정 차단, 미검증 부재주장 재표시가 있었다.',
'artifacts/design/criteria.json에 구현 전 동결. 권한·원문·해시·재개 무결성 및 실제 API가 필수다.',
'현재 MAIN75 338파일에서 격리. 후보rev001. 기존 실패 기반 구조probe이며 in_sample=true/decision_eligible=false다.',
'원문 세대/프로필 보존. 모의 수치3사례 x2arms 모델 호출을 계획했으나 API배선실패로 첫 호출 전에 취소. 모델실행0.',
result['reason'],
'일반화 구현 경계76통과. API는 요청버전 기본값1.1.0과 등록1.2.0이 달라17건 모두404. 별개 후속 ADR에서 정본 등록 버전 선택을 수정한다.',
'검색 효과/회수율/법률정답률 미측정. 일반 계약 검사이며 원문/정답 샘플의 임의 절단 없음.',
'실제 소비자 연결을 검사하여 미등록 워크플로우를 발견했다. 단위검사 통과만으로 활성화하지 않는다.',
'로컬 필요한 내규 데이터와 판본 유효성 메타데이터는 미해결. GENOS 접근/배포없음.',
'MAIN75/작업코드 불변. 완료후 동일snapshot에덮어쓰지않고 새ADR로연결한다.',
'prepare→repin→candidate freeze/validate→freeze.py→run_tests.py→consumer_check.py candidate; artifacts/tests.txt 및consumer.txt.']
meta=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected')
(A/'README.md').write_text('---'+meta+'---\n\n# ADR-0810 원문 완결성과 비교 경계\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n')
(A/'RESULT.txt').write_text('\n\n'.join(texts)+'\n');(A/'실험/README.md').write_text('# 구조 검증\n\n질문 단위 모델 실행은 API 결함으로 호출 전에 취소했습니다.\n')
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not p.name.endswith(('-wal','-shm','.lock'))]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0810','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen boundary and API failure evidence','contains_raw_prompts_and_outputs':False} for p in files]})
