"""Write reviewable Korean report and full request/response records; no model calls."""
import json,hashlib,re,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0503-gemma-obligations-bound-paired-probe'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def block(v):return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```\n'
def verdict(x):return '일치' if x is True else '불일치' if x is False else '미확정'
def files_dump(path):
 return '\n'.join('#### '+str(p.relative_to(A))+'\n'+block({str(p.relative_to(R)):read(p)}) for p in sorted(path.rglob('*.json')))
def main():
 m=read(A/'실험/manifest.json');metrics=read(A/'artifacts/metrics.json');res=read(A/'artifacts/run-001/results.json');judged=read(A/'artifacts/run-001/judgment/results.json');prod={c['case_id']:c for c in read(A/'product-cases.json')['cases']};gold={c['case_id']:c for c in read(A/'gold-cases.json')['cases']};ledger=read(A/'artifacts/retrieval-stage-ledger.json');b=metrics['by_arm']['baseline'];o=metrics['by_arm']['obligations']
 lines=['|문항|수정 전|요구 추적 보강|설명|','|---|---|---|---|']
 qheads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
 case_summary=['# Gemma 보강 전후 실제 답변\n\n저장 기준답·실제 답변과 익명 2회 판정을 함께 제시한다. 독립적인 현행 법률 인증은 아니다.\n']
 for q in m['questions']:
  cid=q['case_id'];rows={r['arm']:r for r in metrics['by_case'] if r['case_id']==cid};detail={a:res['cases'][cid][a] for a in rows};pair='미확정' if any(r['correct'] is None for r in rows.values()) else '신규 일치' if not rows['baseline']['correct'] and rows['obligations']['correct'] else '회귀' if rows['baseline']['correct'] and not rows['obligations']['correct'] else '양쪽 일치' if rows['baseline']['correct'] else '양쪽 불일치'
  lines.append(f"|{cid}|{verdict(rows['baseline']['correct'])}|{verdict(rows['obligations']['correct'])}|{pair}|")
  inp='원문·탐색·선택·주장·검토 기록 전체. 모델에 제공한 실제 메시지는 다음 절의 request.json에 있다.\n'
  stages=[]
  for a in rows:
   trace=read(A/'artifacts/run-001'/cid/a/'trace.json');inp+='### '+a+'\n'+block({str((A/'artifacts/run-001'/cid/a/'trace.json').relative_to(R)):trace})
   stages.append(next(c for arm in ledger['runs'][0]['arms'] if arm['arm_id']==a for c in arm['cases'] if c['case_id']==cid))
  inp+='### 회수·탈락 단계 원장 — run·arm별\n\n제품 실행 후에만 gold를 결합했다. 전체 좌표·탈락 사유:\n'+block(stages)
  model='각 JSON은 저장한 원본 request/response 또는 계측 receipt다. 키와 인증 헤더는 저장하지 않는다.\n'+''.join('### '+a+'\n'+files_dump(A/'artifacts/run-001'/cid/a/'calls') for a in rows)
  judge=files_dump(A/'artifacts/run-001/judgment'/cid)+'\n두 순서 판정이 일치할 때만 확정하며, 불일치는 미확정이다.\n'
  vals=[block({'run_id':'run-001','arms':detail,'record_status':'exact saved payloads; agent final result separate from wire response'}),prod[cid]['question'],gold[cid]['reference_answer'],inp,model,'investigate/select_sources/compose/review는 모두 제품 호출이며 위 절에 호출 순서대로 전체 기록했다. 별도 숨은 중간 호출 없음.',judge,block(rows)+'\n비교: '+pair+'\n\n이 판정은 자동 평가 보조 관측이다. 직접 대조 내용은 CASE_REVIEW.md를 함께 본다.']
  (A/'실험'/q['file']).write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(qheads,vals),1))+'\n')
  case_summary+=['## '+cid+'\n\n'+prod[cid]['question']]
  case_summary+=['### 저장 기준답\n\n'+gold[cid]['reference_answer']]
  for a,label in [('baseline','수정 전'),('obligations','보강 후')]:
   r=rows[a];case_summary+=['### '+label+' — '+verdict(r['correct'])+'\n\n'+(r['answer'] or '(최종 답변 없음)')+'\n\n- 판정 이유 1: '+str(r['judge_reasons'][0])+'\n- 판정 이유 2: '+str(r['judge_reasons'][1])+'\n- 실제 호출: '+str(r['calls'])+'; 주된 원문 제시: '+str(r['gold_presented'])+'/'+str(r['gold_total'])+'\n']
 (A/'CASE_REVIEW.md').write_text('\n\n'.join(case_summary)+'\n')
 table='\n'.join(lines)
 stat='|항목|수정 전|보강 후|\n|---|---:|---:|\n'+f"|기준답 일치(2회 동의)|{b['confirmed_correct']}/7|{o['confirmed_correct']}/7|\n|판정 미확정|{b['unresolved']}|{o['unresolved']}|\n|검토된 주장 포함 답변|{b['with_reviewed_claims']}|{o['with_reviewed_claims']}|\n|제품 모델 호출|{b['product_calls']}|{o['product_calls']}|\n|확인된 제품 비용(USD)|{b['usage']['cost_usd']:.6f}|{o['usage']['cost_usd']:.6f}|\n|문항 소요시간 중앙값(초)|{b['wall_p50_seconds']:.1f}|{o['wall_p50_seconds']:.1f}|"
 dimnames={'demand_coverage':'질문 요구 충족','rule_scope':'규칙·적용 범위','conditions_exceptions':'조건·예외 보존','appropriate_abstention':'확정·유보 적절성','self_review':'자기검토'}
 dims='|능력|수정 전(pass/fail/그 외)|보강 후(pass/fail/그 외)|\n|---|---|---|\n'
 for d,label in dimnames.items():
  def fmt(s):x=s['dimensions'][d];return f"{x.get('pass',0)}/{x.get('fail',0)}/{7-x.get('pass',0)-x.get('fail',0)}"
  dims+=f'|{label}|{fmt(b)}|{fmt(o)}|\n'
 front=(A/'README.md').read_text().split('---',2)[1]
 decision='사전 기준 충족' if metrics['criteria_met'] else '사전 기준 미충족'
 sections=[('결정 요약',f'**7문항 × 수정 전후, 실제 Gemma 비교 결과: {decision}.**\n\n'+stat+'\n\n같은 모델·원문에서 요구 추적을 켜고 껐다. 인샘플 단회 비교이므로 Proposed, MAIN unchanged다. SQL·게시 성공을 판단력 점수로 사용하지 않는다.\n\n[실제 답변 대조](CASE_REVIEW.md), [기계 판독 결과](artifacts/metrics.json).'),('문제와 변경 전 구조','ADR0501은 질문 요구·근거·주장·검토 연결을 구현했다. 이번에는 실제 Gemma에서 기존 장점의 회귀와 약점 개선을 본다. ADR0502는 모델 전송 전 과거 정책 경로 검사로 거부되어 호출 0이었으며, 이번 ADR에서 client와 source grant의 exact 경로를 같은 새 정책에 결속했다. 원문·모델·해시·허용 범위 검증은 유지했다.'),('가설과 사전 판정 기준','사전 [PLAN](PLAN.md)과 [동결 설계](artifacts/frozen-design.json): 신규 정답 최소 1, 정답 회귀 0, 요구 누락 증가 없음, 평균 제품 호출·비용 각 1.5배 이하, controller 300초 이하. 결과 후 기준·제품 prompt·모델을 변경하지 않았다.\n'+block(metrics['criteria'])),('실험 설계','baseline은 ADR0501 rev003의 요구 추적을 끈 대조군, obligations는 켠 군이다. 두 격리 후보는 실험 경로 결속 이외에 같은 코드다. CM008·009·025·050은 기존 긍정 신호, CM029·033·FSC009는 약점으로 사전 선택했다. 각 1회, 문항별 실행 순서를 번갈아 바꿨다. 최대 4문항 병렬. Qwen 평가는 두 익명 순서를 바꾸어 2회 실시하고 서로 다른 판정은 미확정으로 남겼다.'),('데이터·모델·재현성','제품: google/gemma-4-31b-it, OpenRouter DeepInfra FP8, thinking off, temperature 0, fallback 없음. 평가: qwen/qwen3.5-122b-a10b, 제품과 분리. 실제 backend/usage는 각 호출 receipt에 있다. 기존 공개 CM/FSC 질문과 hash 확인된 공개 원문을 사용했다. 기준답은 제품 process에 읽히지 않는다. 법령 현행성은 별도 재검증하지 않았다. 후보·runner·원문·정책은 호출 전에 동결했다.'),('결과',table+'\n\n'+dims+'\n\n'+block(metrics['paired_outcomes'])+'\n분모 7. 미확정은 채점 불일치 또는 기술적 미평가이며 확정 오답과 구분한다. 기술 오류 자체를 모델의 판단력으로 해석하지 않는다.'),('사례별 오류 분석','[CASE_REVIEW](CASE_REVIEW.md)에 질문·기준답·수정 전후 전체 답변과 판정 이유를 담았다. 자기검토 등 능력별 표는 보조 자동 평가다. 원문 미확보와 제시된 원문의 해석 오류는 gold_presented 및 호출 원문으로 구분한다. 의미 원인은 실제 답변과 원문을 확인한 범위만 해석한다.'),('비용·지연·회수 규모',stat+'\n\n중단 요청에 usage가 없으면 비용 합계에서 확인할 수 없다. 비용은 수신한 usage 합계이며 전체 청구액 확정값이 아니다. 누락 receipt 수는 metrics.json에 있다.\n\n평가 모델 비용 및 usage:\n'+block(metrics['judge_usage'])+'\n소요시간은 초기 원문 자원 로딩과 모델 실행을 포함한 wall time이며 controller 시간은 별도 기록한다. 과거 실행과의 latency 비교가 아니다. 각 observed stage의 exact source identity 원장은 [ledger](artifacts/retrieval-stage-ledger.json)에 있다. 마지막 stage는 답변 주장에 포함된 원문이며 게시 여부가 아니다.'),('해석',decision+'이므로 이 결과만으로 전체 능력 향상이나 운영 채택을 주장하지 않는다. 추적 구조가 존재하는 것과 모델이 요구·규칙·조건을 올바르게 판단하는 것은 별도다. 단일 질문·단일 실행에서 나타난 행동을 모델 고유 능력으로 일반화하지 않는다.'),('한계와 일반화 가능 범위','7개 기존 관측 사례를 의도적으로 선택한 in_sample probe. 반복 product 실행·새 holdout·사람 확정 calibration 없음. Qwen 2회 평가도 독립적인 사람 판단을 대신하지 않는다. 사전 성공 사례가 이번에 실패할 수 있으며 비결정성·provider latency·동적 원문 탐색 차이가 있다. 저장 기준답 일치는 현행 법률 정답 인증이 아니다. GENOS 현장 성능은 미측정.'),('운영 결정·롤백 조건','Proposed, decision_eligible=false, MAIN·GENOS unchanged. 완료한 부모와 frozen 후보는 보존한다. 추가 수정이나 재실행은 새 ADR에서 분기하며 이 run을 덮어쓰지 않는다.'),('재현 명령','```bash\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0503-gemma-obligations-bound-paired-probe --final\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py graph --adr-root 04_EXPERIMENTS/ADR\n```\n\n제품 실행은 run_probe.py --execute, 분리 채점은 judge.py, 집계는 analyze.py다. 완료 run 디렉터리를 덮어쓰지 않으며 새 모델 호출은 새 ADR로 분기한다. [산출물](artifacts/manifest.json), [실행·계보](실험/manifest.json).')]
 (A/'README.md').write_text('---'+front+'---\n\n# Gemma 질문 요구 보강 전후 판단 비교\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
 (A/'실험/README.md').write_text('# Gemma 전후 비교 질문 인덱스\n\n'+table+'\n\n'+ '\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n\n원시 system/user/schema/response/usage를 각 질문에 전부 기록했다. 기준답은 평가 전용이다.\n')
 print('Reports generated; raw requests/responses retained')
if __name__=='__main__':main()
