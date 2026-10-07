"""Render historical-control results without rewriting product or judge outputs."""
import json,hashlib
from pathlib import Path
import report
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0493-source-continuation-repair'
def read(p):return json.loads(p.read_text())
def block(x):return '```json\n'+json.dumps(x,ensure_ascii=False,indent=2)+'\n```'
def main():
 report.main();z=read(A/'artifacts/metrics.json');m=read(A/'실험/manifest.json');audit=read(A/'artifacts/article-scope-audit.json');continuation=read(A/'artifacts/continuation-audit.json')
 b=z['by_arm']['baseline'];c=z['by_arm']['repaired'];reviewed={};table='| 방식 | 발견 | 읽기 | 전달 | 선택·게시 | 검토 주장 | 기준답 일치 | 호출 |\n|---|---:|---:|---:|---:|---:|---|---:|\n'
 for arm in ['baseline','repaired']:
  r=read(A/'artifacts/run-001/cm-018'/arm/'result.json');s=r['stages'];claims=len(r.get('result',{}).get('answer',{}).get('claims',[]));reviewed[arm]=int(claims>0)
  table+='| '+' | '.join(map(str,['상속 기준' if arm=='baseline' else '신규 후보',len(s['discovered']),len(s['read']),len(s['presented']),len(s['final_sources']),claims,z['by_arm'][arm]['correct'],r['physical_calls']]))+' |\n'
 m['results']['usage']={'new_product_calls':c['calls'],'new_product_usage':c['usage'],'new_judge_calls':z['judge_calls'],'new_judge_usage':z['judge_usage'],'inherited_control_calls_not_new':b['calls'],'inherited_control_usage_not_new':b['usage']}
 m['results']['reviewed_answer_counts']=reviewed;m['results']['article_scope_audit']=audit;m['results']['continuation_audit']=continuation
 m['results']['mechanism_note']='Live article-range audit is separate from source/answer score. Zero candidate article calls means mechanism not exercised live, not a passed live scope check.'
 for q in m['questions']:
  p=A/'실험'/q['file'];q['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
 (A/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 sections=[('결정 요약',f"28개 계약을 수정본과 frozen revision에서 통과했다. 신규 CM018은 게시{c['publication_success']}/1, 검토 답변{reviewed['repaired']}/1, 기준답 일치{c['correct']}/1, 핵심 조문 recall{c['gold_recall']:.0%}, 출처 관련성 precision{c['source_precision']}. 신규 제품{c['calls']}+평가{z['judge_calls']}호출. 인샘플 단회이며 MAIN 승격 없음.\n\n"+block(z['verdicts'])),
 ('문제와 변경 전 구조','부모 ADR0492는 다음 페이지 cursor를 target에 넣은 오류를 복구하지 못했다. 서버가 원 읽기 대상·범위·cursor를 묶은 검증된 next_actions를 제공하고, cursor-as-target 오류에는 해당 동작을 corrective_actions로 반환한다. 부모 대비 tiers_views/tiers_session 두 파일 변경. 조 전체 범위 읽기 수정은 부모에서 유지한다.'),
 ('가설과 사전 판정 기준',m['design']['hypothesis']+'\n\n'+m['design']['success_criteria']+'\n\n'+block(z['criteria'])),
 ('실험 설계','CM018 신규 후보1회, ADR0492/run-001/repaired immutable 출력 상속 기준. 동시 A/B가 아니다. 부모와 같은 공개145문서·원문 세대·Qwen FP8 thinking off·온도0·출력2800·모델14/도구56/controller300초. 답변/출처 평가2호출, 검토 주장0인 답변은 정답으로 세지 않는다. 결과 확인 후 후보 retuning이나 재실행하지 않았다.'),
 ('데이터·모델·재현성','99개 후보 파일은 완료 부모에서 상속 후2개 변경하여 동결했다. 공통 Python/config는 부모의 sealed-runtime 정확한 복사본을 사용한다. 공개 원문·전송승인·현재 모델 정책은 전송 전 hash 검증한다. immutable export_allowed 속성은 변경하지 않는다. 28개 계약 및 frozen28 통과, 무모델 preflight 통과 후 실행했다. [구현 상세](IMPLEMENTATION.md).'),
 ('결과',table+'\n\n'+block(z['by_arm'])+'\n\n'+block(z['paired_outcomes'])),
 ('사례별 오류 분석',block(continuation)+'\n\n'+block(audit)+'\n\n'+block([{k:x[k] for k in ['arm','execution_error','publication_error','semantic_errors','limitations','phases']} for x in z['by_case']])),
 ('비용·지연·회수 규모',block(m['results']['usage'])+'\n\n'+block(m['results']['latency'])+'\n\n기준 호출·시간·비용은 과거 기록이며 이번 지출이 아니다. 각 arm 표본1개이므로 p50/p95는 동일 관측값이다. 자원 로딩 포함 전체 시간과 controller 시간을 분리했다.'),
 ('해석','원문 ID가 gold에 포함된 것, 관련 문단을 실제 전달한 것, 검토 답변이 있는 것, 기준답이 맞은 것은 별개다. 조 전체 읽기의 범위와 완료 표시는 canonical block/span을 독립 대조했다. full article 요청 자체가 없으면 실제 모델에서 해당 수정을 검증했다고 하지 않는다. 모델이 후속 페이지를 읽거나 적절한 출처를 찾는 것까지 이 코드 변경이 보장하지 않는다.'),
 ('한계와 일반화 가능 범위','인샘플 단회·역사적 기준·동일 Qwen evaluator이며 인간 calibration 및 법령 버전 독립 인증은 없다. 설계48개 전체, canonical evidence 병합, full-v5 journal, 모든 oversized 입력 분할, 오류 resolved/exhausted 생명주기, resume/feedback/service bridge/GENOS는 미완료다. 실제 호출은 session/outbox runner이며 HTTP/Open은 모의 계약으로 확인했다.'),
 ('운영 결정·롤백 조건','이 후보를 운영 registry나 활성 릴리스로 승격하지 않았다. 기존 작업자의 공유 파일 변경도 덮어쓰지 않았다. 완료 원본·후보 revision을 보존한다. 개선 후 재실험은 새 ADR을 사용한다.'),
 ('재현 명령','완료 기록을 덮어쓰지 않는다.\n\n`.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path '+str(A.relative_to(R))+' --final`\n\n[전체 입출력](실험/README.md) · [지표](artifacts/metrics.json) · [범위 감사](artifacts/article-scope-audit.json) · [사전 계획](PLAN.md)')]
 front=(A/'README.md').read_text().split('---',2)[1];(A/'README.md').write_text('---'+front+'---\n\n# ADR-0493: 서버 제공 페이지 계속읽기와 cursor 오류 복구\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{s}' for i,(h,s) in enumerate(sections,1))+'\n')
 (A/'실험/README.md').write_text('# CM018 신규 후보 / 상속 기준\n\n'+table+'\n\n[전체 입출력](질문-001-cm-018.md)\n')
 # report includes its own stdout log; refresh only after this process exits.
if __name__=='__main__':main()
