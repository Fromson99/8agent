"""Close interrupted runs without treating partial progress as a pass."""
from pathlib import Path
import json,hashlib,re
R=Path(__file__).resolve().parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for name in ('ADR-0857-host-assembly-qualification','ADR-0858-host-assembly-fulltext-live'):
 A=R/'04_EXPERIMENTS/ADR'/name;m=json.loads((A/'실험/manifest.json').read_text());inter=json.loads((A/'artifacts/interruption.json').read_text());m['decision_eligible']=False
 for run in m['runs']:
  p=R/run['artifact_path'];result={'status':'interrupted','strict_success':False,'complete_evaluation':False,'interruption':inter,'run_id':run['id'],'new_calls_allowed':False,'reexecute_in_new_ADR':True}
  assert not p.exists();put(p,result);run.update(status='complete',sha256=sha(p))
 arm=m['runs'][0]['arm_ids'][0];m['results'].update(status='complete',by_arm={arm:{'status':'complete','strict_success':False,'outcome':'interrupted before final evaluation'}},comparisons=[],usage={'confirmed_provider_calls':sum(r['completed_provider_receipts'] for r in inter.get('runs',[])),'unknown_outcome_calls':sum(len(r['unknown_outcome_calls']) for r in inter.get('runs',[]))},error_taxonomy=[{'type':'other','reason':'Resource pressure observed before interrupted turn; final evaluation unavailable. No claim of OS kill cause.'}])
 # Interrupted live audit has incomplete presentation receipts; retain raw logs,
 # and explicitly refrain from fabricating a measured retrieval ledger.
 if name.startswith('ADR-0858'):
  m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',summary_run_id=None,artifact_path=None,sha256=None,not_applicable_reason='Interrupted run; no complete presentation ledger. Raw partial calls and journal are retained; not counted as a fulltext pass.')
 put(A/'실험/manifest.json',m)
 heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
 texts=['중단. 완료 결과가 없어 통과·MAIN 승격으로 판정하지 않는다.','MAIN82를 기준으로0856동일 조립 후보를 검사했다.',json.dumps(m['design'],ensure_ascii=False),'사전 동결 코드·입력은 보존. 무거운 작업이 겹쳐 RAM/swap 압박이 관찰됐고 이후 턴 중단·환경 재시작이 확인됐다. OS 원인은 확정하지 않는다.','실제 호출·원응답·해시·중단 시점은 artifacts의 원기록에 보존.',json.dumps(inter,ensure_ascii=False),'끝나지 않은 항목은 미검증. 이미 완료된10서비스 검사와 정적 스키마 목록은 개별 근거이며 전체 통과를 뜻하지 않는다.','실모델 확인된 호출2회, 결과 미확인1회(0858). 미확인 호출을0비용으로 계산하거나 재시도 예산에서 지우지 않는다.0857실모델0회.','코드 결함 여부를 이번 중단으로 판정하지 않는다. 순차 실행·메모리 제한의 새 ADR에서 검증한다.','GENOS 미접근. 법률 정확도·속도·전 과정 완료 미검증.','MAIN82·작업 코드 불변. 완료 기록 덮어쓰기 없이 새 ADR로 이어간다.','원 실행기·freeze는 보존. resource_guard.py로 순차 실행할 새 ADR을 예약한 뒤 실행한다.']
 meta=(A/'README.md').read_text().split('---',2)[1]
 for k,v in [('status','Rejected'),('decision_eligible','false')]:meta=re.sub(r'(?m)^'+k+r':.*$',k+': '+v,meta)
 (A/'README.md').write_text('---'+meta+'---\n\n# 중단 기록\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n')
 for q in m['questions']:
  text='# '+q['case_id']+'\n\n'
  for h,body in [('1. 실행 메타','동결 입력·코드 / 중단 / raw 상태 exact. 최종 결과 없음.'),('2. 사용자 질문 원문','원문은 artifacts/design의 frozen 또는 criteria와 해시 고정 실행기에 보존. 새 호출·수정 없음.'),('3. 기준답변 — 채점 전용, 제품 입력 비공개','법률 gold 없음. 계약 검사만 수행.'),('4. 제품 입력을 구성한 원값','artifacts/design 및 부분 journal 참조.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n중단으로 전체 원장 미확정. 부분 조회·모델 입력은 raw에 보존하며 성공으로 합산하지 않는다.'),('5. 제품 모델 호출 — run·arm별 실제 원문','0857합성 검사.0858 provider/request.json·response.json·usage.json과 wire/*.json.gz에 존재하는 부분 호출만 보존. 미확인 전송1건 있음.'),('6. 중간 LLM 호출 — router/compiler/verifier/repair','0858 calls.json·generations.json 참조. 완료되지 않은 호출을 추정하지 않는다.'),('7. 채점 호출과 반복 판정','모델 채점0회. 재실행 없음.'),('8. 사례 최종 판정','미완료·MAIN 불변. artifacts/interruption.json 참조.')]:text+='## '+h+'\n\n'+body+'\n\n'
  (A/'실험'/q['file']).write_text(text)
 (A/'실험/README.md').write_text('# 중단 검사\n\n원시 로그와 부분 완료 기록 보존. 전체 통과 아님.\n')
 put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not p.name.endswith('.lock')]})
