from common import *
import sys,re,tarfile,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS
s=read(ART/'stage.json');c=ROOT/s['root'];m=read(ADR/'실험/manifest.json')
f=read(sorted(ART.glob('design-rev-*.json'))[-1])
assert all(sha(c/n)==h for n,h in f['files'].items())
assert sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_1031/run_contracts.py')==f['runner_sha256']
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']
log=(ART/'contracts-enabled.log').read_text()
assert ' failed,' not in log and 'ERRORS' not in log and 'FAILURES' not in log
passed=int(re.search(r'(\d+) passed',log).group(1))
baseline_graph=read(ROOT/'04_EXPERIMENTS/ADR/EXPERIMENT_GRAPH.json')['validation_errors']
save(ART/'graph-before-final.json',baseline_graph)
changed=[n for n,h in f['files'].items() if s['working_before'].get(n)!=h]
for n in changed:
 assert (sha(ROOT/n) if (ROOT/n).exists() else None)==s['working_before'].get(n),n
result={'status':'complete','verdict':'IMPLEMENTED_CONTRACT_VERIFIED_MODEL_EFFECT_UNMEASURED',
 'final_revision':m['design']['code_isolation']['candidates'][0]['revision_id'],
 'final_targeted_passed':passed,'broader_passed_before_profile_enable':140,
 'preexisting_test_import_failure':'test_definition_context used an obsolete test function name/signature; repaired and included in final checks.',
 'contract_logs':{p.name:sha(p) for p in ART.glob('contracts-*.log')},
 'external_model_calls':0,'legal_answer_quality_scored':False,'selected_MAIN_changed':False,'GENOS_changed':False,
 'limitations':['Synthetic API/source contracts only; real question latency, tokens and semantic correctness not measured.',
 'Two means distinct resolved endpoints in one explicitly chosen scope. At three or more, retain the menu. Unresolved targets remain unresolved.',
 'Shared permission, original/hash, deadline and tool/read budgets remain. Automatic batch has12000 new-character ceiling including ancestors; oversize retains menu.',
 'No recursive automatic expansion. Automatic originals may be selected explicitly to inspect another connection directory.'],
 'working_integration_authority':'User requested this concrete implementation; selectively integrate contract-tested working code and enable working profile. Product MAIN promotion is not performed.'}
save(ART/'result.json',result)
save(ART/'integration-decision.json',{'result_sha256':sha(ART/'result.json'),'files':changed,
 'before':{n:s['working_before'].get(n) for n in changed},'after':{n:f['files'][n] for n in changed}})
with tarfile.open(ART/'working-before.tar.gz','w:gz') as archive:
 for n in changed:
  if (ROOT/n).is_file():archive.add(ROOT/n,arcname=n)
for n in changed:
 (ROOT/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(c/n,ROOT/n)
assert all(sha(ROOT/n)==f['files'][n] for n in changed)
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']
save(ART/'working-integration.json',{'files':changed,'sha256':{n:sha(ROOT/n) for n in changed},
 'working_flag':True,'MAIN102_pointer_unchanged':True,'GENOS_changed':False,
 'backup_sha256':sha(ART/'working-before.tar.gz'),
 'rollback':'Restore only listed preexisting files from working-before.tar.gz after checking current after-hashes; remove the two listed new test files only if unchanged. MAIN pointer is untouched.'})
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'),executed_arm_ids=['candidate'])
m['results'].update(status='complete',by_arm={
 'baseline':{'status':'complete','correct':None,'total':0,'accuracy':None,'reason':'Historical parent only; not a paired model/retrieval comparison.'},
 'candidate':{'status':'complete','correct':None,'total':0,'accuracy':None,'contract_tests_passed':passed}},
 judge_disagreements=0,usage={'physical_calls':0,'input_tokens':0,'output_tokens':0},
 latency={'model_latency':None,'reason':'No external model calls; contract logs record test elapsed time.'})
save(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1]
parts=[result['verdict'],
 '선택 연결 목록은 보존되지만 원문 읽기는 다시 모델 선택이었다. 상위 항·조의 자체 본문이 원문 문맥으로 전달돼도 연결 출발 범위에서는 빠졌다.',
 m['design']['hypothesis']+'\n\n'+m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],
 '일반 합성 계약·실제 로컬 API 소비자 검사. 외부 모델·정답률·검색 효과 비교 없음. 새 기능 on과 기존 경로 off를 명시적으로 검사한다.',
 '현재 작업 코드에서 격리 snapshot을 만들고 각 검사 전 revision을 고정했다. 기존 실제 데이터 세대·선택 MAIN102 포인터 불변. 신규 외부 호출0. [동결](artifacts/design-rev-005.json).',
 f'신규17검사 통과 뒤 실제 상위 본문 연결·권한·중복 검사를 추가했다. 확대140검사 통과와 기존 테스트 함수명 ImportError1개를 확인했다. 해당 호출을 현행 함수/인자로 수정했다. 최종 설정 활성화 후 관련{passed}검사 통과. [로그](artifacts/contracts-enabled.log).',
 '첫 검사에서는 새 정책 등록 누락, 다음에는 미해결 제목 참조로 인한 불필요한 동반 조회 차단을 발견했다. 미해결 연결과 확인된 대상의 확보 상태를 분리하고 기존 실패 로그와 revision을 보존했다. 모델 효과 실험 결과를 재작성한 것이 아니다.',
 '모델 호출·토큰·비용0. 합성 테스트를 순차 실행했고 주소 공간3GiB 상한을 적용했다. 실행 중 RSS약0.5GiB·가용 RAM11GiB를 관찰했다. 실제 질문의 토큰/지연 개선은 미측정.',
 '선택한 구조 단위의 원문과 상위 자체 본문에 걸린 실제 연결을 함께 제시한다. 완전한 목록의 서로 다른 확인 대상2개 이하는 기존 reader로 동반 확보한다.3개 이상·크기/예산 한도·불완전 조회는 목록과 이유를 보존한다. 새 연결의 자동 재귀 조회는 없다.',
 '\n\n'.join(result['limitations']),
 '사용자가 요청한 구현을 작업 코드에 선택 통합하고 작업 profile의 small_connection_context=true로 활성화했다. 작업 코드 검증이며 MAIN102와 GENOS 선택·배포는 변경하지 않았다. [파일 해시와 복원](artifacts/working-integration.json). 실제 질의 의미 개선은 미검증이므로 quality/decision eligibility를 올리지 않는다.',
 '실행: .venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_1031/run_contracts.py <해당 snapshot 검사 경로> -q. 결과 로그·revision은 덮어쓰지 않는다. run_tool.py adr_structure.py validate --final 및 graph 검사 결과는 final-checks.json에 남긴다.']
assert len(parts)==len(ADR_HEADINGS)
(ADR/'README.md').write_text('---'+front+'---\n\n# 연결2개 이하 원문 동반과 상위 본문 연결\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(ADR_HEADINGS,parts)))
(ADR/'실험/README.md').write_text('# 합성 계약 검사\n\n등록된 실제 질문 실행은 없으며 외부 모델 호출0이다. 테스트와 실제 API 소비자 결과는 [검사 로그](../artifacts/contracts-enabled.log)에 보존했다.\n')
(ADR/'RESULT.txt').write_text('작업 코드 구현·활성화 완료. MAIN102·GENOS 미변경.\n연결 대상2개 이하 자동 원문,3개 이상 목록. 선택 범위와 상위 자체 본문의 연결만 포함하며 형제 항·호 제외.\n추가 모델 호출0, 자동 재귀 없음, 기존 예산·권한·원문 검증 유지.\n최종 관련 검사 '+str(passed)+'개 통과. 실제 질문 모델 효과 미검증.\n')
p=ROOT/'04_EXPERIMENTS/ADR/README.md';t=p.read_text();link='ADR-1031-small-connections-parent-context/README.md'
assert link not in t
p.write_text(t.replace('# ADR workspace\n','# ADR workspace\n- [ADR1031 연결2개 이하 자동 원문·상위 본문 연결]('+link+') — 합성 API 계약 검증·작업 구현, 모델 효과 미검증.\n'))
print(json.dumps({'passed':passed,'integrated_files':len(changed),'main_unchanged':True}))
