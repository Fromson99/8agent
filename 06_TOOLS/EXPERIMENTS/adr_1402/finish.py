"""Record hard resource exit without inventing a provider or API response."""
from common import *
import tarfile
b=ART/'public-live/RISK-CM-029-selected-scope-r3';t=read(b/'terminal-audit.json');calls=t['calls'];a=read(ART/'source-wire-audit.json')['cells'][0]
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');base=read(DES/'baseline.json');assert active==base['pointer']
assert a['budget_matches'] and not any(a[k] for k in ('source_mismatches','acl_violations','wire_mismatches'))
assert all(sha(ROOT/base['release']['code_root']/n)==h for n,h in base['release']['files'].items())
assert len(calls)==4 and [x['status'] for x in calls]==['responded']*3+['unknown']
case=read(DES/'live-cases.json')[0]
usage={'physical_attempts':4,'normal':3,'unknown':1,'reported_cost_usd':sum((c.get('usage') or {}).get('cost',0) for c in calls),'reported_tokens':sum((c.get('usage') or {}).get('total_tokens',0) for c in calls),'unreported_unknown_cost':None,'budget_reserved':a['budget_reserved'],'common_reviews':1,'common_pass':1,'common_repair':0,'sends_after_unknown':0,'replay':0,'grader_model_calls':0}
stop=t['resource_stop'];resources={'swap_growth_mib':(stop['current']['swap_used']-stop['baseline']['swap_used'])/1024**2,'available_gib_at_stop':stop['current']['available']/1024**3,'rss_gib_at_stop':stop['current']['rss']/1024**3,'process_exit':125,'provider_cancel_confirmed':False,'other_worker':'Different ADR1400 DeepInfra worker was observed after admission, although prior REKA worker had exited and15-second quiet admission had passed; concurrent host activity occurred again. This does not establish provider fault.'}
verdict='MAIN147 유지. PF 질문은 첫 실제4회 중3응답을 받았으나 네 번째 보완 호출 중 로컬 스왑 증가로 강제 종료됐다. 완성답변0·마지막 원격 결과 UNKNOWN1, 추가송신0.'
analysis='최초 요청은 외규 전체 권한 범위를 올바르게 선택했고 공통 대화 감시는 PASS했다. 조사 선택은 PF 관련 제6-15조와 별표17-1의 추가 원문 필요를 명시했다. 기존 구조 검증이 별표 17-1 좌표를 SOURCE_TARGET_COORDINATE_INVALID로 거절해 원래 LLM 보완을 요청했지만, 그 호출 도중 resource guard가 종료했다. 공통 조사/최종 감시·보완 실행에 도달하지 못했으며 공통 모순 검출의 성공이나 실패로 세지 않는다. 현재 calls.json의 마지막 started 및 원래 journal을 수정하지 않고 terminal-audit.json에서 미확정 결과를 파생 분류했다. HTTP 응답·완료 답변·원격 취소는 만들어 쓰지 않았다.'
limits='등록 question_only 문항1회. 실제 MAIN 기본 온톨로지OFF·공통 감시enforce·기존 검증·40/1024/1800 예산·출력상한 없음 유지. 같은 요청 자동 재전송 없음. 원격 완료·비용·공급자 문제 원인은 확인하지 못했다. 선행1401의 첫 PF 중단은 물리호출0이며 이번4회와 구분한다. 메인 승격, 원문DB·Gold·GENOS·메일 변경0.'
report={'verdict':verdict,'question':case['steps'][0]['question'],'analysis':analysis,'limits':limits,'usage':usage,'resources':resources,'http_status':None,'api_response_received':False,'answer_success':False,'active':active,'main_changes':0,'source_audit':{k:a[k] for k in ('source_checks','delivered_checks','budget_matches','source_mismatches','acl_violations','wire_mismatches')},'quality_certified':False}
put(ART/'result.json',report)
(ART/'PF_실제질문_결과.txt').write_text(verdict+'\n\n질문: '+report['question']+'\n\n'+analysis+'\n\n'+limits+'\n\n'+json.dumps({'usage':usage,'resources':resources,'source_audit':report['source_audit']},ensure_ascii=False,indent=2)+'\n')
paths=[p for p in (b/'runtime').rglob('*') if p.is_file()];records=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(paths)]
p=b/'runtime-files-sha256.json.gz'
if p.exists():assert read(p)==records
else:write_raw_json(p,records)
if not (b/'runtime-evidence.tar.gz').exists():
 with tarfile.open(b/'runtime-evidence.tar.gz','w:gz') as tar:
  for p in paths:tar.add(p,arcname=str(p.relative_to(b)),recursive=False)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True},'selected':report},comparisons=[],judge_disagreements=0,usage=usage,latency={'known_completed_model_seconds':sum(c['seconds'] for c in calls[:3]),'last_attempt_duration':None,'completed_request_duration':None},error_taxonomy={'resource_hard_exit':1,'unknown':1,'source_target_coordinate_invalid':1,'api_response_received':False});put(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1]
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
content=[verdict,'선행1401은 MAIN147 반영과 두 질문을 완료했지만 PF 질문은 모델 호출 전 자원 중단이었다. 이번에는 그 질문의 첫 실제 모델 호출만 별도 확인했다.',json.dumps(read(DES/'criteria.json'),ensure_ascii=False),'다른 무거운 worker 종료와15초 조용한 구간을 확인해 시작했다. 이후 다른 제공자 worker가 새로 시작해 다시 동시 실행이 관측됐다. 이전 자원 기준을 완화하지 않고 전체 외부송신을 중단했다.','동일 MAIN147530파일·원래 Risk 질문·실제 root service·Risk팀 공개28문서·Qwen3.8 Parasail FP8/none·출력상한 없음. 후보·선택 SHA 동일.',verdict,analysis,json.dumps({'usage':usage,'resources':resources},ensure_ascii=False),'공통 대화 감시1 PASS만 실제 관측했다. 구조 보완 중단을 신규 이유-판단 감시 성공으로 설명하지 않는다.',limits,'MAIN147 변경0·품질 인증 아님. 미확정 물리 호출은 자동 재전송하지 않는다. 원시 started 상태, 없는 HTTP 응답과 UNKNOWN 판정을 구분해 보존한다.','06_TOOLS/EXPERIMENTS/adr_1402/setup.py → idle admission → live.py RISK-CM-029 --scope-r3 → terminal audit → audit.py → ledger.py → finish.py. 실제 재시도는 새로운 승인/미확정 상태 검토와 별도 ADR로 구분한다.']
(ADR/'README.md').write_text('---'+front+'---\n\n# MAIN147 PF 질문 실제 확인\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,content),1))+'\n')
q=m['questions'][0]
parts=[('실행 메타',content[4]),('사용자 질문 원문',report['question']),('기준답변 — 채점 전용, 제품 입력 비공개','question_only, 독립 승인 정답률 없음. 추가 원문 필요 판단과 실제 선택을 대조한다. 정답/근거 후보 주입0.'),('제품 입력을 구성한 원값','### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger.json.gz와 source-wire-audit.json. scope-selection.json·canonical·raw 보존.'),('제품 모델 호출 — run·arm별 실제 원문','artifacts/public-live/RISK-CM-029-selected-scope-r3/raw와 canonical. 호출4 request는 있고 response는 없음. terminal-audit.json과 원래 calls.json을 구분한다.'),('중간 LLM 호출 — router/compiler/verifier/repair',analysis),('채점 호출과 반복 판정','추가 채점 모델0. 재전송0, 미확정 원격 비용 없음으로 단정하지 않음.'),('사례 최종 판정',verdict)]
(ADR/'실험'/q['file']).write_text('# PF 실질문\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(parts,1))+'\n');(ADR/'실험/README.md').write_text('# 실제 질문\n\n[PF 결과]('+q['file']+')\n')
paths={p for p in ART.rglob('*') if p.is_file() and '.observer-versions' not in p.parts and p!=ART/'manifest.json'};paths.update(Path(__file__).parent.glob('*.py'))
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1402','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Actual Qwen, hard resource exit, immutable original journals or read-only terminal audit','contains_raw_prompts_and_outputs':('raw' in p.parts or 'canonical' in p.parts)} for p in sorted(paths)]})
print(json.dumps({'verdict':verdict,'usage':usage},ensure_ascii=False))
