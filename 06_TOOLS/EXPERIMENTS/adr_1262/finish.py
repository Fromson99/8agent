"""Summarize preserved terminal evidence; never dispatch a model or change DB."""
from pathlib import Path
import collections
import hashlib
import json
import sys

R = Path('/home/jin/8-AGENT')
A = R / '04_EXPERIMENTS/ADR/ADR-1262-main130-progress-dedup-live'
D = A / 'artifacts/design'
O = A / 'artifacts/run-001'
P = O / 'live/gold-369'
U = R / '09_ARTIFACTS/AUDITS/20261031-oracle-progress-dedup-main'
read = lambda p: json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()
sys.path.insert(0, str(R / '06_TOOLS/maintenance'))
from experiment_json import write_summary as put

x = read(O / 'audit-decoded.json')
r = read(P / 'result.json')
s = read(O / 'storage-audit.json')
sql = read(O / 'sql-audit.json')
cap = read(O / 'capacity-after.json')
before = read(D / 'capacity-before.json')
final = read(O / 'final-readback.json')
quota = read(O / 'retained-quota.json')
calls = read(P / 'calls.json')
samples = [json.loads(v) for v in (P / 'resource-samples.jsonl').read_text().splitlines()]
capacities = [json.loads(v) for v in (P / 'capacity-samples.jsonl').read_text().splitlines()]
failure = [e['payload'] for e in x['events'] if e['kind'] == 'RUN_FAILED']
rejected = [e['payload'] for e in x['events'] if e['kind'] == 'COMPLETION_ASSESSMENT_REJECTED']
issues = collections.Counter(q['code'] for v in failure for q in v.get('diagnostics', {}).get('output_contract', {}).get('issues', []))
states = final['oracle_run_states']
native_success = final['strict_success']
status = 'NATIVE_FINAL_ANSWER_VERIFIED' if native_success else 'MODEL_TRANSPORT_UNKNOWN' if x['unknown_outcomes'] else 'NATIVE_FINAL_REVIEW_REJECTED' if r['http_status'] == 422 else 'NATIVE_FINAL_FAILED'
last = calls[-1]
diagnostic = last.get('diagnostics', {})
unknown_detail = {k: diagnostic.get(k) for k in ('received_http_status', 'received_chunks', 'received_bytes', 'whitespace_only', 'complete', 'elapsed_seconds', 'worker_reaped', 'worker_returncode')}
active = read(R / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
technical = read(R / '04_EXPERIMENTS/ADR/ADR-1261-oracle-progress-snapshot-dedup/artifacts/run-001/result.json')
checks = {
    'selected_main130': active['generation'] == 130 and active['release_id'] == 'oracle-progress-dedup-20261031-r1',
    'selected496_unchanged': r['engine_code_unchanged'],
    'frozen_files_unchanged': not x['changed_frozen_files'],
    'transport_pins_verified': read(P / 'transport-after.json')['verified'],
    'no_unknown': x['unknown_outcomes'] == 0,
    'source_integrity_acl': not x['source_mismatches'] and not x['acl_violations'],
    'all_progress_history_exact': s['all_progress_history_byte_hash_verified'],
    'actual_large_progress_v4': s['all_eligible_roots_v4'] and s['large_progress_roots_v4'] > 0,
    'structured_responses_retained': x['structured_proposals'] == x['complete_responses'],
    'no_raw_diagnostic_leaks': not x['raw_response_leaks'],
    'nfs_unconfigured_references_explicit': all(v['request_is_diagnostic_reference'] and v['capture_status'] == 'UNCONFIGURED' for v in x['attempts']),
    'no_physical_runtime_sqlite': not x['physical_runtime_exists'],
    'physical_budget_equal': x['physical_budget_matches'],
    'fixed270MiB_retained': quota['hard270MiB_still_present'],
    'allocation_disk_under90': cap['within_limit'] and max(v['used_percent'] for v in capacities) <= 90,
    'native_sql_budgets': r['agent_sql_calls'] <= 10000 and r['sql_calls'] <= 10000 and r['shared_sql_calls'] <= 25000,
    'normal_exit_no_resource_stop': read(O / 'process-exit.json')['exit_code'] == 0 and not (P / 'resource-stop.json').exists(),
    'root_service13': read(U / 'main-entry.json')['passed'],
    'native_final_answer': native_success,
}
result = {
    'status': status, 'strict_success': all(checks.values()), 'checks': checks,
    'main_generation': 130, 'engine_release': active['release_id'], 'engine_files': 496,
    'frozen_files': len(read(D / 'freeze.json')['files']), 'http_status': r['http_status'],
    'run_states': states, 'answer_present': x['answer_present'], 'answer_chars': x['answer_chars'],
    'assessment_rejections': len(rejected), 'validation_issue_codes': dict(issues),
    'native_failure_codes': [v.get('code') for v in failure],
    'phase_at_failure': [v.get('phase_at_failure') for v in failure],
    'final_stage_reached': any(v.get('stage') in ('memory-assess', 'memory-assess-repair') for v in calls),
    'last_transport_stage': last.get('stage'), 'last_transport_diagnostics': unknown_detail,
    'post_unknown_calls': x['post_unknown_calls'],
    'publication_count': len(x['publications']), 'actual_model_calls': len(calls),
    'finish_reasons': x['finish_reasons'], 'unknown_outcomes': x['unknown_outcomes'],
    'provider_counts': x['provider_counts'], 'reported_cost_usd': x['reported_cost_usd'],
    'reported_input_tokens': x['reported_input_tokens'], 'reported_output_tokens': x['reported_output_tokens'],
    'missing_usage_calls': x['missing_usage_calls'], 'seconds': r['seconds'],
    'model_seconds': x['model_seconds'], 'peak_rss_GiB_rusage': r['peak_rss_KiB'] / 1024**2,
    'sampled_resources': x['resources'], 'process_swap_sample_peak_MiB': max(v['VmSwap'] for v in samples) / 1024**2,
    'oracle_tables': x['oracle_tables'], 'source_checks': x['source_checks'],
    'canonical_nested_source_checks': x['nested_checks'], 'source_mismatches': x['source_mismatches'],
    'acl_violations': x['acl_violations'], 'structured_model_responses': x['structured_proposals'],
    'storage': s, 'sql_groups': sql['groups'], 'shared_sql_calls': r['shared_sql_calls'],
    'capacity_admin_queries': r['capacity_queries'], 'post_run_audit_sql_calls': x['audit_sql_calls'],
    'capacity_before': before, 'capacity_after': cap,
    'allocation_delta_MiB': (cap['sidda_used_bytes'] - before['sidda_used_bytes']) / 1024**2,
    'max_allocation_percent_original300MiB': max(v['used_percent'] for v in capacities),
    'quota_retained270MiB': True, 'quota_changes_by_this_trial': 0,
    'ddl_or_additional_deletes_by_this_trial': 0, 'no_followup_question_retry_after_terminal': True,
    'field_genos_ords_oracle19_actual_nfs_certified': False, 'quality_certified': False,
    'post_run_storage_audit_source_sha256': sha(Path(__file__).with_name('storage_audit.py')),
    'frozen_criteria_copy_notes': 'Criteria retained old495/namespace1258 text; exact frozen binding and actual proof are MAIN130496/new namespace1262. Frozen inputs were not rewritten.',
}
put(O / 'result.json', result)
put(U / 'live-result.json', result)

text = f'''MAIN130 진행 상태 중복 저장 축소·실제 Oracle 실험 — 2026-10-31

반영 완료: MAIN130 / {active['release_id']} / 선택496파일.
저장 모듈2개와 엔진pin31개(선택변경33개)만 반영했다. 추가 테이블/컬럼/DDL0.
기본NFS 모드 유지, DP=oracle에서 원문/검색·구조화기록은Oracle, 상세진단은기존NFS정책유지.
큰 stage_progress 전체사본을 손실없이 내용조각으로 나눠 같은 조각은 namespace 안에서 공유한다.
각 이력의원래SHA256/바이트와온톨로지/근거/예산/재개/CAS는보존한다. 최신이력만남기는방식이아니다.
64KiB미만·일반body는기존2/3형식유지, 큰진행상태만새4형식. 누락/손상/순환참조는거절.
조각내구저장후참조root공개,중단업로드/재접속/rollback/이전형식혼합검사.
원본기록삭제·기존namespace재작성/이관0. 기존할당공간을즉시줄이는정리작업이아니며새기록부터적용한다.

고정된동일과거342이력 비교(ADR1261)
모든342이력완전복원·전체이력보존. 저장JSON본문26,105,777→3,948,560문자(84.875%감소),
BODY조각9,763→2,716(72.181%감소), SQL1,752→2,044(16.667%증가).
실제Oracle adapter의격리메모리전송재생이며segment할당/전체응답시간개선율이아니다.
193pytest통과+새기술holdout24바이트동일복원, 기존14실패동일/새실패0.
실제로컬Oracle저장/부분업로드/scope분리/재개/재접속포함. 서비스root진입13조건통과.

실제LLM1회(ADR1262)
결과{status}, HTTP{r['http_status']}, 답변존재{x['answer_present']}, Oracle상태{states}.
실제{len(calls)}물리호출/finish{x['finish_reasons']}/UNKNOWN{x['unknown_outcomes']}, provider{x['provider_counts']}.
Qwen qwen/qwen3.8-27b·ParasailFP8우선·thinkingoff·출력상한없음, native계약변경0.
실행{r['seconds']:.3f}초, 모델경계합{x['model_seconds']:.3f}초,
보고입력{x['reported_input_tokens']}/출력{x['reported_output_tokens']}토큰·${x['reported_cost_usd']:.8f}·사용량누락{x['missing_usage_calls']}.
최종검토거절{len(rejected)}건, 최종실패issues{dict(issues)}. 답변없으면검증을우회하여성공처리하지않았다.
마지막요청{last.get('stage')}: {unknown_detail}.
이번실패는INVESTIGATE중MODEL_TRANSPORT_ERROR/UNKNOWN이며최종ASSESS에도달하지않았다.
HTTP200헤더이후공백60조각660바이트만수신하고약179.08초에기한종료했다. 공급자내부원인은미확인.
UNKNOWN후추가호출{x['post_unknown_calls']}·같은질문재실행0. UNKNOWN요청토큰/비용미보고분은합산에포함되지않았다.
새프로세스Oracle복원: {x['oracle_tables']}, 구조화모델응답{x['structured_proposals']}개.
확보원문{x['source_checks']}대조·canonical중첩{x['nested_checks']}대조에서불일치{len(x['source_mismatches'])}/권한위반{len(x['acl_violations'])}.
동결{result['frozen_files']}파일변경0·전송기기원/hash매물리전후검증·선택MAIN130496불변.
전체요청payload의독립재조립동등성을주장하지않는다. 연구raw/canonical은gzip·해시로별도보존.

실제새기록의저장·용량
진행이력{s['progress_history_rows']}행·고유본문{s['progress_unique_history_bodies']}개전부원래바이트해시복원,
큰진행상태{s['large_progress_roots_v4']}개새4형식사용, 전체BODY{s['all_stored_bodies_hash_verified']}개해시검증.
이번동일큰진행이력의가상기존3형식{s['same_actual_roots_hypothetical_v3_json_chars']:,}문자대비
실제4형식root+공유조각{s['actual_v4_roots_and_unique_leaf_json_chars']:,}문자
({s['envelope_char_reduction_on_same_eligible_history']*100:.3f}%감소). 할당공간과다른분모다.
SIDDA할당{before['sidda_used_bytes']/1024**2:.3f}→{cap['sidda_used_bytes']/1024**2:.3f}MiB
(이번기간+{result['allocation_delta_MiB']:.3f}MiB), 기존300MiB기준{before['sidda_used_percent']:.4f}→{cap['sidda_used_percent']:.4f}%.
hard상한270MiB유지·quota확장0·추가삭제/공간반환DDL0.
할당증가는LOB/index/기존extent재사용을포함하므로순수본문크기나과거다른실험대비인과효과로해석하지않는다.
디스크{cap['disk_used_percent']:.3f}%/Windows{cap['host_disk_used_percent']:.3f}%,90%이내.
SQL{sql['groups']}, 공유{r['shared_sql_calls']}회. 용량관리{r['capacity_queries']}회/사후감사별도.
SQL시간은START→ACK전송·직렬화·DB포함, Oracle CPU시간만아니다.
rusage RSS{result['peak_rss_GiB_rusage']:.3f}GiB, 표본RSS{x['resources']['max_RSS_GiB']:.3f}GiB,
가용RAM최소{x['resources']['min_available_GiB']:.3f}GiB/hostswap증가최대{x['resources']['max_host_swap_growth_MiB']:.3f}MiB.
프로세스VmSwap표본최대{result['process_swap_sample_peak_MiB']:.3f}MiB.

반영경계·운영주의
원래기본데이터/GoldR18물리매핑/연결기/온톨로지설정/검색/모델계약은유지,Gold enginebinding만MAIN130.
병행미반영작업은보존했다. 전체작업tree=선택코드가아니며이번소유2모듈만작업/후보/선택정확일치.
새형식4기록생성뒤에는4를읽는복구릴리스를사용한다. 구MAIN129로새namespace를읽으면안된다.
실제NFS마운트없음: prompt/원시응답은UNCONFIGURED참조, 제품로컬/Oracle상세로그fallback0.
구조화응답의raw/debug/reasoning누출0, 디스크runtime/영구SQLitefallback0.
현장GENOS·ORDS·Oracle19·실제NFS내구성·부하·법률품질은미검증. Git push/메일/현장배포0.
criteria복사문구495/namespace1258은동결원문보존; 실제동결binding/실행증거는MAIN130496/새1262namespace다.
'''
report = U / '메인반영과_실제실험_결과.txt'
assert not report.exists()
report.write_text(text)

m = read(A / '실험/manifest.json')
assert m['reservation']['status'] == 'in_progress'
m['runs'][0].update(status='complete', sha256=sha(O / 'result.json'))
m['results'].update(status='complete', by_arm={'baseline': {'status': 'complete', 'historical_only': True, 'new_model_calls': 0}, 'live': {'status': 'complete', **result}}, usage={'physical_model_calls': len(calls), 'reported_cost_usd': x['reported_cost_usd'], 'input_tokens': x['reported_input_tokens'], 'output_tokens': x['reported_output_tokens']}, latency={'seconds': r['seconds'], 'model_seconds': x['model_seconds'], 'p95': None}, error_taxonomy=[] if native_success else [{'category': status, 'codes': dict(issues), 'http_status': r['http_status']}])
(A / '실험/manifest.json').write_text(json.dumps(m, ensure_ascii=False, indent=2) + '\n')
heads = ['결정 요약', '문제와 변경 전 구조', '가설과 사전 판정 기준', '실험 설계', '데이터·모델·재현성', '결과', '사례별 오류 분석', '비용·지연·회수 규모', '해석', '한계와 일반화 가능 범위', '운영 결정·롤백 조건', '재현 명령']
vals = [
    f"{'Accepted' if native_success else 'Rejected'}: {status}. 저장기술승격1261과실제최종답변결과를구분한다.",
    '진행상태전체사본반복저장. 기술1261에서모든이력바이트를보존하며공유조각으로축소후MAIN130반영.',
    '[호출전동결기준](artifacts/design/criteria.json). source/Agent무결성·270MiB상한·정상최종답변. 검토계약우회0.',
    '알려진369질문새namespace1trial. baseline은1261기술기록참조, 새모델baseline0. 전체질문재전송0.',
    '선택MAIN130496·591동결파일·GoldR18/온톨로지ON DB·실제Oracle·고정Qwen27b/전송기. 독립judge0.',
    '[집계](artifacts/run-001/result.json)\n\n' + text,
    f'최종HTTP{r["http_status"]}, 이슈{dict(issues)}. 일반저장변경이법률판단오류를고친것으로확대하지않는다.',
    f'{r["seconds"]:.3f}초/{len(calls)}물리호출/${x["reported_cost_usd"]:.8f}. 검색정책변경0·단일표본p95없음.',
    '모든진행이력/구조화제안과원문권한검증은보존. 실제최종답변성공여부는별도체크로기록.',
    '알려진질문인샘플1개. LLM경로는과거1258과달라실행시간/DB할당증가인과개선율을주장하지않는다. 실제NFS/GENOS/19c/ORDS미검증.',
    '기술적으로승격된MAIN130유지. 기존270MiB상한유지·구형reader에새layout4 namespace를넘기지않음. 추가모델재시험은새ADR.',
    'checks/preflight/capacity/freeze→quota_fence→1trial→audit/sql/storage/capacity/final_readback. 완료trial재실행금지.',
]
front = (A / 'README.md').read_text().split('---', 2)[1].replace('status: Proposed', 'status: Accepted' if native_success else 'status: Rejected')
(A / 'README.md').write_text('---' + front + '---\n\n' + '\n\n'.join(f'## {i}. {h}\n\n{v}' for i, (h, v) in enumerate(zip(heads, vals), 1)) + '\n')
qh = ['실행 메타', '사용자 질문 원문', '기준답변 — 채점 전용, 제품 입력 비공개', '제품 입력을 구성한 원값', '제품 모델 호출 — run·arm별 실제 원문', '중간 LLM 호출 — router/compiler/verifier/repair', '채점 호출과 반복 판정', '사례 최종 판정']
qv = ['run-001/live·MAIN130496·DP=oracle·1새namespace', read(D / 'cases.json')[0]['request']['json']['question'], '기준답변제품미제공·독립judge0', '[동결](../artifacts/design/freeze.json)·[Oracle감사](../artifacts/run-001/audit-decoded.json)\n\n### 회수·탈락 단계 원장 — run·arm별\n\n검색정책변경0·원문/권한대조는감사참조.', '[raw](../artifacts/run-001/live/gold-369/raw/)·[canonical](../artifacts/run-001/live/gold-369/canonical/), gzip·해시보존. 전체payload독립동등성주장0.', f'실제{len(calls)}물리·finish{x["finish_reasons"]}. 세부단계는calls.json참조.', '별도judge/재채점0·터미널후추가모델0', f'{status} / HTTP{r["http_status"]} / Oracle{states}']
(A / '실험/질문-001-gold-369.md').write_text('# gold-369\n\n' + '\n\n'.join(f'## {i}. {h}\n\n{v}' for i, (h, v) in enumerate(zip(qh, qv), 1)) + '\n')
(A / '실험/README.md').write_text(f'# 실험 인덱스\n\n[gold-369](질문-001-gold-369.md): {status}, 실제{len(calls)}물리, 모든진행이력Oracle해시복원.\n')
artifact_path = A / 'artifacts/manifest.json'
artifact = read(artifact_path)
artifact['description'] = 'Frozen MAIN130 trial, preserved native terminal result and read-only Oracle/source/storage audits'
artifact['files'] = [{'path': str(p.relative_to(R)), 'sha256': sha(p), 'bytes': p.stat().st_size, 'description': 'Frozen design or preserved actual observation/post-run audit', 'contains_raw_prompts_and_outputs': any(v in str(p) for v in ('/raw/', '/canonical/', 'experiment-client'))} for p in (A / 'artifacts').rglob('*') if p.is_file() and p != artifact_path]
artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'status': status, 'checks': checks, 'report': str(report)}, ensure_ascii=False))
