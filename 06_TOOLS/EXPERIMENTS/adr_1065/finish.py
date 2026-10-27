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
 m['runs'][0].update(status=run_status,sha256=sha(ART/'matrix-summary.json'),terminal_execution_status=summary['status'],observed_cells=summary['completed_product_cells'],planned_cells=9,note='Original9-cell run retained. A stopped partial run is failed, not complete. All3 question documents and unexecuted cells remain; no empty observations are invented.')
 m['results']={'status':'complete' if summary['complete_observations'] else 'failed',
  'by_arm':{a:{'status':run_status,'total':summary['arms'][a]['product_observations']['completed'],'planned_total':3,'correct':summary['arms'][a]['semantic']['pass'],'accuracy':summary['arms'][a]['semantic']['determinate_accuracy'],'unknown':summary['arms'][a]['semantic']['unknown']} for a in report.ARMS},
  'comparisons':[],'judge_disagreements':None,'usage':{a:summary['arms'][a]['usage'] for a in report.ARMS},
  'latency':{a:summary['arms'][a]['latency_seconds'] for a in report.ARMS},'terminal_execution_status':summary['status'],
  'primary_required_body_reach':summary['primary_required_body_reach'],
  'first_nine_gate':summary['first_nine_gate'],
  'adr_final_validation_completed':False,'adr_completion_claimed':False,
  'final_validation_constraint':summary['final_validation_constraint'],
  'final_validation_note':summary['final_validation_note'],'quality_certified':False,'operational_success':summary['operational_success']}
 save(ADR/'실험/manifest.json',m)
 tested=read(ART/'release-check-summary.json');api=read(ART/'frozen-api-summary.json')
 gate=summary['first_nine_gate']
 completion_note=('전체 관찰을 기록했으며 ADR 최종 검증·graph 확인은 별도다. 검사 통과 전에는 ADR 완료를 주장하지 않는다.'
  if summary['complete_observations'] else
  '원래9셀 run은 failed로 남겼고3개 질문 문서를 모두 유지했다. 현행 v4 최종 검사기는 전체 문항을 담은 complete run을 요구하여 부분 중단 상태를 통과시킬 수 없다. 표본 축소나 미실행0원장을 만들지 않았으며 ADR 완료를 주장하지 않는다.')
 front=(ADR/'README.md').read_text().split('---',2)[1]
 rows='\n'.join(f"| {a} | {summary['arms'][a]['product_observations']['completed']} / 3 | {summary['arms'][a]['semantic']['pass']} | {summary['arms'][a]['semantic']['unknown']} |" for a in report.ARMS)
 (ADR/'README.md').write_text('---'+front+'---\n'+f'''
# ADR-1065: 현재 조사 작업의 원문·판단·행동 연결

## 1. 결정 요약
승인된3문항×A0/A1/A2 총9셀만 관찰한다. 상태 **{summary['status']}**, 관찰 **{summary['completed_product_cells']}/9**, 운영 기준 통과 **{summary['operational_success']}**. 관찰 완료와 운영/의미 성공은 구분한다. MAIN103과 GENOS는 변경하지 않았다.

## 2. 문제와 변경 전 구조
ADR1063의 전체 상태 반복 전달 및 판단·행동 연결 문제를 진단 자료로 삼아 현재 작업의 원문·판단·행동을 지역화한다. 완료 부모는 ADR1059/compact-input이며 실패한1063 결과를 새 부모 성공으로 취급하지 않는다.

## 3. 가설과 사전 판정 기준
[사전 계획](artifacts/implementation-plan.json), [실행 동결](artifacts/design-freeze.json). 동일 입력 한도와40호출·1024도구·1800초, RSS5GiB·가용3GiB·swap증가512MiB·디스크20GiB를 유지했다. 계약 검사 {tested['passed']}개, 동결 API 검사 {api['passed']}개 통과; 기존 실패 {len(tested['known_existing_failures'])}건을 별도 보존했다.

## 4. 실험 설계
승인37문항 중 기존 첫3문항만 고정했다. Qwen3.8, 승인된429제공자 계약, 출력 상한 없음. A0은 온톨로지 없음, A1/A2는 같은 승인 원문·메타데이터로 표시 구조만 비교한다. 골드와 필수근거 좌표는 평가기에만 전달한다.

## 5. 데이터·모델·재현성
원문 세대·승인 목록·후보 코드·계측기·입력/평가 파일의 정확 해시는 실행 동결에 있다. 외부 모델 실험이며 GENOS 연결은 수행하지 않았다.

## 6. 결과
[전체 결과](artifacts/RESULT.md), [기계 집계](artifacts/matrix-summary.json), [9셀 운영 기준](artifacts/gate.json), [원문 원장](artifacts/retrieval-ledger.json).

| arm | 완료 관찰 | 의미 pass | 의미 unknown |
|---|---:|---:|---:|
{rows}

{completion_note}

## 7. 사례별 오류 분석
각 질문 문서와 원시 저널에 입력 한도·도구·판단·근거·전송 실패를 구분해 남긴다.

## 8. 비용·지연·회수 규모
제품/평가 호출과 usage·p50/p95·원문 확보/전달/인용 지표는 기계 집계에 연결한다. 누락된 사용량은 0으로 채우지 않는다.

## 9. 해석
원문 도착·취득·실제 전달·판단 뒤 행동·최종 소비·의미 정확도를 구분한다. 1064의 부모 text_ref 및 ASSESS 참조 감사를 새 실행 전에 동결해 적용했으며 원시 기록과 좌표·권한·해시를 확인하지 못한 값은 미확인이다. 알려진3문항의 in-sample probe이며 일반화나 법률 정답 인증이 아니다. 10번째 셀과 추가102셀은 이번 실험에 포함되지 않는다.

## 10. 한계와 일반화 가능 범위
3문항의 알려진 표본이며 decision_eligible=false다. 의미 품질과 일반화, 현장 성능 인증은 별도다.

## 11. 운영 결정·롤백 조건
Proposed. MAIN103 유지; 결과 후 변경은 새 ADR에서 수행한다.

## 12. 재현 명령
MAIN 승격·GENOS 배포 없음. 결과 후 코드 변경·재실험은 새 ADR이 필요하다. `.venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_1065/run_matrix.py --inspect-only`로 불변 입력을 확인한다. 예약·완료 셀은 다시 실행하지 않는다.
''')
 (ADR/'실험/README.md').write_text('# ADR1065 질문별 관찰\n\n[동결 실행](../artifacts/design-freeze.json) · [결과](../artifacts/RESULT.md)\n\n'+'\n'.join(f"- [{x['case_id']}]({x['file']})" for x in m['questions'])+'\n')
 save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1065','created_at':m['reservation']['created_at'],'files':[{'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Execution repair implementation and immutable observed experiment evidence','contains_raw_prompts_and_outputs':'model' in p.parts or p.name=='journal.sqlite'} for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json' and p.suffix!='.lock']})
 print(summary['status'],summary['completed_product_cells'],summary['finished_evaluation_cases'])
if __name__=='__main__':main()
