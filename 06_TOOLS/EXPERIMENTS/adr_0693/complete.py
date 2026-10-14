from pathlib import Path
import json, hashlib, gzip, xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3]; A=R/'04_EXPERIMENTS/ADR/ADR-0693-main46-display-judgment-integration'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json'); bindings=read(A/'artifacts/contracts/bindings.json')
suites={}
for b in bindings:
 p=A/'artifacts/contracts'/(b['arm']+'.xml');cs=list(E.parse(p).iter('testcase'))
 suites[b['arm']]={'tests':len(cs),'failed':[c.get('name') for c in cs if c.find('failure') is not None or c.find('error') is not None],'junit_sha256':sha(p)}
 assert b['exit_code']==0
limitations=['No real model calls or legal quality measurements. MAIN and GENOS unchanged.',
 'One historical experience-reuse fixture fails before and after the judgment integration; separately reproduced and retained, excluded from declared final suite.',
 'Candidate code was physically isolated and frozen before final contracts. Experiment manifest isolation references were reconciled after contracts, not falsely asserted as a prior freeze; this probe cannot qualify for promotion.',
 'Paired MAIN46 comparison and independent public holdout are required in a later ADR.']
result={'status':'complete','suites':suites,'model_calls':0,'main_changed':False,'genos_deployed':False,'limitations':limitations}
put(A/'artifacts/contracts/result.json',result)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{**{k:v for k,v in b.items() if k not in ('arm','exit_code','code_root')},'candidate_id':b['arm'],'arm_id':b['arm'],'experiment_id':m['experiment_id'],'run_ids':['run-001']} for b in bindings])
m['design']['arms'][2]['derived_from']=['safe-display']
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','model_calls':0,'role':'Pinned MAIN46 inspection; no paired product requests'},**{k:{'status':'complete',**v,'model_calls':0} for k,v in suites.items()}},usage={'model_calls':0},latency={'not_measured_reason':'Contract-only probe'},error_taxonomy=['historical_experience_fixture','late_manifest_isolation_linkage'],limitations=limitations)
m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/contracts/result.json'))
put(A/'실험/manifest.json',m)
sections=[('결정 요약','오류 표시 분리와 v4 판단 후보의 고정 코드 계약 검사를 완료했다. 실제 모델·독립 검증 전 연구 후보이며 MAIN46은 유지한다.'),('문제와 기존 경로','채팅·SSE·진행 카드·저장 표시가 진단 본문을 드러내고, 승인 전 판단과 다른 부족의 근거가 섞일 수 있었다.'),('가설과 사전 기준','design/criteria.json의 표시 경계, 인용 보존, 부족별 근거·행동 영수증, 조건·선택·예외 및 사용자 사실 출처 검사를 적용했다.'),('설계와 비교 범위','safe-display에서 consistent-judgment를 분기했다. 전체 후보 파일·부모 차이는 design/integration-map.json에 있다. 기준 MAIN46은 실행 결속 감사 대상이며 실제 모델 A/B는 수행하지 않았다.'),('데이터와 재현성','MAIN46과 같은 원문 세대·공개 65문서 설정에 결속했다. 합성 계약만 실행했으며 외부 모델 호출은 0회다. contracts/bindings.json에 고정 코드와 실행기 해시가 있다.'),('검증 결과',f"표시 후보 {suites['safe-display']['tests']}개, 판단 후보 {suites['consistent-judgment']['tests']}개 모두 통과. 실제 원문 검색 품질은 미측정이다."),('오류 및 재개','기존 경험 재사용 fixture 1건의 동일 실패는 baseline/candidate 원문 로그로 별도 보존했다. 늦은 판단은 case revision·payload hash 검사로 거절하며 원인은 로그에 남긴다.'),('비용과 시간','모델 호출·토큰·비용 0. 테스트 시간은 JUnit에 있다. 모델 최적화 효과로 해석하지 않는다.'),('구현 해석','예외와 조건 그룹을 출처에 묶고 같은 승인 claim을 판단과 최종 답변에서 소비한다. 자료 확보·모델 전달·근거 채택을 혼동하지 않는다.'),('한계','; '.join(limitations)),('MAIN 및 롤백','작업 제품 경로·활성 포인터·GENOS 변경 없음. 후속 독립 검증과 hash 고정 승격 없이는 운영에서 선택하지 않는다.'),('재현','06_TOOLS/EXPERIMENTS/adr_0693/validate_frozen.py로 두 frozen revision 계약을 검사했다. 원시 실패/시도 로그는 logs/receipts.json의 gzip과 원문 hash로 복원한다.')]
fm=f"---\nadr_id: ADR-0693\ntitle: MAIN46 오류 표시 분리와 v4 판단 계약 구현\nstatus: Proposed\ndecision_date: 2026-10-08\nphase: probe\nin_sample: true\ndecision_eligible: false\nmain_wiring: unchanged\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n\n"
(A/'README.md').write_text(fm+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(A/'실험/README.md').write_text('# 합성 계약 검사\n\n실제 법률 질문·모델 실행 없음. [결과](../artifacts/contracts/result.json), [고정 코드](../artifacts/contracts/bindings.json).\n')
receipts=[]
for p in Path('/tmp').glob('adr693*.log'):
 t=A/'artifacts/logs'/(p.name+'.gz');t.parent.mkdir(exist_ok=True);data=p.read_bytes()
 with gzip.open(t,'wb') as f:f.write(data)
 receipts.append({'path':str(t.relative_to(R)),'sha256':sha(t),'original_sha256':hashlib.sha256(data).hexdigest(),'restore':'gzip -dc archive.gz > original.log'})
put(A/'artifacts/logs/receipts.json',receipts)
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0693','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Synthetic contracts and preserved development failures','contains_raw_prompts_and_outputs':False} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']})
print(result)
