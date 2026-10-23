from common import *
import sys,tarfile,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS,QUESTION_HEADINGS_V4
f=read(ART/'design-freeze.json');s=read(ART/'stage.json');o=read(ART/'observations.json');r=o['native_result']
assert (ART/'guard-result.json').exists()
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
assert all(sha(ROOT/s['roots']['candidate']/n)==h for n,h in f['files']['candidate'].items())
assert all(sha(ROOT/n)==h for n,h in f['working_files'].items())
assert o['main_unchanged']
calls=read(ART/'decision-context-audit.json')['calls']
endpoint=read(ART/'article-endpoint-diagnosis.json')
findings=[
 '92조 제2항 제1호의 정확한 범위에서 연결4개를 바로 제시했다. call002가 제97조 연결 READ를 선택해 원문을 확보했다. 이 구간에 별도 FOLLOW 목록 판단이나 LOCATE 구조 검색은 없었다.',
 'call003은 제97조 원문1754자를 받은 뒤 양도가액 산정 기준도 필요하다며 제96조를 읽었다. 최초 검색의 읽기 후보에서 선택했으며 새로운 검색이나 검증된 연결 선택은 아니었다.',
 'call004와 보정call005 모두 제97조 원문1754자와 사용자 질문을 받았다. 그러나92→97 연결 카드가 already_read=false와 READ 선택을 다시 제공했다. 모델은97조 재읽기를 선택했고 unchanged navigation action 검사와1회보정 뒤 조사에서 이탈했다. 실제 중복 원문 읽기는 실행되지 않았다.',
 '원인은 데이터의 조 전체 참조가 targets.block_ids=[]인 경우다. 표시용 endpoint_block_ids는 대상 조의 전체 블록으로 보완하지만 already_read는 비어 있지 않은 원래 block_ids만 검사한다. OPTIONAL 연결에는 required_blocks 보완도 없어 조 전체를 확보해도 미열람으로 표시한다. 재현 입력과 코드 지점을 보존했고 이번 실험 중 수정하지 않았다.',
 '시행령163조에 도달하지 못했다. 따라서163조 확보 후 후속 연결 판단에 본문이 전달되는지와97조 복귀 해소는 이번 실제 실행으로 검증되지 않았다. 앞선 합성 API 검증과 실제 검증을 구분한다.'
]
if r['service_status']==422:
 findings.append('최종 판단과 허용된1회보정이 같은 설명을 반복하며 각각6400출력토큰에서 잘려 HTTP422/review_incomplete로 종료했다. 최종 답변을 발행하지 못했다.')
else:
 findings.append('최종 서비스 상태와 출력은 observations.json/answer.txt에 보존했다. 성공 여부는 실제 service_status와 outcome을 따른다.')
limits=['같은 공개 질문1건·외부 Qwen3.8/Parasail FP8 실측이며 승인된 법률 정답·분리평가·품질인증 없음.',
 '기존 ADR0998은 역사적 참고값(15호출/480.17초)이다. 이번은163조 미도달과 조기 조사 종료가 있어 짧아진 시간을 정상 답변 속도 개선으로 해석하지 않는다.',
 '이번 변경은 격리된 실행·계측·결과 기록뿐이다. 작업 런타임426파일·선택 MAIN101·GENOS·원문·색인을 수정하지 않았다.',
 '전역 graph는 검사 결과를 별도 기록한다. 과거9개 오류가 유지되면 전역 검사 전체 통과로 보고하지 않는다.']
summary={'status':'COMPLETE','verdict':'INLINE_CONNECTION_PATH_CONFIRMED; ARTICLE_ONLY_READ_STATE_DEFECT; DECREE_CONTEXT_UNTESTED; NATIVE_ANSWER_FAILED' if r['service_status']!=200 else 'OBSERVED_WITH_KNOWN_DEFECT',
 'findings':findings,'limitations':limits,'physical_calls':r['model_calls'],'service_status':r['service_status'],
 'seconds':r['seconds'],'model_seconds':o['model_seconds'],'input_tokens':o['input_tokens'],'output_tokens':o['output_tokens'],'cost_usd':o['cost_usd'],
 'source_checks':o['source_checks'],'outcome':o['outcome'],'native_answer_success':r['service_status']==200,
 'quality_certified':False,'criteria_met':False,'main_changed':False,'genos_changed':False,'product_code_changed':False,
 'decree163_followup_context_observed':False,'article_only_endpoint_defect_confirmed':endpoint['entire_article_acquired']}
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
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','new_calls':0,'historical_reference_only':True},'candidate':{'status':'complete','correct':None,'total':1,'accuracy':None,'accuracy_not_scored_reason':'No approved legal gold; failed native answer and explicit trace criteria assessed separately.','new_calls':r['model_calls'],'quality_certified':False}},comparisons=[],judge_disagreements=0,
 usage={'physical_calls':r['model_calls'],'input_tokens':o['input_tokens'],'output_tokens':o['output_tokens'],'cost_usd':o['cost_usd']},latency={'service_seconds':r['seconds'],'model_seconds':o['model_seconds'],'request_p50_seconds':r['seconds'],'request_p95_seconds':r['seconds'],'sample_size':1},
 error_taxonomy=[{'kind':'other','description':'Article-only reference with empty endpoint block_ids remains unread after complete read; duplicate READ rejected twice. ASSESS and repair repeat until output token cap; decree163 never reached.'}])
n=len(o['final_coordinates']);m['retrieval_accounting'].update(corpus_total=o['corpus_total'],before_filter=len(o['read_coordinates']),after_filter=n,presented_total=n,presented_mean=n,presented_p50=n,presented_p95=n,golden_recall={'candidate':None},selectivity=n/o['corpus_total'])
m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
front=(ADR/'README.md').read_text().split('---',2)[1]
parts=[summary['verdict'], '사용자는5개 이하 연결의 직접 표시와 판단 원문 보존 수정 후 같은 질문의 실제 재실행을 요청했다.',
 m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],m['design']['sampling'],
 '현재 검증된 작업 코드426파일 snapshot, 기존 MAIN101 데이터·65공개문서·Qwen3.8·6400출력 상한·40호출/1800초 예산. [동결](artifacts/design-freeze.json).',
 '\n\n'.join(findings), '[정확한 판단 원문/선택](artifacts/decision-context-audit.json), [조 전체 연결 결함](artifacts/article-endpoint-diagnosis.json), [원문·권한 검사](artifacts/source-audit.json).',
 json.dumps({k:summary[k] for k in ('physical_calls','seconds','model_seconds','input_tokens','output_tokens','cost_usd','source_checks')},ensure_ascii=False,indent=2),
 '직접 연결을 타는 첫 구간은 확인했다. 전체 흐름의 성공 기준은 미충족이며163조 이후 본문 전달은 실측하지 못했다. 확보 원문이 있는데도 미열람으로 표시하는 결정적 코드 결함과 반복 출력 실패를 분리한다.',
 '\n\n'.join(limits), 'MAIN101·GENOS 불변. runtime 변경 없음. 실패 기록과 동결 코드는 보존하고 보완 후 실험은 새 ADR에서 수행한다.',
 'prepare.py → freeze.py → candidate hash validation → guard.py 단1회 → analyze.py → decision_audit.py → endpoint_diagnosis.py → finish.py → status/hash/validate --final/graph.']
(ADR/'README.md').write_text('---'+front+'---\n\n# 판단 원문·작은 연결 목록 실제 재실행\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(ADR_HEADINGS,parts)))
row=m['questions'][0];rawlinks=[f'[{p.relative_to(P)}](../artifacts/{p.relative_to(ART)})' for p in sorted((P/'model').glob('*/*.json'))]
values=['run-001/candidate; original public question once through native local service/API.',read(ART/'known-request.json')['json']['question'],
 '승인된 법률 gold 없음. 정답/좌표를 제품 입력에 주입하지 않았다. 사전 trace criteria만 평가한다.',
 '[요청 원값](../artifacts/known-request.json), [입력 원문/연결/선택](../artifacts/decision-context-audit.json), [원문 감사](../artifacts/source-audit.json).',
 '[확보 원문→최종 인용 원장](../artifacts/retrieval-ledger.json). 전체 검색 후보 회수율이나 승인된 정답 recall은 측정하지 않음.',
 '\n\n'.join(rawlinks),'실제 원시 요청·응답·usage·모델·provider·스키마·원문·이력을 보존했다. 종료 후 runtime을 무손실 압축/해시 검증했다.',
 '모델 judge 호출 없음. 저장 원문 및 코드·선택 이력을 읽기 전용 검사했다.', '\n\n'.join(findings+limits)]
qp=ADR/'실험'/row['file'];qp.write_text('# 양도차익 필요경비 재실행\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,values)));row['sha256']=sha(qp)
(ADR/'실험/README.md').write_text('# 사례\n\n- [질문·입출력·판정]('+row['file']+')\n')
save(ADR/'실험/manifest.json',m)
(ADR/'RESULT.txt').write_text('\n\n'.join(findings+limits)+'\n\n'+json.dumps({k:summary[k] for k in ('physical_calls','service_status','seconds','source_checks')},ensure_ascii=False)+'\n')
index=ROOT/'04_EXPERIMENTS/ADR/README.md';txt=index.read_text()
line='- [ADR-0999 판단 원문·작은 연결 목록 실제 재실행](ADR-0999-original-context-inline-live-rerun/README.md) —92②1→97직접연결 확인. 조 전체 연결의 이미 읽음 표시 결함·중복선택 거절·최종판단 출력한도 실패.163미도달, MAIN101/GENOS 불변.\n'
if 'ADR-0999 판단 원문' not in txt:index.write_text(txt.replace('# ADR workspace\n','# ADR workspace\n'+line))
files=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'description':'Frozen code/design, native execution, raw model evidence, read-only diagnosis','contains_raw_prompts_and_outputs':'model' in p.parts or p.name=='runtime.tar.gz'} for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json']
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':files})
print(json.dumps({k:summary[k] for k in ('physical_calls','service_status','seconds','source_checks')},ensure_ascii=False))
