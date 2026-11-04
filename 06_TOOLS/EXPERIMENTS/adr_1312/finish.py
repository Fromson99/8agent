from common import *
import shutil
r=read(ART/'analysis.json');sem=read(ART/'semantic-review.json');aud=read(ART/'source-wire-audit.json');contracts=read(ART/'contract-comparison.json');m=read(ADR/'실험/manifest.json')
m['retrieval_accounting']=read(ART/'retrieval-metrics.json');ref=json.loads((ART/'retrieval-stage-ledger.json').read_text())
if isinstance(ref,dict) and set(ref)=={'raw_json'}:
 p=Path(ref['raw_json']['path']);p=p if p.is_absolute() else ROOT/p;m['retrieval_accounting']['stage_ledger'].update(artifact_path=str(p.relative_to(ROOT)),sha256=sha(p))
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
byarm={a:[x for x in r['rows'] if x['arm']==a] for a in ('before','after')}
m['results'].update(status='complete',by_arm=byarm,comparisons=[r['paired369']],judge_disagreements=0,usage={k:r[k] for k in ('physical_calls','reported_cost_usd','reported_tokens','unknown')},latency={'p95':None,'reason':'One stochastic question pair plus one candidate question; failures excluded from speed ratios'},error_taxonomy=[{'type':'preexisting_api_fixture_failure','count':20,'before_after_identical':True}]+[{'type':'actual_cell_failure','cell':x['cell'],'http_status':x['http_status']} for x in r['rows'] if x['http_status']!=200]);put(ADR/'실험/manifest.json',m)
table='| 질문/설정 | 전체 초 | 모델 초 | 모델 밖 초 | 호출 | 내용 |\n|---|---:|---:|---:|---:|---|\n'
for x in r['rows']:table+=f"| {x['cell']} | {x['seconds']:.3f} | {x['model_seconds']:.3f} | {x['outside_model_seconds']:.3f} | {x['physical_calls']} | {x['answer_review']['verdict']} |\n"
handoffs=sum(x['finish_handoffs'] for x in r['rows'] if x['arm']=='after');working=(ART/'working-integration.json').exists();stop=read(ART/'STOP_EXTERNAL.json') if (ART/'STOP_EXTERNAL.json').exists() else None
sections=[('결정 요약',f'구조 성능수정(ADR1311)에 이어 검증된 FINISH를 기존 최종판단으로 넘기는 조건을 구현했다. 실제 후보 내용완료 {r["after_content_pass"]}/2, 후보의 실제 FINISH직행 관측{handoffs}건. '+('작업코드에 검증한감독1모듈+종속pin통합.' if working else '아직작업통합전.')+' 선택MAIN136 유지. 반복순회 수정의 동등재생73.76%감소와 실제모델시험을 구분한다.'),
('문제와 변경 전 구조','앞선1310은 부모마다 전체256848노드를 반복순회해children88.27초를 확인했다.1311은 기존부모색인·성공선택128개/1MiB재사용·문서별sourceID·블록512개/4MiB재사용으로 동일재생120.774→31.691초/입력16/16·최종2/2동일을 확인했다. 별도 종료문제는 FINISH뒤 감독이371조 추가조사를 제안해2모델24.537초를 더썼던 경로다.'),
('가설과 사전 판정 기준','명시FINISH·원래요구전부ANSWERABLE·필수원문확보·열린need/conflict/미검토원문없음이면 감독모델재검토를생략하고기존ASSESS로직행한다. pendingUNKNOWN/halt/미완료페이지는우회금지. 같은질문원문핵심3규칙과인용보존·새회귀0·source/ACL/wire불일치0. 기준design/criteria.json사전동결.'),
('실험 설계','성능수정동일517파일before/after중감독1모듈과pin만차이. before369→after369→after365 단회새프로세스. NearAI FP8 only/Qwen3.8-27b/reasoningnone/fallback0/ontologyOFF/최종검토표OFF시험조건. 전체60/셀40물리호출/개별180초/UNKNOWN전부중단·같은셀재실행0. 실제정답은사후검토에만사용.'),
('데이터·모델·재현성','기존SQLite원문판본·전체SHA와승인문서권한결속. Oracle드라이버미로드·Oracle0. 공개질문에서내부사건파생질문승인은동일정본과허용scope로확인. 전체raw/canonical/사용량/실패는각셀gzip원본보존. 최초원문준비와OS파일캐시는재생/실모델시험의한계로명시.'),
('결과',table+f'\n계약78통과·기존API시험20동일실패,현재nativeAPI3·원문목표/페이지보호18통과. 신규FINISH검사에는실제과거005응답을그대로입력해추가감독0과역사적need보존확인포함. 실제원문확보대조{sum(x["source_checks"] for x in r["rows"])}·전달{sum(x["delivered_checks"] for x in r["rows"])}·source/ACL/wire불일치0. '+json.dumps(r['paired369'],ensure_ascii=False)),
('사례별 오류 분석','\n'.join(x['cell']+': '+x['basis'] for x in sem['rows'])+'\n'+('전역중단: '+json.dumps(stop,ensure_ascii=False) if stop else '확정응답불명으로인한전역중단없음.')+'\n작업통합후동일FINISH계약/현재nativeAPI25검사통과(앞선검사와중복). 사후분석기의query_stats필드가실제live관측기의rows형식과달라실패한1건은원본보존후집계형식수정,새모델0. 기존API시험20개는동일testID/오류(생성requestID와후보경로제외)로before에도실패했다. 11개는reference_bundle_review정책의존설정,나머지는옛모의전송/출력fixture와현재계약불일치다. 최초문서검사정확제목/schema표식2종정정및실패보존. 비교기정규화는후보의상대경로·생성requestID만허용;제품오류를제거하지않았다.'),
('비용·지연·회수 규모',f'물리{r["physical_calls"]}·UNKNOWN{r["unknown"]}·보고토큰{r["reported_tokens"]}·보고비용${r["reported_cost_usd"]:.9f}. 새평가모델0. 모든물리호출/예산일치. 총요청=HTTPask,모델=실제POST구간합,잔여≠DB시간. sourceSQLtrace와앱execute/fetch시간은구별한다. 실패시간을개선율로세지않는다. 실제원문좌표회수원장retrieval-stage-ledger.json과source-wire-audit.json참조.'),
('해석','source_goal_control.resolve를먼저실행하여필수원문을우선한다. 새로운read_review가저장된현재상태해시·권한·원문material을확인한다. 옛wire의required목록을쓰지않고변경된원문span은다시검토대상으로남긴다. 성공FINISH결정/사유를receipt에저장해재개시중복호출하지않는다. 역사적need장부·최종claim/source검증·부분결과·중단예산은유지한다. 충분성승인아님을내부이벤트에기록한다.'),
('한계와 일반화 가능 범위','1311초기자료준비표본약18.1초와두source_unit전체메타데이터읽기는남는다. 컴파일러코드수정은Gold파생데이터게시계약까지영향이있어이번동등조회수정과분리했다. 실제모델전후1쌍은응답경로·제공자변동이있으므로통계적/일반적속도보장없음. 완성FINISH분기조건이없는질문에는추가호출생략을강요하지않는다. SQLite측정값을OracleGold현장속도로확대하지않는다.'),
('운영 결정·롤백 조건',('1311제품4파일과이번감독1파일이작업코드에반영됐다. 후보검토표OFF설정은작업기본값에복사하지않았다. 각working-before+working-integration.json에원복파일/해시보존. ' if working else '')+'선택MAIN136/Goldbinding/원문세대/DB/DDL/기본제공자/외부배포/메일/Gitpush변경0. 실제최종답변/코드효과확인과로컬선택MAIN상태를구분한다.'),
('재현 명령','setup/edit→freeze→계약/baseline비교/현재nativeAPI→사전ADR검사→run_all3셀→audit/audit_ablation/ledger→최종주장원문대조→analyze→선택hunk작업통합/API→전파일SHA검증runtime보관→finalize/hash/ordinaryvalidate/statuscompleted/finalvalidate/graph.')]
p=ADR/'README.md';front=p.read_text().split('\n---\n',1)[0]+'\n---\n';p.write_text(front+'\n# FINISH 종료 수정과 실제 NearAI 결과\n\n'+'\n\n'.join(f'## {i}. {t}\n\n{b}' for i,(t,b) in enumerate(sections,1))+'\n')
for q in m['questions']:
 p=ADR/'실험'/q['file'];s=p.read_text();s=s.split('## 8. 사례 최종 판정')[0]
 s=s.replace('현재미실행.','전체원응답과실패보존완료.').replace('현재 미실행.','전체원응답과실패보존완료.').replace('예정 arm:','설계 arm:').replace('원장 작성 예정.','원장기록완료; ../artifacts/retrieval-stage-ledger.json과source-wire-audit.json참조.')
 s+='## 8. 사례 최종 판정\n\n'+json.dumps([x for x in sem['rows'] if x['case_id']==q['case_id']],ensure_ascii=False,indent=2)+'\n\n'+table;p.write_text(s)
report=ROOT/'09_ARTIFACTS/AUDITS/20261104-latency-repair-live';report.mkdir(exist_ok=True)
(report/'원인_수정_실제실험결과.txt').write_text('\n\n'.join(t+'\n'+b for t,b in sections)+'\n');shutil.copyfile(ART/'analysis.json',report/'analysis.json')
files=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Full repair and live-test evidence','contains_raw_prompts_and_outputs':'canonical'in p.parts or 'raw'in p.parts or p.name in ('response.json.gz','runtime.tar.gz')} for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json' and not (p.parent.name=='.observer-versions' and p.name.startswith('manifest-'))]
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1312','files':files});print('Live results documented; validate before completion')
