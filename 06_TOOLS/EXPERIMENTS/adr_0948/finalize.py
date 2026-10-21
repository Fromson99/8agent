"""Close the observed runs without turning interrupted usage into a comparison."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0948-research-decision-live-repeat'
D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert len((A/'artifacts/sequence.jsonl').read_text().splitlines())==4
assert read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(D/'baseline.json')['pointer']
for name in ('scope_audit.py','coverage_audit.py','navigation_audit.py','packet_audit.py',
             'citation_audit.py','transition_audit.py','report.py'):
    subprocess.run([sys.executable,'-B',str(T/name)],check=True)
r=read(O/'result.json');m=read(A/'실험/manifest.json')
manual=read(O/'manual-review.json')
resources=[read(p) for p in (A/'artifacts').glob('resource-*.json')]
checks={
    'four_requests_recorded':len(resources)==4,
    'failed_child_read_originals_transferred':not any(x['failed_read_not_returned'] for x in read(A/'artifacts/failure-handoff-audit.json')),
    'no_resource_guard_stop':all(v['stop_reason'] is None for v in resources),
    'scope_and_side':all(all(c['in_workflow_grant'] and c['side_matches'] for c in read(p)['checks']) for p in (A/'artifacts').glob('scope-*.json')),
    'source_checks_exercised':sum(v['stored_original_checks'] for v in r['by_arm'].values())>0,
    'four_scope_records':len(list((A/'artifacts').glob('scope-*.json')))==4,
    'stored_originals_exact':all(v['source_mismatches']==0 for v in r['by_arm'].values()),
    'selected_quotes_exact':all(read(p)['literal_mismatches']==0 for p in O.glob('*/*/citation-audit.json')),
    'metadata_within_frozen_threshold':not any(v['metadata_overgrowth'] for v in r['paired']),
    'call_budget':all(v['model_calls']<=40 for arm in r['cases'].values() for v in arm.values()),
    'four_terminal_responses':all(v['both_terminal_responses'] for v in r['paired']),
    'all_generation_usage_complete':all(v['generation_usage_complete'] for arm in r['cases'].values() for v in arm.values()),
}
put(A/'artifacts/technical-checks.json',checks)
comparability={}
lines=[]
for pair in r['paired']:
    ident=pair['case_id'];b=r['cases']['baseline'][ident];n=r['cases']['modified'][ident]
    comparable=bool(pair['both_terminal_responses'] and b['generation_usage_complete'] and n['generation_usage_complete'] and not b['unknown_calls'] and not n['unknown_calls'])
    comparability[ident]={'comparable_completed_usage':comparable,
        'valid_input_token_ratio':pair['input_token_ratio'] if comparable else None,
        'reason':'Both terminal completed/partial responses; all received generations have token receipts and no unknown calls. 429 rejection counts separate; rejected-call billing unverified.' if comparable else
        'A request failed or a generation has unknown outcome/usage. No valid completed-answer token comparison; retain received-generation token sums and rejected429 counts separately.',
        'raw_pair_record_preserved':str((O/'result.json').relative_to(R)),
        'matched_workload_cost_conclusion':False,
        'workload_limit':'RP candidate failed intake; leverage control lost all originals on429 whereas candidate delivered internal originals. Observed ratios do not isolate code overhead; frozen125% threshold is not waived.'}
    lines.append(f"{ident}: calls {b['model_calls']} -> {n['model_calls']}; recorded input tokens "
                 f"{b['input_tokens']:,} -> {n['input_tokens']:,}; comparable={comparable}; "
                 f"added field max {n['metadata_fraction_max']*100:.2f}%; 429 {b['known_rejected_429']} -> {n['known_rejected_429']}.")
put(A/'artifacts/comparability.json',comparability)
status='Proposed'
if not all(checks[k] for k in ('no_resource_guard_stop','scope_and_side','stored_originals_exact',
                               'selected_quotes_exact','metadata_within_frozen_threshold','call_budget','failed_child_read_originals_transferred')):
    status='Rejected'
summary=manual['conclusion']+'\n\n'+'\n'.join(lines)
summary+='\n선택적 출력 need_resolution 필드의 문자 비중은 각 요청별 기록을 따른다. 고정 지시문 차이는 static-prompt-delta.json 참조. 문자 비중을 토큰 비중으로 주장하지 않는다.\n'
summary+='원문 일치 검사 '+str(sum(v['stored_original_checks'] for v in r['by_arm'].values()))+'회; 불일치 '+str(sum(v['source_mismatches'] for v in r['by_arm'].values()))+'건.\n'
summary+='알려진2사례 단회 관찰이며 법률 정답률·GENOS 성능을 인증하지 않는다. 429 미수락과 결과 불명 호출을 구분했다. 사전 동결한 각 arm/case1회이며 추가 재호출은 없다. 이번 실험에서 MAIN90과 작업 코드를 변경하지 않았다.\n'
(A/'RESULT.txt').write_text(summary)
m['results']['error_taxonomy']=manual.get('failure_records',[])
m['results']['comparisons']=comparability
front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: '+status)
sections=[
 ('결정 요약',summary),
 ('문제와 변경 전 구조','새 원문ID 없이 변경된 조사 결과의 상위 판단, 명시적 부족 해소, 제한된 발견→읽기 연결을 수정한 완료 후보를 실제 모델로 관찰했다.'),
 ('가설과 사전 판정 기준','artifacts/design/criteria.json에 호출 전 동결. 중단을 성공으로 바꾸거나 사후 임계값을 조정하지 않는다.'),
 ('실험 설계','수정RP→기준RP→기준레버리지→수정레버리지. 같은 데이터·모델·검색·권한·예산, 요청마다 새 runtime.'),
 ('데이터·모델·재현성','ADR0944의 기준1.18과 최종 ADR0947후보1.19.2 각각389파일. Qwen3.8/Parasail FP8, reasoning none, fallback 없음. 기존 승인 workflow 문서 범위만 사용.'),
 ('결과','실제 토큰/호출은 artifacts/run-001/result.json, 유효 비교 여부는 artifacts/comparability.json. 실패 호출의 누락 사용량을0으로 간주하지 않는다.'),
 ('사례별 오류 분석',json.dumps(manual,ensure_ascii=False,indent=2)),
 ('비용·지연·회수 규모','\n'.join(lines)+'\n\n### 단계별 회수·탈락 원장\n\nartifacts/run-001/retrieval-ledger.json. 원문 확보/반환/최종 인용을 구분한다. 승인 gold가 없어 recall은 미측정.'),
 ('해석','변경된 조사 상태 재검토와 인용 원문 일치는 기술 검증이다. 의미 판단의 정답이나 미확보 자료의 부재 증명이 아니다. 사전 기준에 따라 응답 완료·생성 사용량 완전성·결과불명 호출 여부로 비교 가능성을 판단한다. 429 자체는 생성 토큰 누락과 구분하고 과금은 별도 미확인으로 남긴다.'),
 ('한계와 일반화 가능 범위','소표본 known-case probe. 저장·중복 소비자는 완료된 응답에서만 확인했다. 실제 사례별 한계는 manual-review.json을 따른다. 전송 성공과 의미 정답을 구분한다.'),
 ('운영 결정·롤백 조건','이 실험 자체는 MAIN 승격 근거가 아니다. 별도 기술 자격 검사와 작업 통합을 구분한다. 비용 비교 가능성은 comparability.json, 허용 증가125% 초과 여부는 result.json에 기록한다. 단회 인샘플 관찰만으로 MAIN을 자동 전환하지 않는다.'),
 ('재현 명령','원 실행 명령은 resource-*.json. 원시 기록은 각 case의 raw-runtime.tar.gz 및 archive-manifest.json으로 무손실 복원한다. 추가 모델 비교는 새 ADR로 동결한다.'),
]
(A/'README.md').write_text('---'+front+'---\n\n# 조사 판단 연결 실제 비용 관찰\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
for q in m['questions']:
    p=A/'실험'/q['file']
    s=p.read_text().replace('실행 후 기록.',json.dumps({'comparability':comparability[q['case_id']],
        'observation':manual['cases'][q['case_id']]},ensure_ascii=False,indent=2))
    p.write_text(s);q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
(A/'실험/README.md').write_text('# 질문별 결과\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+') — baseline/modified run-001; 상세 결과 RESULT.txt' for q in m['questions'])+'\n')
subprocess.run([sys.executable,'-B',str(T/'archive.py')],check=True)
paths=[A/'RESULT.txt',*T.glob('*.py')]+[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']
artifact=read(A/'artifacts/manifest.json')
artifact['files']=[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,
    'description':'Frozen inputs, observed outcomes and lossless failure records','contains_raw_prompts_and_outputs':p.name.endswith('.gz')} for p in sorted(set(paths))]
put(A/'artifacts/manifest.json',artifact)
for args in (['hash','--path',str(A)],['status','--path',str(A),'--status','completed','--note',
    'Observed all four requests; provider interruptions retained; no adaptive replay or MAIN change.'],
    ['validate','--path',str(A),'--final']):
    subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py',*args],check=True)
print(summary)
