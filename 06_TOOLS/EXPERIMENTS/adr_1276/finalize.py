from common import *
import re
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert active['generation']==132 and active['release_id']==RELEASE
p=ROOT/active['manifest_path'];release=read(p);entry=read(OUT/'main-entry.json');gold=read(OUT/'gold-entry.json');api=read(ART/'prepared-api/result.json')
assert entry['passed'] and gold['passed'] and api['passed']==13 and api['failed']==0
assert all(sha(ROOT/release['code_root']/n)==sha(ROOT/n)==h for n,h in release['files'].items())
inherited=read(DES/'inherited-verification.json');live=read(ROOT/inherited['actual']['path'])
result={'status':'PASS','release_id':RELEASE,'generation':132,'serving_files':504,'changed_serving_files':36,
 'deployment_basis':active['deployment_basis'],'quality_certified':False,'prepared_api_passed':13,'root_conditions':len(entry['checks']),'gold_conditions':len(gold['checks']),
 'inherited_verification':inherited,'actual_qwen_status':live['status'],'new_model_calls':0,'oracle_calls':0,'genos_deployed':False,'git_pushed':False,
 'rollback':'MAIN131 official rollback plus saved Gold binding; retain layout4 and all data',
 'limitations':['Incomplete source-only replies do not certify legal conclusions','Provider UNKNOWN remains terminal with no automatic resend','Semantic follow-up routing and command checks still incur model calls','Oracle/GENOS/NFS and broad legal-quality verification not performed']}
put(RUN/'result.json',result);put(OUT/'summary.json',result)
m=read(ADR/'실험/manifest.json');m['design']['frozen_pre_cutover_isolation']=m['design']['code_isolation'];m['design']['operational_audit']=True
m['design']['code_isolation']={'schema_version':'adr-code-isolation-v1','mode':'user_directed_cutover','reason':'User authorized all completed work in MAIN and requested remaining recovery fixes; exact verified delta selected through official prepare/apply.',
 'production_paths_modified_before_decision':True,'runtime_import_allowed':True,'production_registry_registered':True,'main_wiring_unchanged':False,'candidates':[],
 'release':{'manifest_path':str(p.relative_to(ROOT)),'sha256':sha(p),'release_id':RELEASE}}
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'generation':131},'selected':result},judge_disagreements=0,usage={'new_model_calls':0,'oracle_calls':0},latency={'prepared_api_seconds':api['elapsed_seconds']},error_taxonomy=[{'type':'KNOWN_EXTERNAL_LIMITS','detail':result['limitations']}]);put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[
 '사용자의 전체 MAIN 반영 지시와 후속 수정 지시에 따라 MAIN132/final-review-multiturn-20261102-r1을 공식 prepare/apply로 선택했다. 서빙504파일 중 제품5+pin31=36변경. Gold 엔진도 같은 MAIN132를 사용한다.',
 'MAIN131의 최종 검토 연결 누락과 보완 소진422를 기술1274에서 수정했다. 모델의 명시 연결을 유일하게 결속하고, 미완료 판단은 채택하지 않은 채 원문 응답과 후속 대화를 연결한다.',
 '[기준](artifacts/design/criteria.json): 검증된518파일과 정확 일치, 공식 서빙504·API13·root/Gold 소비자 일치, 원문/매핑/권한/예산/저장 정책 유지. 새 품질 인증 없이 사용자 지시 반영한다.',
 'MAIN131 baseline을 보존하고 검증된36차이만 작업 코드에 반영해 새 후보를 동결했다. 이후 공식 preview/rebase/prepare와 준비 API를 통과한 뒤 apply했다. 다른 작업 코드를 후보로 덮어쓰지 않았다.',
 '1274 최종 후보 및1277 실제 실험과 전체518해시가 같다. 기존원문 세대·Goldquery R18·물리 매핑·온톨로지 설정·연결기·Oracle layout4 reader·상세NFS 정책을 보존했다. 이번 반영 감사 새모델/Oracle0.',
 f'준비 API13·실제 root{len(entry["checks"])}조건·Gold{len(gold["checks"])}조건 통과. 기술641회귀·신규17·추가{inherited["followup_display_checks"]}검사(범위 중복)는1274 기록에 결속. 실제Qwen1277={live["status"]}, {live["physical_calls"]}물리·UNKNOWN{live["unknown"]}; 이 결과를 새 독립 표본으로 합산하지 않는다.',
 '1274의 fixture 선택/좌표와 화면 timeout 표식 회귀를 최종rev-002에서 확인했다. 실제 실패/미확인 및 원래 거절 제안은 그대로 보존하며 source-only 결과를 법률 결론 성공으로 바꾸지 않는다.',
 f'반영 중 모델 비용0·Oracle/DDL0. 준비 API{api["elapsed_seconds"]:.3f}초는 합성 소비자 검사 경과시간이며 실제 질의 속도 개선율 아님.',
 '현재 서비스가 검증한 정확한 코드를 선택한다는 구조적 결과다. USER_DIRECTED_CUTOVER·quality_certified=false이며 현장 배포 또는 전체 법률품질 인증이 아니다.',
 '공급자 UNKNOWN/504 내부 원인, 실제Oracle 전체RAG·GENOS·NFS·부하·법률품질은 별도다. 후속 분류/명령작성/검토의 모델 경계도 남아 있다. 최종 검토실패 시 원문응답에는 결론이 없다.',
 'MAIN132 선택. 원복은 해당 릴리스 rollback/ACTIVE_RELEASE.json의MAIN131과 감사gold-before.json의binding을 함께 복원한다. Gold connect.py는 이번에 바뀌지 않았다. 새기록/데이터 삭제0·layout4 미지원MAIN129로 원복금지.',
 'prepare.py → prepare_release.py → maintenance/check_agent_loop_recovery.py --api-only --code-root <준비릴리스> → activate.py → main_entry.py → gold_entry.py → finalize.py. 완료 apply/실모델 셀을 재실행하지 않는다.'
]
p=ADR/'README.md';front=p.read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Accepted',front);front=re.sub(r'(?m)^main_wiring:.*$','main_wiring: user-directed-cutover',front)
p.write_text('---'+front+'---\n\n# ADR1276 최종 검토 복구 MAIN132\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
(ADR/'실험/README.md').write_text('# 반영 감사\n\n[결정](../README.md) · [실행 manifest](manifest.json) · [산출물](../artifacts/manifest.json). 새 모델/Oracle 호출0.\n')
p=ART/'manifest.json';am=read(p);files=[x for x in ART.rglob('*') if x.is_file() and x!=p and '/runtime/' not in str(x) and '/selected-entry-runtime/' not in str(x) and '/__pycache__/' not in str(x)]+[x for x in OUT.iterdir() if x.is_file()]
am['files']=[dict(bind(x),bytes=x.stat().st_size,description='Frozen verified delta and official MAIN consumer receipts',contains_raw_prompts_and_outputs=False) for x in sorted(files)];p.write_text(json.dumps(am,ensure_ascii=False,indent=2)+'\n')
print('MAIN132 complete',result['actual_qwen_status'])
