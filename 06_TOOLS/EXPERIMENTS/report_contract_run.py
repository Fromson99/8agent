"""Write a technical ADR report from retained test/consumer receipts."""
from pathlib import Path
import json,hashlib,re,sys
R=Path(__file__).resolve().parents[2];A=R/sys.argv[1];notes=json.loads(Path(sys.argv[2]).read_text());status=notes['status']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
log=(A/'artifacts/candidate-api.log').read_text();passed=int(re.findall(r'(\d+) passed',log)[-1]);matches=re.findall(r'(\d+) failed',log);failed=int(matches[-1]) if matches else 0
m=json.loads((A/'실험/manifest.json').read_text());arm=m['runs'][0]['arm_ids'][0];f=json.loads((A/'artifacts/design/freeze.json').read_text())
consumer=json.loads((A/'artifacts/candidate-consumer.json').read_text()) if (A/'artifacts/candidate-consumer.json').exists() else None
if status=='Accepted':
 assert failed==0 and consumer and consumer['status']=='PASS' and all(consumer['checks'].values())
 assert all(sha(R/n)==h for n,h in f['files'].items())
result={'status':'complete','strict_success':status=='Accepted','passed':passed,'failed':failed,'real_model_calls':0,'consumer':consumer,'notes':notes,'frozen_candidate':f['candidate']}
put(A/'artifacts/run-001/result.json',result)
m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'));m['results'].update(status='complete',by_arm={arm:result},comparisons=[],usage={'product_model_calls':0,'offline_evaluator_calls':0},error_taxonomy=[] if not failed else [{'type':'other','reason':notes['findings']}]);
if status!='Accepted':m['decision_eligible']=False
put(A/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
text=[f'{status}. {passed}통과·{failed}실패. '+notes['findings'],'MAIN82의 전체 워크플로우·데이터·검색 정책 위에서 출력 조립 계약만 수정한다.',json.dumps(m['design'],ensure_ascii=False),'유한 기술 계약 전수와 명시한 기존 회귀. 법률 정답 holdout이 아니며 의미 정확도·현장 성능을 인증하지 않는다.','freeze.json의 후보711파일, 데이터·프로필·실행기·검사 SHA를 보존. 모델0회.',json.dumps(result,ensure_ascii=False),notes['findings'],'실제 RAM/시간은 resources.json 및 각 실행 로그. 실모델 fulltext는 별도 ADR. 새 원문 회수·법률 채점 없음.','생성 제약·기계적 조립과 최종 실행 검증을 각각 확인하며 의미를 만들지 않는다.',json.dumps(notes['limitations'],ensure_ascii=False),'Accepted인 경우만 같은 코드 작업 반영/검증/명시적MAIN승격/서비스선택 확인으로 진행한다. GENOS는 별도 반입·현장검증. 실패 기록과 기존MAIN은 보존.','setup.py;repin.py;seal.py;preview.py;resource_guard.py→run_validation.py candidate;consumer.py candidate;report_contract_run.py;stable status/hash/validate --final/graph.']
meta=(A/'README.md').read_text().split('---',2)[1]
for k,v in [('status',status),('decision_eligible',str(m['decision_eligible']).lower()),('in_sample',str(m['in_sample']).lower())]:meta=re.sub(r'(?m)^'+k+r':.*$',k+': '+v,meta)
(A/'README.md').write_text(('---'+meta+'---\n\n# 시스템 조립 계약 기술 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{b}' for i,(h,b) in enumerate(zip(heads,text),1))+'\n').replace('PENDING','대기 종료'))
for q in m['questions']:
 body='# '+q['case_id']+'\n\n'
 for h,b in [('1. 실행 메타','run-001 / '+arm+' / exact synthetic technical proposals / 원시 로그 보존'),('2. 사용자 질문 원문','전체 스키마와 시스템 복원 계약을 맞추고 최근MAIN을 유지한다.'),('3. 기준답변 — 채점 전용, 제품 입력 비공개','법률 gold 없음. 사전 동결한 기술 상태와 정확한 schema/canonical 계약만 검사.'),('4. 제품 입력을 구성한 원값','artifacts/design/criteria.json·freeze.json·execution-plan.json의 전체 검사·입력·코드 해시.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n모델 회수 효과 비교 아님. 합성 fixture와 보존된 이전 응답의 재구성. 실제 fulltext 원장은 별도 실모델 ADR.'),('5. 제품 모델 호출 — run·arm별 실제 원문','새 모델 호출0회. 합성 입력은 SHA고정된 테스트 파일, 이전 raw응답은 원래ADR에 보존. 보고서에서 본문 중복하지 않음.'),('6. 중간 LLM 호출 — router/compiler/verifier/repair','모델0회. 합성 정상/복구/실패·권한·상태·예산 경계는 실제 adapter로 검사.'),('7. 채점 호출과 반복 판정','모델 채점0회. 원시 test 로그를 그대로 보존.'),('8. 사례 최종 판정',json.dumps(result,ensure_ascii=False))]:body+='## '+h+'\n\n'+b+'\n\n'
 (A/'실험'/q['file']).write_text(body.replace('PENDING','대기 종료'))
(A/'실험/README.md').write_text(f'# 기술 검증\n\n{passed}통과·{failed}실패. artifacts/run-001/result.json과 원시 로그 참조.\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not p.name.endswith('.lock')]})
