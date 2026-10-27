"""Close the observed run without treating its unexecuted cells as complete."""
from pathlib import Path
import statistics
from common import ROOT,ADR,ART,read,save,sha
import report_results as report

def rel(p):return str(p.relative_to(ROOT))
def main():
 f=read(ART/'design-freeze.json');code=ROOT/f['code_root']
 assert all(sha(code/n)==h for n,h in f['files'].items())
 assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
 assert all(sha(ROOT/n)==h for n,h in read(ART/'preservation.json')['files'].items())
 resources=f['equal_operational_overrides']
 assert all(resources.get(k)==v for k,v in {
  'minimum_available_memory_bytes':3*1024**3,'memory_limit_bytes':5*1024**3,
  'memory_limit_kind':'worker_RSS','address_space_limit_bytes':6*1024**3,
  'minimum_disk_free_bytes':20*1024**3,'maximum_swap_increase_bytes':512*1024**2}.items())
 freeze,cases,cells,judges,summary,ledger=report.load_inputs()
 report.require(summary['complete_observations'] or bool(summary['stop']),
  'close only a completed observation matrix or a recorded stopped matrix')
 save(ART/'retrieval-ledger.json',ledger);summary['retrieval_ledger']=report.receipt(ART/'retrieval-ledger.json')
 save(ART/'matrix-summary.json',summary)
 (ART/'RESULT.md').write_text(report.report_markdown(summary))
 m=read(ADR/'실험/manifest.json');m['questions']=[]
 for number,case in enumerate(cases,1):
  p=ADR/'실험'/f"질문-{number:03d}-{case['case_id']}.md"
  p.write_text(report.question_markdown(number,case,freeze,cells,judges,summary))
  m['questions'].append({'number':number,'case_id':case['case_id'],'file':p.name,'sha256':sha(p)})
 corpus_total=f.get('corpus_total_article_roots')
 for cell in cells.values():
  if cell.get('metrics'):
   report.require(cell['metrics']['corpus_total_article_roots']==corpus_total,'cell corpus total differs from frozen total')
 arm_metrics={}
 for arm in report.ARMS:
  ledgers=[c['ledger'] for c in cells.values() if c['cell']['arm']==arm and c.get('ledger')]
  counts=[x['stages'][-1]['after_count'] for x in ledgers]
  gold_total=sum(x['gold_total'] for x in ledgers)
  gold_after=sum(x['stages'][-1]['gold_after'] for x in ledgers)
  arm_metrics[arm]={'presented_total':sum(counts) if counts else None,
   'presented_mean':statistics.mean(counts) if counts else None,
   'presented_p50':statistics.median(counts) if counts else None,
   'presented_p95':sorted(counts)[round((len(counts)-1)*.95)] if counts else None,
   'golden_recall':gold_after/gold_total if gold_total else None,
   'selectivity':statistics.mean(counts)/corpus_total if counts and corpus_total else None}
 m['retrieval_accounting'].update(corpus_total=corpus_total,
  before_filter={'status':'unavailable','reason':'No full pre-filter snapshot; not inferred from displayed candidate pages'},
  after_filter={'status':'unavailable','reason':'Exact acquisition/delivery/citation coordinates retained'},
  **{name:{a:arm_metrics[a][name] for a in report.ARMS} for name in
     ('presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity')})
 m['retrieval_accounting']['stage_ledger'].update(sha256=sha(ART/'retrieval-ledger.json'))
 run_status='complete' if summary['complete_observations'] else 'failed'
 m['runs'][0].update(status=run_status,sha256=sha(ART/'matrix-summary.json'),terminal_execution_status=summary['status'],observed_cells=summary['completed_product_cells'],planned_cells=111,note='Original111-cell run retained. A stopped partial run is failed, not complete. All37 question documents and unexecuted cells remain; no empty observations are invented.')
 m['results']={'status':'complete' if summary['complete_observations'] else 'failed',
  'by_arm':{'baseline':{'status':'complete','total':0,'correct':None,'accuracy':None,'reason':'Immutable1059 parent reference; no historical reuse as paired results'},**{a:{'status':run_status,'total':summary['arms'][a]['product_observations']['completed'],'planned_total':37,'correct':summary['arms'][a]['semantic']['pass'],'accuracy':summary['arms'][a]['semantic']['determinate_accuracy'],'unknown':summary['arms'][a]['semantic']['unknown']} for a in report.ARMS}},
  'comparisons':[],'judge_disagreements':None,'usage':{a:summary['arms'][a]['usage'] for a in report.ARMS},
  'latency':{a:summary['arms'][a]['latency_seconds'] for a in report.ARMS},'terminal_execution_status':summary['status'],
  'primary_required_body_reach':summary['primary_required_body_reach'],
  'first_nine_gate':summary['first_nine_gate'],
  'adr_final_validation_completed':False,'adr_completion_claimed':False,
  'final_validation_constraint':summary['final_validation_constraint'],
  'final_validation_note':summary['final_validation_note'],'quality_certified':False}
 save(ADR/'실험/manifest.json',m)
 tested=read(ART/'release-check-summary.json');api=read(ART/'frozen-api-summary.json')
 gate=summary['first_nine_gate']
 completion_note=('전체 관찰을 기록했으며 ADR 최종 검증·graph 확인은 별도다. 검사 통과 전에는 ADR 완료를 주장하지 않는다.'
  if summary['complete_observations'] else
  '원래111셀 run은 failed로 남겼고37개 질문 문서를 모두 유지했다. 현행 v4 최종 검사기는 전체 문항을 담은 complete run을 요구하여 부분 중단 상태를 통과시킬 수 없다. 표본 축소나 미실행0원장을 만들지 않았으며 ADR 완료를 주장하지 않는다.')
 front=(ADR/'README.md').read_text().split('---',2)[1]
 rows='\n'.join(f"| {a} | {summary['arms'][a]['product_observations']['completed']} / 37 | {summary['arms'][a]['semantic']['pass']} | {summary['arms'][a]['semantic']['unknown']} |" for a in report.ARMS)
 (ADR/'README.md').write_text('---'+front+'---\n'+f'''\n# ADR-1061: 온톨로지 MVP 실행·입력·부분 검토 구현

## 1. 결정 요약
계획서의 후보 탐색/원문 읽기 분리, 최대3source 검토, 독립 판단 commit, 행 보완1회, 전역 미검토 유지, 온톨로지 전달 결속과 모드별 최종 입력 한도를 격리 후보에 구현했다. MAIN103과 GENOS는 변경하지 않았다.

## 2. 문제와 변경 전 구조
부모1059는 후보에서 정의 원문을 자동으로 읽고 모든 검토 누락을 다음 행동 차단으로 연결했다. 계획과 감사를 근거로1059의 완료 compact-input arm 위에서 이어 구현했다. 기존 작업 코드를 후보 전체로 덮어쓰지 않았다.

## 3. 가설과 사전 판정 기준
[구현 전 계획](artifacts/implementation-plan.json)과 연결된 상세 계획 전체를 따른다. 한 행동의 검증된 출발 판단과 전역 검토 완료를 분리하며 원문·권한·상태·입력 상한을 보존한다. 판단이나 법률 결론을 시스템이 만들어 채우지 않는다.

## 4. 실험 설계
37문항×A0/A1/A2=111셀 전체를 동결하고 FSC005·CM023·FSC008의9셀 진행 기준을 먼저 검사한다. A0묶음없음, A1/A2같은 승인정보·다른배열. 현재 관찰상태는 **{summary['status']}**, 완료 관찰 **{summary['completed_product_cells']}/111**이다. 미실행 셀은 성공/실패의 분모로 꾸미지 않는다.

## 5. 데이터·모델·재현성
[실행 동결](artifacts/design-freeze.json). 승인37질문·31묶음, 동일 원문세대·색인, Qwen3.8, 기존 승인429제공자경로, 출력상한없음. 요청별40호출·1024도구·1800초, RSS5GiB·가용3GiB·swap증가512MiB·디스크20GiB 기준. {len(f['files'])}개 동일 코드 파일, 계약/API {tested['passed']}개 및 동결 경로 {api['passed']}개 통과. 외부 모델과 합성 API 검사는 구분한다. [수정 전 동일 실패](artifacts/known-existing-failures.json) {len(tested['known_existing_failures'])}건은 실패 결과를 유지하며 새 실패로 면제하지 않았다.

## 6. 결과
[전체 결과와 분모](artifacts/RESULT.md) · [정확한 수치](artifacts/matrix-summary.json) · [첫9셀 진행 기준](artifacts/gate.json).

| arm | 완료 관찰 | 의미 pass | 의미 unknown |
|---|---:|---:|---:|
{rows}

진행 기준: {gate.get('passed') if gate.get('present') else '미실행/기록없음'}. 기록·freeze·첫9셀 해시 결속 확인: {gate.get('verified')}. 전체37문항 효과 판정은 모든 짝과 평가가 갖춰졌을 때만 허용한다. 정확도34문항과 근거전용3문항은 별도다.

{completion_note}

## 7. 사례별 오류 분석
질문별 원본·변경/실패 상태는 [실험 목차](실험/README.md), 각 셀 execution-audit·metrics·저널에 있다. 입력 한도, 판단 보완, 미도착, 원문 미확보, 전송 장애, 의미 오답을 분리한다. 반복 자동 실행은 하지 않았다.

## 8. 비용·지연·회수 규모
모든 실제 호출·usage·peakRSS·지연은 matrix-summary에 남겼다. [읽기·전달·인용 원장](artifacts/retrieval-ledger.json). 필수 근거 본문 도달률은 데이터에 없는 필수 조문도 분모에 남기고 문항별 평균을 계산한다. 일부/전체 범위 전달은 별도다.

## 9. 해석
HTTP200, 원문확보, 실제전달, 판단유효, 답변인용, 의미정확도를 각각 기록했다. A1/A2 기대묶음에 도착하지 못한 경우 온톨로지 효과없음으로 해석하지 않는다. 유효근거 없이 평가로 넘어간 제어결함은 실패다.

## 10. 한계와 일반화 가능 범위
현재 표본은 in_sample=true, decision_eligible=false다. 전체111관찰이 없으면 전체표본 비교·일반화·최적화 완료 주장을 하지 않는다. 실제 GENOS Oracle·내부모델·워크플로우 검증은 수행하지 않았다.

## 11. 운영 결정·롤백 조건
Proposed. 격리 후보만 존재하며 MAIN103 포인터와 부모 완료 기록 해시를 확인했다. 진행 기준 실패 후 코드수정·재호출은 새 ADR에서만 한다. 이번 기록을 과거 실험 결과에 덮어쓰지 않는다.

## 12. 재현 명령
`.venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_1061/run_matrix.py --inspect-only`

완료·예약 셀은 재호출하지 않는다. 실제 요청/응답은 각 셀 model/과 저널 한 곳에 보존하며 보고서에는 경로·해시만 연결한다.
''')
 (ADR/'실험/README.md').write_text('# ADR1061 질문별 관찰\n\n[동결 실행](../artifacts/design-freeze.json) · [결과](../artifacts/RESULT.md)\n\n'+'\n'.join(f"- [{x['case_id']}]({x['file']})" for x in m['questions'])+'\n')
 save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1061','created_at':m['reservation']['created_at'],'files':[{'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Execution repair implementation and immutable observed experiment evidence','contains_raw_prompts_and_outputs':'model' in p.parts or p.name=='journal.sqlite'} for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json' and p.suffix!='.lock']})
 print(summary['status'],summary['completed_product_cells'],summary['finished_evaluation_cases'])
if __name__=='__main__':main()
