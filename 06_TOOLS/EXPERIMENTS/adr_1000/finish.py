from common import *
import sys,tarfile,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS,QUESTION_HEADINGS_V4
f=read(ART/'design-freeze.json');s=read(ART/'stage.json');o=read(ART/'observations.json');r=o['native_result'];integ=read(ART/'integration.json')
assert read(ART/'stop.json')['reason']=='PROVIDER_FAILURE'
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
assert all(sha(ROOT/s['roots']['candidate']/n)==h==sha(ROOT/n) for n,h in f['files']['candidate'].items())
assert o['main_unchanged'] and r['service_status']==503 and r['model_calls']==1 and not r['usage']
# A failed provider attempt returned no usage. Empty sums are not measured zero cost.
for k in ('model_seconds','non_model_elapsed_seconds','input_tokens','output_tokens','cost_usd'):o[k]=None
o['usage_status']='NOT_RETURNED_BY_PROVIDER';save(ART/'observations.json',o)
findings=[
 'ADR0999에서 확인한 조 전체 연결의 빈 block_ids를 미열람으로 처리하는 결함을 수정 전 재현했다. 전체 범위 확보는 실패하고 부분 범위는 미확보로 유지되는 회귀1실패/1통과를 기록했다.',
 '원문 읽기·연결 카드·권한 범위·의무 검사·재읽기 메뉴가 같은 정규 endpoint 범위와 실제 확보 codepoint를 사용하도록 통일했다. 특정 법령 번호나 질문의 예외 분기는 추가하지 않았다.',
 '실제 저장된92②1→97 연결의22블록 전체 확보/1블록 누락을 검증했다. 동일한 조 전체 빈 endpoint 표현52,476개를 확인했다. 원문·관계 색인을 수정하지 않았다.',
 '동결 후보106검사, 선택 통합한 작업 코드106검사를 각각 통과했다. 합성 native API5경로는 연결 연속 탐색·원문/질문 전달·실패 후 구조검색·읽은 연결 재선택 제거·중복 요청을 확인한다. 기존 무효 fixture1건은 사전 실패 근거와 함께 제외했다.',
 '동일 질문의 실제 실행은 첫 request-entry 호출에서 Parasail HTTP429로 중단됐다. native 서비스503, 물리 호출1회,17.414초, 이후 호출0이다. 실제97→163 도달 및 답변 성공은 미검증이다. usage 미반환으로 토큰/비용/모델 처리 시간은 미측정이다.',
 '일반 결함 수정은 검증한428파일과 동일하게 작업 코드에 선택 통합했다. MAIN101 포인터는 실험 동안 불변이며 최신 사용자의 MAIN 반영·삼성 발송 지시는 별도 전환 기록에서 처리한다.'
]
limits=['전체 실제 질의 성공 기준 미충족. probe/in_sample/decision_eligible=false이며 법률 정답·품질 인증 없음.',
 'ADR0999의 ASSESS 반복 출력/출력 한도 실패와 기존 불필요한 조사 확대·수치 오류가 해결됐다는 증거는 없다.',
 '후속 MAIN 전환은 사용자 명시 지시이며 실험의 성공 판정으로 소급하지 않는다. GENOS 현장 반입·내부 모델·배포 미검증.',
 '전역 graph의 기존9개 오류와 신규 ADR 검사를 분리한다.']
summary={'status':'COMPLETE','verdict':'DETERMINISTIC_COVERAGE_FIXED; LIVE_EFFECT_UNTESTED_PROVIDER_429','findings':findings,'limitations':limits,'physical_calls':1,'service_status':503,'seconds':r['seconds'],'input_tokens':None,'output_tokens':None,'cost_usd':None,'usage_status':'NOT_RETURNED_BY_PROVIDER','native_answer_success':False,'criteria_met':False,'quality_certified':False,'working_code_integrated':True,'main_changed_during_experiment':False,'genos_changed':False,'candidate_contracts_passed':106,'working_contracts_passed':106,'frozen_candidate_files':428}
save(ART/'result.json',summary)
P=ART/'known-query/candidate';runtime=P/'runtime';archive=P/'runtime.tar.gz'
if runtime.exists():
 assert not archive.exists()
 hashes={str(p.relative_to(P)):sha(p) for p in runtime.rglob('*') if p.is_file()}
 with tarfile.open(archive,'w:gz',compresslevel=6) as t:t.add(runtime,arcname='runtime')
 with tarfile.open(archive,'r:gz') as t:
  for name,h in hashes.items():
   with t.extractfile(name) as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==h
 save(P/'runtime-archive.json',{'archive':'runtime.tar.gz','sha256':sha(archive),'verified_files':hashes,'restore':'Extract into an empty directory; runtime relative paths preserved.','process_finished':True})
 shutil.rmtree(runtime)
m=read(ADR/'실험/manifest.json');assert m['design']['success_criteria']==f['design']['success_criteria']
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','new_calls':0,'historical_reference_only':True},'candidate':{'status':'complete','correct':None,'total':1,'accuracy':None,'accuracy_not_scored_reason':'Provider429 before investigation. No approved gold; deterministic coverage verified separately.','new_calls':1,'quality_certified':False}},comparisons=[],judge_disagreements=0,usage={'physical_calls':1,'input_tokens':None,'output_tokens':None,'cost_usd':None,'status':'NOT_RETURNED_BY_PROVIDER'},latency={'service_seconds':r['seconds'],'model_seconds':None,'request_p50_seconds':r['seconds'],'request_p95_seconds':r['seconds'],'sample_size':1},error_taxonomy=[{'kind':'other','description':'Provider429 first call; no investigation or answer. Coverage code defect corrected in deterministic contract/API tests; native effect untested.'}])
m['retrieval_accounting'].update(corpus_total=o['corpus_total'],before_filter=0,after_filter=0,presented_total=0,presented_mean=0,presented_p50=0,presented_p95=0,golden_recall={'candidate':None},selectivity=0)
m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
front=(ADR/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected')
parts=[summary['verdict'],'\n\n'.join(findings[:2]),m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],m['design']['sampling'],'428파일 동결, 동일 데이터·65공개문서·모델·예산. [동결](artifacts/design-freeze.json).','\n\n'.join(findings),'[실제 데이터](artifacts/real-data-contract.json), [작업 통합](artifacts/integration.json), [106검사](artifacts/working-contracts.txt), [원시 모델 오류](artifacts/known-query/candidate/model/call-001-service/response.json).',json.dumps(summary,ensure_ascii=False,indent=2),'결정적 결함은 검증했으나 실제 질의의 사전 성공 기준은 확인하지 못했다. 기준 변경·재시도·품질 승격 없이 종료한다.','\n\n'.join(limits),'작업 코드 통합 완료. MAIN101 실험 동안 유지. 이후 사용자 지시 MAIN 전환은 별도 감사에서 기록한다.','prepare → regression → fix → contracts → freeze → one guarded live attempt → offline audit → selective working integration → working contracts → finish/status/hash/validate/graph.']
(ADR/'README.md').write_text('---'+front+'---\n\n# 연결 대상 범위·확보 상태의 공통 판정 수정\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(ADR_HEADINGS,parts)))
row=m['questions'][0];values=['run-001/candidate; native local service public question once.',read(ART/'known-request.json')['json']['question'],'법률 gold 없음. provider 실패로 정답 평가 불가.','[요청](../artifacts/known-request.json), [실제 데이터 검사](../artifacts/real-data-contract.json).','[확보→인용 원장](../artifacts/retrieval-ledger.json). provider 실패로 실제 조사0.','[요청 원값](../artifacts/known-query/candidate/model/call-001-service/request.json), [응답 원값](../artifacts/known-query/candidate/model/call-001-service/response.json).','물리 호출1; 모델usage 미반환; native503;17.414초. 원시 기록과 무손실 runtime archive 보존.','추가 모델 judge 없음. 법률 정답 미평가.','\n\n'.join(findings+limits)]
qp=ADR/'실험'/row['file'];qp.write_text('# 양도차익 필요경비\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,values)));row['sha256']=sha(qp)
(ADR/'실험/README.md').write_text('# 사례\n\n- [질문·입출력·판정]('+row['file']+')\n');save(ADR/'실험/manifest.json',m)
(ADR/'RESULT.txt').write_text('\n\n'.join(findings+limits)+'\n')
index=ROOT/'04_EXPERIMENTS/ADR/README.md';txt=index.read_text();line='- [ADR-1000 연결 대상 범위·확보 상태 공통 판정](ADR-1000-canonical-reference-read-coverage/README.md) — 결정적 결함 수정106검사; 실제 재실행은 첫 호출429, 효과 미검증. 품질승격 불가.\n'
if 'ADR-1000 연결 대상' not in txt:index.write_text(txt.replace('# ADR workspace\n','# ADR workspace\n'+line))
files=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'description':'Frozen design/code, contracts, native provider failure, working integration','contains_raw_prompts_and_outputs':'model' in p.parts or p.name=='runtime.tar.gz'} for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json']
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':files})
print(summary['verdict'])
