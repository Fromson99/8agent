from pathlib import Path
import json,hashlib,subprocess,sys
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0940-research-continuity-prompt-cost';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert len((A/'artifacts/sequence.jsonl').read_text().splitlines())==4
manual=read(O/'manual-review.json');assert set(manual['cases'])=={'rp-bond-scope','leverage'}
for name in ('scope_audit.py','coverage_audit.py','navigation_audit.py','packet_audit.py','citation_audit.py','report.py'):
 subprocess.run([sys.executable,'-B',str(T/name)],check=True)
r=read(O/'result.json');m=read(A/'실험/manifest.json')
resources=[read(p) for p in (A/'artifacts').glob('resource-*.json')]
technical={
 'four_resource_records':len(resources)==4,
 'no_resource_stop':all(v['stop_reason'] is None for v in resources),
 'scope_and_side_pass':all(read(p)['all_scope_checks_pass'] for p in (A/'artifacts').glob('scope-*.json')),
 'four_scope_records':len(list((A/'artifacts').glob('scope-*.json')))==4,
 'primary_quote_literal_match':all(read(p)['literal_mismatches']==0 for p in O.glob('*/*/citation-audit.json')),
 'consumer_checks_pass':all(row['consumer_checks'] and all(row['consumer_checks'].values()) for arm in r['cases'].values() for row in arm.values()),
 'provider_usage_complete':all(row['usage_complete'] for arm in r['cases'].values() for row in arm.values()),
 'call_budget_preserved':all(row['model_calls']<=40 for arm in r['cases'].values() for row in arm.values()),
 'time_budget_preserved':all(row['elapsed_seconds']<=1800 for arm in r['cases'].values() for row in arm.values()),
 'no_new_graph_errors':not read(A/'artifacts/graph-check.json')['new_errors'],
}
put(A/'artifacts/technical-checks.json',technical)
status='Rejected' if not all(technical.values()) or any(p['input_token_overgrowth'] or p['metadata_overgrowth'] or not p['both_terminal_responses'] for p in r['paired']) or any(a['source_mismatches'] for a in r['by_arm'].values()) else 'Proposed'
active=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert active==read(D/'baseline.json')['pointer']
working=read(D/'working-before.json');drift=[n for n,h in working.items() if sha(R/n)!=h]
put(A/'artifacts/final-binding.json',{'active_pointer_unchanged':True,'working_file_count':len(working),'working_current_drift':drift,'genos_executed':False,'code_roots':{arm:read(D/(arm+'-binding.json'))['code_root'] for arm in ('baseline','modified')}})
put(A/'artifacts/resources-summary.json',{'runs':len(resources),'peak_rss_mib':max(v['peak_group_rss_bytes'] for v in resources)/2**20,'minimum_available_gib':min(v['min_available_bytes'] for v in resources)/2**30,'guard_stops':[v['stop_reason'] for v in resources if v['stop_reason']]})
lines=[]
for pair in r['paired']:
 name=pair['case_id'];b=r['cases']['baseline'][name];n=r['cases']['modified'][name]
 lines.append(f"{name}: calls {b['model_calls']} -> {n['model_calls']}; input tokens {b['input_tokens']:,} -> {n['input_tokens']:,} ({(pair['input_token_ratio']-1)*100:+.1f}%); max prompt tokens {b['prompt_tokens_max']:,} -> {n['prompt_tokens_max']:,}; added metadata max {n['metadata_fraction_max']*100:.2f}%.")
summary=manual['conclusion']+'\n\n'+'\n'.join(lines)
summary+='\n\nFixed system instruction +209 Unicode chars. Actual provider input tokens include messages and schema. Metadata character counterfactual removes new fields only, preserving the same captured source/decision state.\n'
summary+=f"Actual Qwen3.8/Parasail requests {r['model_calls']}; exact original checks {sum(a['stored_original_checks'] for a in r['by_arm'].values())}; mismatches {sum(a['source_mismatches'] for a in r['by_arm'].values())}.\n"
summary+='Technical checks: '+json.dumps(technical,ensure_ascii=False)+'. Global ADR graph retains the same nine historical errors; no new errors.\n'
summary+='\nKnown-case probe, one fresh request per arm/case; no legal gold or general performance certification. Both code/data/model bindings and the four-run order were frozen before calls. No adaptive model rerun. Raw records, early validation metadata omissions and actual failures remain.\nMAIN90/workflow1.16.0 remains selected; working1.17.0 and GENOS untouched by this test.\n'
(A/'RESULT.txt').write_text(summary)
sections=[('결정 요약',summary),('문제와 변경 전 구조','조사 이력 전달은 반복을 줄일 수 있지만 프롬프트를 늘릴 수 있다. 연결부 기술 검사가 실제 모델 입력량·원문 선택 개선을 보장하지 않으므로 별도로 비교했다.'),('가설과 사전 판정 기준',json.dumps(read(D/'criteria.json'),ensure_ascii=False,indent=2)),('실험 설계','같은 두 질문을 baseline/modified 각각1회. 수정RP→기준RP→기준레버리지→수정레버리지 순서. 새 runtime, 같은 승인 문서 범위·원문 세대·검색·모델·예산. 제품 코드 추가 변경 없음.'),('데이터·모델·재현성','MAIN90 baseline release와 ADR0939에서 검증·통합한 작업388파일의 불변 snapshot. Qwen3.8/Parasail FP8, effort none, fallback 없음. 기존 승인 workflow grant만 사용. risk_cm 원본 질문·정답 후보·사진을 입력하지 않았다.'),('결과',json.dumps(r,ensure_ascii=False,indent=2)),('사례별 오류 분석',json.dumps(manual,ensure_ascii=False,indent=2)),('비용·지연·회수 규모','원시 usage의 실제 prompt/completion 토큰과 각 호출의 메시지·schema 크기를 측정했다. 신규 metadata의 동일 상태 문자 순증은 토큰으로 가장하지 않았다. source→returned→cited 원장과 자원 측정을 함께 보존했다.'),('해석','전체 입력 토큰은 호출 수와 선택한 원문의 차이까지 포함한다. 신규 필드 순증·고정 지시문 증가·전체 비용을 분리했다. 낮은 비용은 법률 답변 정확도 증명이 아니다.'),('한계와 일반화 가능 범위','알려진2사례 단회 비교다. 질문·경로별 변동과 작은 표본 때문에 일반 성능 효과나 GENOS 내부 모델 결과로 해석하지 않는다. 기존8계약 실패는 이번 실제모델 측정에서 수리한 것이 아니다.'),('운영 결정·롤백 조건','선택 MAIN90·작업코드·GENOS 변경 없음. 추가 개선과 MAIN 승격은 별도 결정이다. 이전 작업 통합의 복구는 09_ARTIFACTS/AUDITS/20261020-research-continuity/rollback.py와 receipt를 따른다.'),('재현 명령','동결된 schedule.json과 live.py를 사용한 실제 명령은 각 resource-*.json에 있다. 완료 결과의 새 모델 재실행은 새 ADR로 선점한다. raw-runtime.tar.gz는 case 폴더에서 tar -xzf로 복원하며 archive-manifest에 모든 원본 hash가 있다.')]
meta=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: '+status)
(A/'README.md').write_text('---'+meta+'---\n\n# 조사 연속성 실제 입력 비용과 원문 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{body}' for i,(h,body) in enumerate(sections,1))+'\n')
for q in m['questions']:
 p=A/'실험'/q['file'];s=p.read_text();s=s.replace('실행 후 기록.',json.dumps({'cost':next(v for v in r['paired'] if v['case_id']==q['case_id']),'source_review':manual['cases'][q['case_id']]},ensure_ascii=False,indent=2));p.write_text(s);q['sha256']=sha(p)
(A/'실험/README.md').write_text('# 질문별 비교\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
put(A/'실험/manifest.json',m)
subprocess.run([sys.executable,'-B',str(T/'archive.py')],check=True)
paths=[A/'RESULT.txt',*T.glob('*.py'),R/'02_BACKEND/lawrag/research/candidates/adr_0940/modified/candidate.json']+[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']
art=read(A/'artifacts/manifest.json');art['files']=[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen paired prompt/call/source audit or lossless execution record','contains_raw_prompts_and_outputs':p.name.endswith('.gz')} for p in sorted(set(paths))];put(A/'artifacts/manifest.json',art)
for args in (['hash','--path',str(A)],['status','--path',str(A),'--status','completed','--note','Four fresh model requests audited; prompt costs, preserved originals and remaining source selection limitations recorded. MAIN unchanged.'],['validate','--path',str(A),'--final']):
 subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py',*args],check=True)
print(summary)
