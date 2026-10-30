from common import *
import gzip,collections
r=read(RUN/'result.json');m=read(ADR/'실험/manifest.json');rows=[];failed=[];counts={};maxunchanged={}
for cid in ('cm-001','cm-007','cm-009'):
 p=RUN/cid;cs=read(p/'calls.json');counts[cid]=len(cs);failed.extend({'case':cid,**x} for x in cs if x['status']!='completed');g=[]
 for f in sorted((p/'canonical').glob('[0-9][0-9][0-9].json.gz')):
  v=json.loads(gzip.decompress(f.read_bytes()))['view'];z=v.get('answer_progress_context',{}).get('unchanged_steps_by_issue',{});g.extend(z.values())
 maxunchanged[cid]=max(g,default=0)
assert counts=={'cm-001':2,'cm-007':38,'cm-009':31}
f=read(DES/'freeze.json');assert all(sha(ROOT/f['code_root']/n)==h for n,h in f['files'].items());assert sha(ROOT/'02_BACKEND/lawrag/research/experiment_client.py')==f['client_sha256'];assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
resource={'case':'cm-009','classification':'host_resource_guard_before_send','http':502,'reason':'Host-wide swap usage exceeded frozen512MiB threshold; check_resources failed before sending the next call','physical_calls':31,'next_generation_sent':False,'causal_limit':'Host-wide swap does not establish this single worker as sole cause; peak RSS recorded in result. No final judgment or final answer occurred.'};put(RUN/'cm-009/resource-stop.json',resource)
extra={'external_requests':sum(counts.values()),'per_case':counts,'failed_physical_requests':failed,'max_unchanged_steps_in_delivered_context':maxunchanged,'candidate_code_unchanged':True,'experiment_client_unchanged':True,'active_MAIN111_unchanged':True,'all_three_requests_terminal':True,'live_workers_finished':True,'no_whole_case_retry':True,'old_CM51_batch_resumed':False,'supervisor_recovery':'One supervisor exited143; surviving007worker observed through completion and never relaunched;009 dispatched once','legal_quality_certified':False,'original_read_boundary':'Journal acquisition, actual source delivery, and final citation distinguished. Stage original_read means journal acquisition; partial ranges do not prove full statutory coverage.'};put(RUN/'completion-audit.json',extra)
text='''CM 실패3문항 재실행 결과 — 2026-10-28

실행: MAIN110 기반 ADR1155 rev002와 동일한 격리 후보. 현재 활성 MAIN111 변경없음.
Qwen3.8 / Parasail FP8 / reasoning none / 출력토큰 상한없음. 각문항1회, 네이티브40/1024/1800한도 유지.
총 외부요청71회(001=2,007=38,009=31), 문항 전체 재실행0, 평가모델0. 기존CM51배치 재개0.
3건 모두 최종 사용자 답변0. 정답률0%라고 확장하지 않는다: 서로 다른 기술실패·검토실패·자원중단이다.

CM001 — 100분의10 합산 여부: 2회/38.976초/HTTP500.
제26조는 후보에 있었고 서버 확보기록도 있지만, 모델 sources에는 아직 본문이 없는 화면이다.
answer_progress ANSWERABLE 분기에 basis_refs minItems=1과maxItems=0이 함께 생성됐다.
제공자가 불가능한 스키마로 거부했다. runner는 HTTP200 오류봉투를 모델/제공자 불일치라고 잘못 분류했으므로 실제 원인은 schema-failure.json을 따른다.
오프라인 JSONSchema 문법검사와 근거가 있는 fixture만으로 이 분기의 충족 불가능성을 놓쳤다.

CM007 — 의무인수 수량·보유기간: 38회/1305.516초/HTTP422.
3번째 호출에서 코스닥 제13조 선택→4번째 입력에 원문 전달. 과거의28번째 선택보다 일찍 도달했다.
그러나 ANSWERABLE/NO_CHANGE를 기록하면서 무관하다고 설명한 원문까지 반복 조사했다.
등록 기준근거2개 중 코스닥 제13조는 전달됐지만 유가증권시장 제13조는 이번 관측 입력에서 제시/전달되지 않았다.
최종 C1은 작성했으나 J3·J9의 원문과 C1의 근거가 겹치지 않아 거절. 실제 제공자 보완 출력도 첫 출력과 구조적으로 동일했다.
보완입력 내부에 거절주장 C2 / 오류명세 주장키 C1 불일치가 남았다. 이것이 반복 출력에 미친 단독 인과효과는 분리검증하지 않았다.
과거37회/422 실패와 비교해 전체종료·호출 개선은 확인되지 않았다. 제공자429재시도2회도38회에 포함.

CM009 — 의무인수 면제: 31회/810.759초/HTTP502.
2번째 호출에서 코스닥 제13조 선택→3번째 입력에서 면제원문 전달. 이후제31조도 전달됐다.
답변가능·진전없음이 반복되며 추가 조사를 지속했다. 다음 호출 전 호스트 스왑사용량이 동결512MiB 기준을 넘어 보호중단했다.
그 다음 요청은 제공자에게 보내지 않았다. 최종 답변은 미확인이고, 법률 정답/오답으로 채점하지 않는다.

판정: 후보/매칭표시 개선만으로 근본 문제가 해결되지 않았다.
근거없는 화면의 스키마 충돌, 진전판단과 실제 행동의 불일치, 최종 보완 번호와 근거 연결의 문제가 남는다.
원문 획득·모델 전달·판단·최종답변은 별도상태다. 원문/권한검사0위반을 답변성공으로 세지 않는다.

운영: 모델호출 종료. MAIN111 유지. 제품반영·승격·GENOS배포·메일·Git작업 없음.
로그: 각cm폴더의 raw/,canonical/,wire/,runtime.tar.gz,analysis.json,focus-audit.json 및 개별결함JSON.
상위감독1회 종료143은 별도보존했고 기존007자식의 종료를 기다린 뒤009만 새로 시작했다.
'''
text+='\n진전없음 최대 누적: '+json.dumps(maxunchanged,ensure_ascii=False)+'\n제공자 기록 비용 합계: $'+str(r['usage']['cost_usd'])+' (실패 응답의 미보고 비용을0으로 보증하지 않음).\n'
(RUN/'재실행_결론과_남은결함.txt').write_text(text)
p=ADR/'README.md';s=p.read_text().replace('status: Proposed','status: Rejected');s+='\n\n[재실행 결론과 남은 결함](artifacts/run-001/재실행_결론과_남은결함.txt).\n\n기술·운영상 성공기준 미달로 Rejected. CM009의 자원중단은 법률오답으로 채점하지 않는다. 감독프로세스 종료와 복구, 제공자429, 실제스키마충돌·반복출력·번호불일치를 보존했다.\n';p.write_text(s)
put(ART/'post-analysis-scripts.json',{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')})
print('Sealed audit:71requests,0final answers,MAIN111 unchanged')
