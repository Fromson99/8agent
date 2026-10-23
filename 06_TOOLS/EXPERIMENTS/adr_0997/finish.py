"""Seal the completed observation, preserving the raw run and scope conclusions."""
from common import *
import sys,tarfile,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS,QUESTION_HEADINGS_V4
f=read(ART/'design-freeze.json');s=read(ART/'stage.json');o=read(ART/'observations.json');r=o['native_result']
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
assert all(sha(ROOT/s['roots']['candidate']/n)==h for n,h in f['files']['candidate'].items())
assert sha(ART/'known-request.json')==f['request_sha256']
assert o['source_checks']['mismatches']==o['source_checks']['scope_violations']==0
findings=[
'검색 적중은 소득세법 제92조 제2항 제1호(unit1142)였다. 최초 parent_offer 준비값은 제2항 subtree1141이었지만 실제 시스템 정의 원문 읽기는 exact/subtree1142를 선택했다. UNIT_READ_CHOICE seq193의 offer.block_ids는1142 하나이며 article_complete=false다. 조 제목1139·제2항 도입1141은 문맥으로 별도 확보했다. 제92조 전체 읽기는 재현되지 않았다.',
'제88조 제1호 일부→외국환거래규정 서식 일부→제92조 제2항 제1호→제94조 전체는 시스템 acquire_initial이 자동으로 읽었다. 그 사이 모델의 개별 활용/관련없음 판단은 없고 SYSTEM_DEFINITION_ORIGINALS_ACQUIRED는 model_calls0이다. 이후 원문4곳을 한 번의 ASSESS(call002)에 전달했다.',
'제92조의 양도가액 정의 색인은 정의구간9..45에 포함된 제94조만 definition_reference로 연결한다. 같은 호48..52의 제97조는 전체 reference 색인에 정상 존재하지만 이 좁은 정의구간 밖이다. 초기 자동 정의 읽기가94조를 읽고97조를 읽지 않은 이유이며, 원문 전체의 연결 부재가 아니다.',
'call002는 제97조가 필요하다고 판단하고 missing_target=소득세법 제97조(필요경비)를 냈다. 그 뒤에야 첫 탐색 선택 call003이 열렸다. 초기 정의 원문 획득과 answer_first handoff 때문에 읽기 직후 연결 선택보다 ASSESS가 먼저 실행됐다.',
'connected_exploration.anchors는 현재 선택 초점만이 아니라 acquired/unexcluded 전체 원문을 루트로 삼는다. call003에4anchor의118connection_groups가 합쳐졌고 dependency_cards16개·omitted248개가 기록됐다. 제92조에서 제시된 OUTGOING은 해당1호의94·97 두 개였다. 여러 원문 연결의 혼합과 조 단위 역참조를 제92조의 모든 항·호 OUTGOING 전달로 혼동하면 안 된다.',
'제97조 연결은 call003의 두 번째 dependency_card이며 read_action T64다. 모델은 source_ref E30(제92조의 실제 읽은 원문), relation DEPENDENCY, target T64를 선택했다. T64는 gap target과 연결 target이 같은 정확한 원문 읽기 동작으로 결속된 경우여서 둘 중 UI 항목 하나만 보고 선택했다고 분리 추정하지 않는다. 실제제97조22블록 읽기와 후속 ASSESS를 확인했다.',
'후속 call004는 시행령의 구체항목 미확인을 언급하면서 현재 일반범위로 충분하다고 판단해 gaps=[]로 종료했다. 결과는 PARTIAL/LIMITED_ANSWER이고 시행령163은 원문 미확보다. 이번 실행의 시행령 미탐색은 못찾았다는 검색 실패가 아니라 추가 필요성을 닫은 모델 판단이다.',
'사용자 지적대로 원문 보존과 다음 연결 탐색 출발점은 분리해야 한다. 현재 구현에는 읽어둠→활용범위 선택→해당항호 연결 제시라는 판단 경계가 연결 메뉴에 반영되지 않는다. 묶음 처리의 비용 절약 목적은 확인된 사실이 아니며, 위 동작과 호출 횟수만 실측이다.'
]
limits=['사진에는 최초 입력창 문장이 없어 앱에 표시된 질문 문장을 전사했다. 법령명·조항번호를 입력에 추가하지 않았다.','최근 작업419파일을 frozen candidate로 실행했다. 선택된 MAIN101/GENOS 코드 교체나 신규 제품 수정은 없었다.','일반 로컬 RAG_ASK 경로와 외부Qwen3.8이다. GENOS workflow task_context/내부모델/현장 코드 해시는 동일성을 확인하지 못했고 현장 원인을 그대로 확정하지 않는다.','알려진 한 질문 한 번의 관찰이며 기준군 모델 실행·개선율·법률 정답률·일반화 평가는 하지 않았다.','총127.73초 중 provider28.27초, 차이99.46초는 서버 계산·초기화·기록 등을 포함한 잔여 경과다. 이 모두를 연결 목록 때문이라고 귀속하지 않는다. call003 입력55487토큰 역시 메뉴 전체이며 연결 카드만의 토큰이 아니다.']
summary={'status':'COMPLETE','verdict':'SCOPE_MIXING_AND_AUTOMATIC_READ_SEQUENCE_OBSERVED','diagnostic_complete':True,'findings':findings,'limits':limits,'physical_calls':r['model_calls'],'service_status':r['service_status'],'seconds':r['seconds'],'model_seconds':o['model_seconds'],'input_tokens':o['input_tokens'],'output_tokens':o['output_tokens'],'cost_usd':o['cost_usd'],'source_checks':o['source_checks'],'outcome':o['outcome'],'main_changed':False,'genos_changed':False,'integrity':{'snapshot_files_verified':len(f['files']['candidate']),'main_pointer_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256'],'working_drift':[n for n,h in f['working_files'].items() if sha(ROOT/n)!=h]}}
save(ART/'result.json',summary)
# The run process has completed. Archive only this run's generated runtime; originals/indexes were shared.
P=ART/'known-query/candidate';runtime=P/'runtime';archive=P/'runtime.tar.gz'
if runtime.exists():
 assert not archive.exists()
 hashes={str(p.relative_to(P)):sha(p) for p in runtime.rglob('*') if p.is_file()}
 with tarfile.open(archive,'w:gz',compresslevel=6) as t:t.add(runtime,arcname='runtime')
 with tarfile.open(archive,'r:gz') as t:
  for name,digest in hashes.items():
   with t.extractfile(name) as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==digest
 save(P/'runtime-archive.json',{'archive':'runtime.tar.gz','sha256':sha(archive),'verified_files':hashes,'restore':'Extract runtime.tar.gz under an empty directory; original relative runtime paths are preserved.','process_finished':True})
 shutil.rmtree(runtime)
m=read(ADR/'실험/manifest.json');assert m['design']['success_criteria']==f['design']['success_criteria']
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','new_calls':0,'historical_byte_reference_only':True},'candidate':{'status':'complete','diagnostic_complete':True,'correct':None,'total':1,'accuracy':None,'accuracy_not_scored_reason':'Behavior trace; no approved legal-answer gold','new_calls':r['model_calls'],'quality_certified':False}},comparisons=[],judge_disagreements=0,usage={'physical_calls':r['model_calls'],'input_tokens':o['input_tokens'],'output_tokens':o['output_tokens'],'cost_usd':o['cost_usd']},latency={'service_seconds':r['seconds'],'model_seconds':o['model_seconds'],'request_p50_seconds':r['seconds'],'request_p95_seconds':r['seconds'],'sample_size':1},error_taxonomy=[{'kind':'other','description':'Automatic originals are accumulated as connection anchors without per-scope applicability selection. Whole92 selection not observed.'}])
n=len(o['final_coordinates']);m['retrieval_accounting'].update(corpus_total=o['corpus_total'],before_filter=len(o['read_coordinates']),after_filter=n,presented_total=n,presented_mean=n,presented_p50=n,presented_p95=n,golden_recall=None,selectivity=n/o['corpus_total'])
m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
front=(ADR/'README.md').read_text().split('---',2)[1]
parts=['최근 작업 코드에서 실제1회 실행,5모델호출·127.73초·HTTP200. 검색·실제 읽기는92조2항1호. 누적 원문들의 연결 혼합과 자동 읽기 후 일괄 판단을 확인했다. 전체92읽기로 설명한 이전 추정은 이번 기록에 맞지 않는다.',
'사용자는 검색 적중 항·호 대신 넓은 연결이 제시되는 이유와 LLM의 넓은 읽기 선택 여부를 물었다.',m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],m['design']['sampling'],
'현재419제품파일 frozen snapshot, MAIN101의동일세대·65공개문서허용범위. Qwen3.8/Parasail FP8/reasoning none/fallback없음. [질문 출처](artifacts/query-provenance.json), [동결](artifacts/design-freeze.json).',
'1. request-entry FULLTEXT\n2. 시스템이88조 일부·서식·92조2항1호·94조 원문 확보(중간모델0회)\n3. ASSESS 제97조필요\n4. 누적4원문의 연결을 포함한 탐색입력 → 모델T64선택 →97조읽기\n5. ASSESS 일반3범주충분판단 → COMPOSE.\n\n[전체 호출](artifacts/calls.json) · [실제 답변](artifacts/answer.txt)',
'\n\n'.join(findings),
json.dumps({k:summary[k] for k in ('physical_calls','seconds','model_seconds','input_tokens','output_tokens','cost_usd','source_checks')},ensure_ascii=False,indent=2)+'\n\n읽은 원문/미리보기15조문 root→최종인용2조문, 허용코퍼스15777root. 원장은 실제확보→최종인용이며 검색전체회수율이 아니다. 승인gold없어정답률/recall미채점. call003 입력55487토큰. peakRSS3172MiB.',
'문제는 모델이92전체를선택한것이아니라 자동읽기와 현재탐색범위/누적원문보존이 묶여있는것이다. 관련성판단/연결출발점선택을 원문보존과분리하는수정이필요하다. 물리호출1회에서도 범위별판단과nextanchor를표현할수있으므로 모든조항을별도모델호출로만처리해야하는것은아니다.',
'\n\n'.join(limits),
'제품수정·MAIN승격·GENOS적용없음. 기존원본/실패/동결기록보존. 수정과 효과검증은 별도작업 및 새ADR로수행한다.',
'prepare.py → guard.py(한번실행) → analyze.py → finish.py → adr_structure.py status/hash/validate --final/graph. 기존guard는재실행거부. rawmodel request/response는artifacts/known-query/candidate/model, runtime은검증압축보존.']
(ADR/'README.md').write_text('---'+front+'---\n\n# 필요경비 질문의 실제 읽기·연결 범위\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(ADR_HEADINGS,parts)))
row=m['questions'][0]
rawlinks=[]
for p in sorted((P/'model').glob('*/*.json')):rawlinks.append(f'[{p.relative_to(P)}](../artifacts/{p.relative_to(ART)})')
values=['run-001/candidate, one natural local RAG request; external Qwen3.8.',json.dumps(read(ART/'known-request.json'),ensure_ascii=False,indent=2),'Legal gold absent; diagnostic criteria frozen before execution. No target answer or coordinates entered product input.',
'[Original provider input and all calls](../artifacts/calls.json), [expanded navigation input](../artifacts/navigation-input-expanded.json), [actual scope trace](../artifacts/known-query/candidate/scope-trace.jsonl), [source verification](../artifacts/source-audit.json).',
'[Exact source-read/citation ledger](../artifacts/retrieval-ledger.json). It is not a full search-stage reconstruction. Detailed actual search previews/read offers are retained in scope-trace.jsonl.',
'\n\n'.join(rawlinks),'All5nativecalls retained, no replay or synthetic model answer. Event journal is archived losslessly inruntime.tar.gz; [event export](../artifacts/events.json).','Offline review only; no model judge, approved gold or accuracy comparison.','\n\n'.join(findings)+'\n\n'+'\n\n'.join(limits)]
qp=ADR/'실험'/row['file'];qp.write_text('# 양도차익 필요경비\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,values)));row['sha256']=sha(qp)
(ADR/'실험/README.md').write_text('# 사례\n\n- [실제 질문·입출력·판정]('+row['file']+')\n');save(ADR/'실험/manifest.json',m)
files=[]
for p in sorted(ART.rglob('*')):
 if p.is_file() and p!=ART/'manifest.json':files.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'description':'Frozen design, exact model/trace/source evidence or offline diagnostic','contains_raw_prompts_and_outputs':'model' in p.parts or p.name in ['runtime.tar.gz','navigation-input-expanded.json']})
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':files})
(ADR/'RESULT.txt').write_text('실제 로컬5호출·127.73초. 제92조 제2항 제1호를 읽었다. 전체조읽기 재현없음.\n'+'\n\n'.join(findings)+'\n\n'+'\n'.join(limits)+'\nMAIN101/GENOS/제품코드 변경없음.\n')
index=ROOT/'04_EXPERIMENTS/ADR/README.md';txt=index.read_text();line='- [ADR-0997 필요경비 실제 연결 범위 추적](ADR-0997-income-tax-connection-scope-live/README.md) — 현재 작업코드5호출·127.73초.92조2항1호읽기, 자동확보4원문의연결혼합확인;97조읽음·시행령추가조사는충분성판단으로종료.제품/MAIN불변.\n'
if 'ADR-0997 필요경비' not in txt:index.write_text(txt.replace('# ADR workspace\n','# ADR workspace\n\n'+line,1))
print('Completed observed trace; archived runtime verified; MAIN unchanged.')
