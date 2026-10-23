"""Record measured outcomes without changing the frozen criteria or product."""
from common import *
import sys,tarfile,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS,QUESTION_HEADINGS_V4
f=read(ART/'design-freeze.json');s=read(ART/'stage.json');o=read(ART/'observations.json')
r=o['native_result'];v=read(ART/'verdict.json');P=ART/'known-query/candidate'
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
assert all(sha(ROOT/s['roots']['candidate']/n)==h for n,h in f['files']['candidate'].items())
assert all(sha(ROOT/n)==h for n,h in s['working_before'].items())
assert o['main_unchanged']
physical=[json.loads(x) for x in (P/'physical-calls.jsonl').read_text().splitlines()]
assert len(physical)==r['model_calls']
if not r['usage']:
 for k in ('model_seconds','non_model_elapsed_seconds','input_tokens','output_tokens','cost_usd'):o[k]=None
 o['usage_status']='NOT_RETURNED_BY_PROVIDER';save(ART/'observations.json',o)
summary={**v,'status':'COMPLETE','physical_calls':r['model_calls'],'service_status':r.get('service_status'),'seconds':r['seconds'],
 'input_tokens':o['input_tokens'],'output_tokens':o['output_tokens'],'cost_usd':o['cost_usd'],
 'legal_accuracy':None,'quality_certified':False,'decision_eligible':False,'working_code_changed':False,
 'main_changed':False,'genos_changed':False,'candidate_contracts_passed':38,'frozen_files':len(f['files']['candidate']),
 'selected_release_exact_files':len(s['base_release']['files']),'source_checks':o['source_checks']}
save(ART/'result.json',summary)
runtime=P/'runtime';archive=P/'runtime.tar.gz'
if runtime.exists():
 assert not archive.exists()
 hashes={str(p.relative_to(P)):sha(p) for p in runtime.rglob('*') if p.is_file()}
 with tarfile.open(archive,'w:gz',compresslevel=6) as t:t.add(runtime,arcname='runtime')
 with tarfile.open(archive,'r:gz') as t:
  for name,h in hashes.items():
   with t.extractfile(name) as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==h
 save(P/'runtime-archive.json',{'archive':'runtime.tar.gz','sha256':sha(archive),'verified_files':hashes,'restore':'Extract into an empty directory; runtime relative paths preserved.','process_finished':True})
 shutil.rmtree(runtime)
m=read(ADR/'실험/manifest.json');assert m['design']==f['design']
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','new_calls':0,'historical_reference_only':True},'candidate':{'status':'complete','correct':None,'total':1,'accuracy':None,'accuracy_not_scored_reason':'Known in-sample operational probe; no approved legal-answer gold. Source acquisition, native completion and contract metrics separately reported.','new_calls':r['model_calls'],'quality_certified':False}},comparisons=[],judge_disagreements=0,usage={'physical_calls':r['model_calls'],'input_tokens':o['input_tokens'],'output_tokens':o['output_tokens'],'cost_usd':o['cost_usd'],'returned_usage_records':len(r['usage'])},latency={'service_seconds':r['seconds'],'model_seconds':o['model_seconds'],'request_p50_seconds':r['seconds'],'request_p95_seconds':r['seconds'],'sample_size':1},error_taxonomy=v['error_taxonomy'])
nr=len(o['read_coordinates']);nf=len(o['final_coordinates'])
m['retrieval_accounting'].update(corpus_total=o['corpus_total'],before_filter=nr,after_filter=nf,presented_total=nf,presented_mean=nf,presented_p50=nf,presented_p95=nf,golden_recall={'candidate':None},selectivity=nf/o['corpus_total'])
m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
findings=v['findings'];limits=v['limitations']
front=(ADR/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: '+('Proposed' if v['criteria_met'] else 'Rejected'))
parts=[v['verdict'],'\n\n'.join(findings[:2]),m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],m['design']['sampling'],
 'MAIN102 선택 코드420파일 일치, 보조 검사 포함428파일 동결. 동일 데이터·65공개문서·Qwen3.8/Parasail FP8. [동결](artifacts/design-freeze.json).',
 '\n\n'.join(findings),'[호출별 기록](artifacts/known-query/candidate/physical-calls.jsonl), [원문 검사](artifacts/source-audit.json), [모의 계약38개](artifacts/contracts.txt), [실제 답변](artifacts/answer.txt).',
 json.dumps(summary,ensure_ascii=False,indent=2),v['decision'],'\n\n'.join(limits),
 '실험 격리 실행만 완료. 작업 코드·선택 MAIN102·GENOS 변경 없음.',
 'reserve → selected release copy → freeze → 38contracts → guarded native request once → offline source/call audit → lossless archive → status/hash/validate/graph. 최초 실행 준비의 진단 모듈 경로 오류는 서비스 호출 전 발생했고 모델0회다. 원본을 보존하고 관찰 코드만 수정해 호출 전에 재동결했다. [기록](artifacts/setup-amendment.json).']
(ADR/'README.md').write_text('---'+front+'---\n\n# MAIN102 연결관계 실제 실행과 단계별 호출 감사\n\n'+''.join(h+'\n\n'+x+'\n\n' for h,x in zip(ADR_HEADINGS,parts)))
row=m['questions'][0]
values=['run-001/candidate; selected MAIN102 native local service, one public request.',read(ART/'known-request.json')['json']['question'],
 '승인된 법률 정답 없음. 원문 전달·연결·완료 여부를 별도 검사한다.','[요청](../artifacts/known-request.json), [출처 이력](../artifacts/query-provenance.json).',
 '[확보→인용 원장](../artifacts/retrieval-ledger.json); canonical article-root 단위이며 gold를 제품에 넣지 않았다.',
 '[모델 입출력](../artifacts/known-query/candidate/model), [호출별 목적](../artifacts/known-query/candidate/physical-calls.jsonl).',
 f"물리 호출{r['model_calls']}; native{r.get('service_status')}; {r['seconds']:.3f}초. 상세 usage와 지연은 manifest 및 원시 기록에 보존.",
 '추가 모델 judge0회. 법률 정답 미평가; paired causal comparison 미실행.', '\n\n'.join(findings+limits)]
qp=ADR/'실험'/row['file'];qp.write_text('# 양도차익 필요경비\n\n'+''.join(h+'\n\n'+x+'\n\n' for h,x in zip(QUESTION_HEADINGS_V4,values)));row['sha256']=sha(qp)
(ADR/'실험/README.md').write_text('# 사례\n\n- [질문·입출력·판정]('+row['file']+')\n')
save(ADR/'실험/manifest.json',m)
(ADR/'RESULT.txt').write_text('\n\n'.join(findings+limits)+'\n')
index=ROOT/'04_EXPERIMENTS/ADR/README.md';text=index.read_text()
line=f"- [ADR-1001 MAIN102 연결관계 실제 실행](ADR-1001-main102-connection-live-audit/README.md) — {v['index_summary']}\n"
assert 'ADR-1001 MAIN102' not in text
index.write_text(text.replace('# ADR workspace\n','# ADR workspace\n'+line))
rows=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'description':'Frozen selected release, native model attempt and source/call audit','contains_raw_prompts_and_outputs':'model' in p.parts or p.name=='runtime.tar.gz'} for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json']
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':rows})
print(json.dumps({k:summary[k] for k in ('verdict','physical_calls','service_status','seconds','criteria_met')},ensure_ascii=False))
