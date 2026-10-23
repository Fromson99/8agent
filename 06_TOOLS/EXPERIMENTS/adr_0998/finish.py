from common import *
import sys,tarfile,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS,QUESTION_HEADINGS_V4
f=read(ART/'design-freeze.json');s=read(ART/'stage.json');o=read(ART/'observations.json');r=o['native_result'];a=read(ART/'selected-scope-audit.json');integration=read(ART/'integration.json')
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
assert all(sha(ROOT/s['roots']['candidate']/n)==h for n,h in f['files']['candidate'].items())
assert o['source_checks']['mismatches']==o['source_checks']['scope_violations']==0
findings=[
'연결 탐색 범위는 모델이 고른 실제 제시 원문 span으로 고정한다. 편·장·절·관·조·항·호·목 및 복수 범위·제외 선택을 공통 구조 계약으로 처리한다. 문맥용 상위 제목/도입부와 다른 자동 획득 원문은 연결 루트에 자동 합치지 않는다.',
'기존 FOLLOW_CONNECTION 선택으로 범위를 지정한 뒤 검증된 연결 메뉴를 연다. 해당 범위 바깥의 넓은 역참조는 작은 항·호의 직접 연결처럼 보여주지 않는다. 새로 읽은 연결 대상도 모델이 그 범위를 선택하기 전에는 다음 연결 루트로 자동 확장하지 않는다.',
'연결 없음은 현재 범위·색인에서 검증된 연결 미확인으로 표시한다. 시간 초과 등 복구 가능한 실패는 기존 단일 복구 담당이 기록하고 동일 실패 동작을 차단한다. 기존 LOCATE/CATALOG_SEARCH와 READ를 계속 제공하며 압축 입력에도 복구 사유를 전달한다. 권한·해시·상태 오류는 검색 성공으로 바꾸지 않는다.',
'실제 사진 전사 질문은92조2항1호의97조 참조를 읽고 LOCATE(구조 선택)→READ로97조에 도달했다.92조 연결 메뉴를 먼저 고른 실행은 아니므로 연결 우선 사용을 강제했다고 설명하지 않는다. 이후 모델이97조를 선택해 그 범위의 연결 메뉴에서 시행령163조를 FOLLOW하고 원문을 확보했다.',
'최종 답변은HTTP422/review_incomplete로 실패했다. ASSESS와허용된1회보정 모두 모델이 설명을 반복하다6400출력토큰 한도에서 잘렸다. 추가 질문 재실행은 하지 않았다. 성공/제한답변으로 표시하지 않는다.',
'시행령163조를 제시한 뒤에도 모델은163조 확보 필요라는 이유로97조의 남은 연결 메뉴를 계속 탐색했다. 단일 사례의 조사 확대 및 지연은 개선 완료로 판정하지 않는다. 구조/원문 경계의 구현 검증과 의미 판단·효율 검증을 구분한다.'
]
limits=['외부 Qwen3.8/Parasail FP8의 일반 로컬 service/API 실행이다. GENOS 내부 모델·워크플로우·현장 배포 검증은 아니다.',
'사진 앱에 표시된 질문을 전사한 알려진1문항이며 승인된 법률 gold나 out-of-sample 비교가 없다. 답변 정확도와 속도 개선을 인증하지 않는다.',
'회귀405통과/2실패. 두 실패는 수정 전 작업 코드에서도 재현되는 기존 fixture의 structure_selections 누락과 오래된37개 도구 등록 기대값이다. 별도최종범위12검사통과, 모의API3경로통과. 원시 실패 로그를 보존했다.',
'작업 코드에 선택적으로 통합했으며422파일 후보와 동일성을 확인했다. 선택 MAIN101 포인터와 GENOS 현장은 변경하지 않았다.']
summary={'status':'COMPLETE','verdict':'STRUCTURAL_PATH_VERIFIED; NATIVE_ANSWER_FAILED; EFFICIENCY_UNRESOLVED','findings':findings,'limits':limits,
 'physical_calls':r['model_calls'],'service_status':r['service_status'],'seconds':r['seconds'],'model_seconds':o['model_seconds'],
 'input_tokens':o['input_tokens'],'output_tokens':o['output_tokens'],'cost_usd':o['cost_usd'],'source_checks':o['source_checks'],
 'scope_catalog_count':o['scope_catalog_count'],'outcome':o['outcome'],'integration':integration,
 'main_changed':False,'genos_changed':False,'quality_certified':False,'legal_answer_certified':False,'native_answer_success':False}
save(ART/'result.json',summary)
P=ART/'known-query/candidate';runtime=P/'runtime';archive=P/'runtime.tar.gz'
if runtime.exists():
 assert not archive.exists()
 hashes={str(p.relative_to(P)):sha(p) for p in runtime.rglob('*') if p.is_file()}
 with tarfile.open(archive,'w:gz',compresslevel=6) as t:t.add(runtime,arcname='runtime')
 with tarfile.open(archive,'r:gz') as t:
  for name,d in hashes.items():
   with t.extractfile(name) as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==d
 save(P/'runtime-archive.json',{'archive':'runtime.tar.gz','sha256':sha(archive),'verified_files':hashes,'restore':'Extract runtime.tar.gz under an empty directory; original relative runtime paths preserved.','process_finished':True})
 shutil.rmtree(runtime)
m=read(ADR/'실험/manifest.json');assert m['design']['success_criteria']==f['design']['success_criteria']
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','new_calls':0,'historical_reference_only':True},'candidate':{'status':'complete','correct':None,'total':1,'accuracy':None,'accuracy_not_scored_reason':'No approved legal-answer gold. Structure/failure contracts independently tested.','new_calls':r['model_calls'],'quality_certified':False}},comparisons=[],judge_disagreements=0,usage={'physical_calls':r['model_calls'],'input_tokens':o['input_tokens'],'output_tokens':o['output_tokens'],'cost_usd':o['cost_usd']},latency={'service_seconds':r['seconds'],'model_seconds':o['model_seconds'],'request_p50_seconds':r['seconds'],'request_p95_seconds':r['seconds'],'sample_size':1},error_taxonomy=[{'kind':'other','description':'After163 was delivered, unnecessary remaining97links exploration continued. ASSESS and its single repair both hit6400output token cap through repetitive prose; nativeAPI422 review_incomplete. Two regression fixtures fail unchanged in parent.'}])
n=len(o['final_coordinates']);m['retrieval_accounting'].update(corpus_total=o['corpus_total'],before_filter=len(o['read_coordinates']),after_filter=n,presented_total=n,presented_mean=n,presented_p50=n,presented_p95=n,golden_recall={'candidate':None},selectivity=n/o['corpus_total'])
m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
front=(ADR/'README.md').read_text().split('---',2)[1]
parts=[findings[0], '사용자는 읽은 원문 중 활용할 구조 범위만 연결 출발점으로 선택하고 연결 누락/실패 시 기존 구조 검색으로 복구하도록 요청했다. 전체 구조단위를 대상으로 한다.',m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],m['design']['sampling'],
'동일 MAIN101 데이터/65공개문서 범위, 후보422파일과 Qwen3.8 고정. [동결](artifacts/design-freeze.json), [실제 실행](artifacts/observations.json), [원문 감사](artifacts/source-audit.json).',
'원문 획득→LLM 탐색/범위 선택→선택 범위 연결 검증→모델의 대상 읽기 판단→새 원문 읽기. 실패/누락 시 구조 조회·READ. 기존 원문과 복구/예산 상태는 보존한다.',
'\n\n'.join(findings),json.dumps({k:summary[k] for k in ('physical_calls','seconds','model_seconds','input_tokens','output_tokens','cost_usd','source_checks','scope_catalog_count')},ensure_ascii=False,indent=2),
'구조 범위·연결 원문과 복구 흐름은 구현·검증했다. 실제답변은모델반복출력으로실패했다. 연결 우선 사용 강제·불필요한 추가 조사·속도·최종답변의 정상완료는 미해결이다.', '\n\n'.join(limits),
'[작업 코드 통합·롤백](artifacts/integration.json). MAIN101/GENOS 미변경. 요청 범위 밖 데이터·모델·기존 작업은 덮어쓰지 않았다.',
'prepare.py→implement.py와 계약 수정→repin.py→run_contracts.py→freeze.py→validate→guard.py(1회)→analyze.py→integrate.py→작업API검사→finish.py→validate --final/graph.']
(ADR/'README.md').write_text('---'+front+'---\n\n# 선택 구조 범위의 연결과 구조 검색 복구\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(ADR_HEADINGS,parts)))
row=m['questions'][0];rawlinks=[f'[{p.relative_to(P)}](../artifacts/{p.relative_to(ART)})' for p in sorted((P/'model').glob('*/*.json'))]
values=['run-001/candidate; one natural local service/API request.',json.dumps(read(ART/'known-request.json'),ensure_ascii=False,indent=2),'Legal gold absent. Contract criteria frozen before execution. No answer/coordinate injection into product input.',
'[Exact calls](../artifacts/calls.json), [scope audit](../artifacts/selected-scope-audit.json), [original audit](../artifacts/source-audit.json).',
'[Read/citation stage ledger](../artifacts/retrieval-ledger.json); not all search hits or approved answer recall.', '\n\n'.join(rawlinks),
'One native execution, full raw model I/O and event log preserved. Runtime archived losslessly after exit. No query rerun.',
'Offline code/data/trace review and deterministic contract/API tests, no model judge or quality certification.', '\n\n'.join(findings+limits)]
qp=ADR/'실험'/row['file'];qp.write_text('# 양도차익 필요경비\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,values)));row['sha256']=sha(qp)
(ADR/'실험/README.md').write_text('# 사례\n\n- [질문·입출력·검증]('+row['file']+')\n');save(ADR/'실험/manifest.json',m)
(ADR/'RESULT.txt').write_text('\n\n'.join(findings+limits)+'\n\n'+json.dumps({k:summary[k] for k in ('physical_calls','seconds','source_checks')},ensure_ascii=False)+'\n')
index=ROOT/'04_EXPERIMENTS/ADR/README.md';txt=index.read_text();line='- [ADR-0998 선택 구조 범위 연결과 구조 검색 복구](ADR-0998-selected-scope-connection-fallback/README.md) — 전체 구조 단위·실패 복구 구현, 실제97→시행령163연결 확인. 최종답변422실패·추가조사/속도미해결; 작업코드 통합, MAIN101/GENOS 불변.\n'
if 'ADR-0998 선택 구조' not in txt:index.write_text(txt.replace('# ADR workspace\n','# ADR workspace\n'+line))
files=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'description':'Frozen implementation, tests, native evidence, integration receipt or offline audit','contains_raw_prompts_and_outputs':'model' in p.parts or p.name in ['runtime.tar.gz','navigation-input-expanded.json']} for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json']
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':files})
print(json.dumps({k:summary[k] for k in ('physical_calls','seconds','source_checks')},ensure_ascii=False))
