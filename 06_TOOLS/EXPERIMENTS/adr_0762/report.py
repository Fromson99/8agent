"""Report original outcomes without changing the frozen experiment or answers."""
from pathlib import Path
import json, hashlib, statistics
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0762-main53-three-public-cases'
O=A/'artifacts/run-001';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');r=read(O/'result.json');review=read(O/'semantic-review.json')
table='| 문항 | MAIN52 근거 응답 | MAIN53 근거 응답 | 호출 52→53 | 입력 토큰 52→53 | 요청시간 52→53 |\n|---|---|---|---:|---:|---:|\n'
for case in read(D/'dataset.json')['cases']:
 cid=case['case_id'];b=next(x for x in r['by_arm']['baseline']['cases'] if x['case_id']==cid);c=next(x for x in r['by_arm']['main53']['cases'] if x['case_id']==cid)
 table+=f"| {cid} | {'있음' if b['supported_response'] else '실패/없음'} | {'있음' if c['supported_response'] else '실패/없음'} | {b['model_calls']}→{c['model_calls']} | {b['usage']['input_tokens']:,}→{c['usage']['input_tokens']:,} | {b['request_seconds']:.1f}→{c['request_seconds']:.1f}초 |\n"
 q=next(x for x in m['questions'] if x['case_id']==cid);p=A/'실험'/q['file'];body=p.read_text().split('\n<!-- measured results -->')[0]
 body+='\n<!-- measured results -->\n\n'+table.splitlines()[0]+'\n'+table.splitlines()[1]+'\n'+table.splitlines()[-1]+'\n\n'
 for arm,label in [('baseline','MAIN52'),('main53','MAIN53')]:
  v=review['cases'][cid][arm];body+=f"**{label} 의미 검토:** "+v['summary']+'\n\n'
 body+='[동결 원문과 의미 검토](../artifacts/run-001/semantic-review.json). 제품 입력·응답·상태는 ../artifacts/run-001/raw.tar.gz, 파일별 해시·복원 방법은 raw-archive.json.\n'
 p.write_text(body);q['sha256']=sha(p)
tot=r['performance_comparison']['totals'];b=tot['baseline'];c=tot['main53'];ids=r['performance_comparison']['case_ids']
delta=lambda new,old: f'{(new/old-1)*100:+.1f}%' if old else '산정 불가'
perf=f"양쪽 근거 응답 비교쌍 {len(ids)}개({', '.join(ids) or '없음'}): 입력 {b['input']:,}→{c['input']:,}({delta(c['input'],b['input'])}), 호출 {b['calls']}→{c['calls']}, 요청시간 합계 {b['seconds']:.1f}→{c['seconds']:.1f}초({delta(c['seconds'],b['seconds'])})."
totals='| 릴리스 | 근거 응답 | 의미 검토 통과 | 호출 | 입력 | 출력 | 요청시간 합계 | 요청시간 중앙값 / 최대 |\n|---|---:|---:|---:|---:|---:|---:|---:|\n'
for arm,label in [('baseline','MAIN52'),('main53','MAIN53')]:
 v=r['by_arm'][arm];totals+=f"| {label} | {v['supported']}/3 | {v['semantically_correct']}/3 | {v['calls']} | {v['input_tokens']:,} | {v['output_tokens']:,} | {v['request_seconds']:.1f}초 | {v['request_p50']:.1f} / {v['request_max']:.1f}초 |\n"
semantic='\n\n'.join('**'+cid+'**\n\n'+'\n'.join('- '+label+': '+review['cases'][cid][arm]['summary'] for arm,label in [('baseline','MAIN52'),('main53','MAIN53')]) for cid in review['cases'])
sections=[
 ('결정 요약','사용자 요청에 따른 공개3문항·총6요청 비교 측정. 기존 MAIN53과 MAIN52의 코드를 그대로 실행했다. 결과에 따른 코드 수정·MAIN 변경·GENOS 배포는 하지 않았다. 실행 완료와 답변 품질을 구분한다.'),
 ('문제와 변경 전 구조','MAIN53의 최종 비교가 신규1문항에 한정되어 있었다. 이번에는 권한/의무/예외, 제목 검색과 기한, 주체별 의무의3유형을 추가 측정했다. 내부 CM 질문을 사용한 평가가 아니다.'),
 ('가설과 사전 판정 기준','artifacts/design/criteria.json에 질문·순서·6요청·무재실행·해시/권한/원문/상태 감사와 지표를 호출 전에 동결했다. 목표는 MAIN53 근거 응답3/3과 기준만 성공하는 회귀0. 의미 판단은 별도 원문 대조이며 신규 승격 기준은 아니다. 성능 개선 임계치를 사후 만들지 않는다.'),
 ('실험 설계','P01 기준→MAIN53, P02 MAIN53→기준, P03 기준→MAIN53 순서. 요청마다 새 프로세스와 세션. MAIN53의295파일을 snapshot/freeze하고 선택 릴리스와 전수 해시 대조했다. MAIN52 동결 코드는 공유했다. 기존 코드·캐시 정책·프로필·원문 세대를 변경하지 않았다.'),
 ('데이터·모델·재현성','공개 허용65문서 중3개의 저장 원문을 읽고 직접 작성한 공개 질문이다. 전체 노출 이력 미검증이므로 in_sample=true·decision_eligible=false이며 새 holdout이라고 하지 않는다. Qwen3.8/Parasail FP8/reasoning none/fallback 없음·출력6400·최대40콜. 실험 모델과 별도로 Opus5.5는 코드·일반화한 문제 설명만 받아 계획을 작성했다.'),
 ('결과',table+'\n'+totals+'\n'+perf+'\n\n근거 응답은 인용이 있는 실행 성공이며 의미상 정답과 다르다. [원시 집계](artifacts/run-001/result.json).'),
 ('사례별 오류 분석',semantic),
 ('비용·지연·회수 규모','실패를 포함한 전체 요청 비용과 양쪽 정상 근거 응답 쌍을 분리했다. provider가 보고하지 않은 사용량/비용은 채우지 않았다. 회수→읽기→실제 전송 조문 목록과 canonical ledger를 보존했다. 요청시간에는 요청 내부 원문 준비가 포함되고 앱 setup 시간은 별도다. OS 캐시·provider 부하는 통제하지 못했다.3문항 p95를 일반적인 지연 상한으로 해석하지 않는다.'),
 ('해석','고정한3문항에서 관측된 방향만 보고한다. 계약상 근거 연결, 실제 의미 정확성, 의역 반복, 실패 후 복구와 비용을 각각 판단한다. 데이터 선택의 편향과 모델 출력 변동이 있어 전체 CM·현장 성능으로 확대하지 않는다.'),
 ('한계와 일반화 가능 범위','3문항 각1회, 목적 표집, 독립 법률 전문가/별도 judge 합의 없음. 실제 내부 질문·GENOS 모델·동시접속·상주 서버 상태는 평가하지 않았다. 기존15검사 실패는 이번에 재실행/수정하지 않았다. 전역 graph의 기존8오류는 별도 보존한다.'),
 ('운영 결정·롤백 조건','MAIN53 포인터와 선택 코드·데이터를 유지했다. 구현·승격·Git main 병합·상주 서버 재시작·GENOS 적용 없음. [Opus5.5 계획](artifacts/planning/OPUS_PLAN.md)은 제안이며 실행 결과가 아니다. 후속 구현 효과 비교는 새 ADR에서 기준을 먼저 동결한다.'),
 ('재현 명령','06_TOOLS/EXPERIMENTS/adr_0762/prepare.py → run_all.py → offline semantic-review.json 작성 → audit.py → archive.py → report.py → adr_structure.py hash/status/validate --final/graph. 완료 결과를 재실행해 덮어쓰지 않으며 새 측정은 새 ADR에서 시작한다.')]
front=(A/'README.md').read_text().split('---',2)[1]
(A/'README.md').write_text('---'+front+'---\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{body}' for i,(h,body) in enumerate(sections,1))+'\n')
(A/'실험/README.md').write_text('# 공개3문항 MAIN52·MAIN53 비교\n\n'+table+'\n'+perf+'\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
(A/'MEASUREMENT_RESULT.md').write_text('# MAIN53 공개3문항 측정\n\n'+table+'\n'+totals+'\n'+perf+'\n\n'+semantic+'\n\nMAIN53 유지. 캐시·제품 코드 수정과 GENOS 배포 없음.3문항 목적 표집·각1회, 전체 품질 인증 아님. 상세 계약/회수/사용량과 한계는 [결정문](README.md)을 따른다.\n')
put(A/'실험/manifest.json',m)
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen inputs, measured outcomes, planning provenance and restoration evidence','contains_raw_prompts_and_outputs':p.name in ('raw.tar.gz','result.json','response.json','prompt.txt')} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not any(x in p.parts for x in ('provider','runtime','binding-runtime','setup-check'))]})
print(table+'\n'+perf)
