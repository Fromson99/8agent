"""Close the observed runs without turning interrupted usage into a comparison."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0944-research-decision-live-cost'
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
    'no_resource_guard_stop':all(v['stop_reason'] is None for v in resources),
    'scope_and_side':all(read(p)['all_scope_checks_pass'] for p in (A/'artifacts').glob('scope-*.json')),
    'four_scope_records':len(list((A/'artifacts').glob('scope-*.json')))==4,
    'stored_originals_exact':all(v['source_mismatches']==0 for v in r['by_arm'].values()),
    'selected_quotes_exact':all(read(p)['literal_mismatches']==0 for p in O.glob('*/*/citation-audit.json')),
    'metadata_within_frozen_threshold':not any(v['metadata_overgrowth'] for v in r['paired']),
    'call_budget':all(v['model_calls']<=40 for arm in r['cases'].values() for v in arm.values()),
    'four_terminal_responses':all(v['both_terminal_responses'] for v in r['paired']),
    'all_usage_complete':all(v['usage_complete'] for arm in r['cases'].values() for v in arm.values()),
}
put(A/'artifacts/technical-checks.json',checks)
comparability={}
lines=[]
for pair in r['paired']:
    ident=pair['case_id'];b=r['cases']['baseline'][ident];n=r['cases']['modified'][ident]
    comparable=bool(pair['both_terminal_responses'] and b['usage_complete'] and n['usage_complete'])
    comparability[ident]={'comparable_completed_usage':comparable,
        'valid_input_token_ratio':pair['input_token_ratio'] if comparable else None,
        'reason':'Two terminal responses with complete recorded provider usage.' if comparable else
        'Interrupted/failed provider requests: observed token sums are partial; raw arithmetic ratio is not a cost comparison.',
        'raw_pair_record_preserved':str((O/'result.json').relative_to(R))}
    lines.append(f"{ident}: calls {b['model_calls']} -> {n['model_calls']}; recorded input tokens "
                 f"{b['input_tokens']:,} -> {n['input_tokens']:,}; comparable={comparable}; "
                 f"added field max {n['metadata_fraction_max']*100:.2f}%.")
put(A/'artifacts/comparability.json',comparability)
status='Proposed'
if not all(checks[k] for k in ('no_resource_guard_stop','scope_and_side','stored_originals_exact',
                               'selected_quotes_exact','metadata_within_frozen_threshold','call_budget')):
    status='Rejected'
summary=manual['conclusion']+'\n\n'+'\n'.join(lines)
summary+='\n고정 지시문 +32자, 새 모델 입력 필드0, 선택적 출력 need_resolution 추가. 문자 비중을 토큰 비중으로 주장하지 않는다.\n'
summary+='원문 일치 검사 '+str(sum(v['stored_original_checks'] for v in r['by_arm'].values()))+'회; 불일치 '+str(sum(v['source_mismatches'] for v in r['by_arm'].values()))+'건.\n'
summary+='알려진2사례 단회 관찰이며 법률 정답률·GENOS 성능을 인증하지 않는다. 중단된 호출의 실제 사용량은 미확인이다. 모델 재실행 없음. MAIN90 및 작업 코드 미변경 상태에서 종료했다.\n'
(A/'RESULT.txt').write_text(summary)
m['results']['error_taxonomy']=manual.get('failure_records',[])
m['results']['comparisons']=comparability
front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: '+status)
sections=[
 ('결정 요약',summary),
 ('문제와 변경 전 구조','새 원문ID 없이 변경된 조사 결과의 상위 판단, 명시적 부족 해소, 제한된 발견→읽기 연결을 수정한 완료 후보를 실제 모델로 관찰했다.'),
 ('가설과 사전 판정 기준','artifacts/design/criteria.json에 호출 전 동결. 중단을 성공으로 바꾸거나 사후 임계값을 조정하지 않는다.'),
 ('실험 설계','수정RP→기준RP→기준레버리지→수정레버리지. 같은 데이터·모델·검색·권한·예산, 요청마다 새 runtime.'),
 ('데이터·모델·재현성','working1.18와 완료0943후보1.19 각각389파일. Qwen3.8/Parasail FP8, reasoning none, fallback 없음. 기존 승인 workflow 문서 범위만 사용.'),
 ('결과','실제 토큰/호출은 artifacts/run-001/result.json, 유효 비교 여부는 artifacts/comparability.json. 실패 호출의 누락 사용량을0으로 간주하지 않는다.'),
 ('사례별 오류 분석',json.dumps(manual,ensure_ascii=False,indent=2)),
 ('비용·지연·회수 규모','\n'.join(lines)+'\n\n### 단계별 회수·탈락 원장\n\nartifacts/run-001/retrieval-ledger.json. 원문 확보/반환/최종 인용을 구분한다. 승인 gold가 없어 recall은 미측정.'),
 ('해석','변경된 조사 상태 재검토와 인용 원문 일치는 기술 검증이다. 의미 판단의 정답이나 미확보 자료의 부재 증명이 아니다. 제공자 장애가 섞인 관측은 비용 개선/악화의 근거로 쓰지 않는다.'),
 ('한계와 일반화 가능 범위','소표본 known-case probe. 저장·중복 소비자는 완료된 응답에서만 확인했다. RP 의미 판단의 한계와 레버리지 비용 미확인을 보존한다.'),
 ('운영 결정·롤백 조건','이 실험 자체는 MAIN 승격 근거가 아니다. 별도 기술 자격 검사와 작업 통합을 구분한다. 실제 비용 비교가 불완전하므로 전체 비용 증가가 없다는 결론과 MAIN 자동 전환은 보류한다.'),
 ('재현 명령','원 실행 명령은 resource-*.json. 원시 기록은 각 case의 raw-runtime.tar.gz 및 archive-manifest.json으로 무손실 복원한다. 추가 모델 비교는 새 ADR로 동결한다.'),
]
(A/'README.md').write_text('---'+front+'---\n\n# 조사 판단 연결 실제 비용 관찰\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
for q in m['questions']:
    p=A/'실험'/q['file']
    s=p.read_text().replace('실행 후 기록.',json.dumps({'comparability':comparability[q['case_id']],
        'observation':manual['cases'][q['case_id']]},ensure_ascii=False,indent=2))
    p.write_text(s);q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
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
