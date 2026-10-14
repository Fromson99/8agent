from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0753-bounded-selection-public-qualification';D=A/'artifacts';read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');r=read(D/'run-001/result.json');passed=r['strict_success'];failed=[k for k,v in r['checks'].items() if not v]
table='| arm | 원문 근거 응답 | 호출 | 입력 토큰 | 요청시간 합계 |\n|---|---:|---:|---:|---:|\n'
for arm,v in r['by_arm'].items():table+=f"| {arm} | {v['supported']}/{len(v['cases'])} | {v['calls']} | {v['input_tokens']:,} | {v['request_seconds']:.1f}초 |\n"
for q in m['questions']:
 p=A/'실험'/q['file'];s=p.read_text()+'\n\n| arm | HTTP | 호출 | 입력 토큰 | 시간 | 근거 응답 |\n|---|---:|---:|---:|---:|---|\n'
 for arm,v in r['by_arm'].items():
  c=next(x for x in v['cases'] if x['case_id']==q['case_id']);s+=f"| {arm} | {c['http_status']} | {c['model_calls']} | {c['usage']['input_tokens']:,} | {c['request_seconds']:.1f} | {c['supported_response']} |\n"
 s+='\nExact original provider inputs/outputs and native journals: ../artifacts/run-001/raw.tar.gz, SHA and restoration in raw-archive.json. [의미 검토](../SEMANTIC_REVIEW.md). No original/model text duplicated in this report.\n';p.write_text(s);q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
sections=[('결정 요약','동결한 기준을 통과한 로컬 MAIN 승격 후보.' if passed else 'Rejected: '+', '.join(failed)+'; MAIN52 유지.'),
 ('문제와 변경 전 구조','MAIN52는 모델에 긴 탐색 ID와 반복 카드 메타데이터를 전달한다. 추가 탐색의 필요성을 자유문 이유에 의존하고, bound 문서의 제목 부재를 문서 없음으로 잘못 보고할 수 있다. v5의 obligations 배열은 원문 허용을 의무로 표시하고 동일 내용을 결론·조건·의무에 반복할 수 있다.'),
 ('가설과 사전 판정 기준','criteria.json을 호출 전에 동결했다. 새 공개2문항 후보 모두 원문 근거 응답, 명시 양태 구분 보존, 원문·권한·상태·내용·실제 코드 결속을 요구한다. 양쪽 정상 완료 쌍 최소1개, 해당 쌍 합산 입력10% 이상 감소, 호출 증가 최대2회, 시간 증가 최대50%. 세부 의미 오류는 별도로 기록한다.'),
 ('실험 설계','완료752/integrated 코드 그대로318파일 상속, 서빙295파일 동결. H01 기준→후보, H02 후보→기준의 총4요청, 실행 후 수정·재시도·질문 대체 없음. 두 arm에 같은 연구 전용 구간 계측을 적용했다.'),
 ('데이터·모델·재현성','같은 원문 세대와 공개65문서, Qwen3.8/Parasail FP8/reasoning none/fallback 없음. 752까지의 노출과 수동 설계 열람 기록을 포함한6137개 primary root를 제외했다. 구현 고정 뒤 body350~900자·명시 양태·ID 순서와 서로 다른 문서를 기준으로 첫2개를 선택하되 이전 주 질문의 문서는 모두 제외했다. 본문 조문을 대상으로 하며 이전 설계 열람과 제외 기록도 계승했다. 이전 공개12질문 기록을 보존하면서 외부 표본을 작게 유지하는 후속 검증이다. 정답 자료는 평가기만 읽으며 제품 입력에 포함하지 않는다. 내부CM 데이터·GENOS 모델은 사용하지 않았다.'),
 ('결과',table+'\n정상 완료 쌍 비교: '+json.dumps(r['performance_comparison'],ensure_ascii=False)+'\n[집계](artifacts/run-001/result.json). 원문 근거 응답은 독립적인 법률 정답률이 아니다.'),
 ('사례별 오류 분석','[원문 대조와 의미 검토](SEMANTIC_REVIEW.md). 145개 핵심 경계·소비자 검사 통과, 전체416개에서 기존15개 외 새 실패0. 최초731의 카드 순서 오류와732~734의 테스트 소비자 가정 오류를 각각 실패 기록으로 보존했다.735에서 연결 검증,736에서 명시 양태를 보강했다.737 공개 비교에서 의역 중복과 검색 재개 중단을 발견했다.738은 단일 규정 출력,739는 검색 완료 진전을 구현했고740에서 잘못된 모의 페이지 구조를 바로잡았다.741은 직접 읽기에 쓰이지 않는 인용 필드 때문에 거절한 실패를 보존했다.742는 조건의 불필요한 ALL/ANY 중첩 표시만 정리하고743은 직접 요청의 권한과 참조 탐색의 근거를 구분했다.이후744의 원문 재작성 거절을 보존했다.745는 끝말 검출 미확정을 의미 오류 증명으로 취급하지 않고,746은 원문 ID 선택과 명시 표지 교정을 구현했다.145개 검사를 통과했다.'),
 ('비용·지연·회수 규모','사전 기준에 따라 양쪽 정상 완료 쌍만 비용 효과에 포함한다. 실패 요청의 실제 비용·사용량은 전체 집계에 보존한다. 구조/본문 탐색, 회수·전달·채택 목록, 물리 모델 호출, 입력/출력 토큰, 요청시간을 기록했다. 중첩 구간 시간 합계를 총 요청시간으로 해석하지 않는다.'),
 ('해석','긴 선택 ID는 호출별 가역 문자열로 바꾸고 서버가 원래 ID·엄격 스키마로 검증한다. 표 형태 카드는 열 순서를 고정하고 모든 원문·선택 값을 복원 검증한다. 추가 탐색마다 원래 요구 인용과 미해결 필요를 요구하며 의존 탐색은 전달된 원문 구절이 필요하다. v8는 모델이 원문 ID를 선택하면 서버가 정확한 인용을 붙인다. 명시 양태와 다른 분류 표지만 정규화하고 원래 표지를 기록한다. 설명 자체의 명백한 양태 반전은 거절한다. 끝말이 불명확한 경우는 원문 맥락에 따른 모델 판단으로 남기며 정답 인증으로 간주하지 않는다. 규정 답변은 결론·세부 설명·규정으로 세 번 작성하지 않고 단일 내용으로 작성·표시한다. 같은 원문·양태·효과·적용 맥락을 그대로 반복하면 병합하도록 요청한다. 서로 다른 효과나 조건은 같은 출처를 사용해도 허용한다.748은 자료 부족 재탐색을 형식 선호보다 먼저 처리했고749는 중복 판정을 정밀화했다.750은 근거 ID 반복으로 입력과 시간이 증가해 실패했다.751은 전송 단계에 목록 제한을 넣어 가역성 검사에서 거절됐고752는 원래 결정 스키마에서 선택지 수와 고유성을 제한해 원문·스키마 복원을 보존했다. 완료된 외부 검색의 신규 내용은 다음 중단 판정 전에 진전으로 반영하며 동일 결과는 초기화하지 않는다.'),
 ('한계와 일반화 가능 범위','소표본2문항으로 전체 품질·속도를 인증하지 않는다. 탐색 이유의 실제 의미적 적합성, 문장 간 추론, 의역 중복과 법률 해석의 정확성을 이 계약만으로 보증하지 않는다. 이전 v5/v6 및 v7의 source-modality-v2 저장 내용을 기존 표시로 검증한다. 캐시 작업은 사용자 지시로 제외했다. GENOS 실행 및 내부 데이터 품질은 미확인이다. 과거15개 테스트 실패와 실험 그래프8개 오류는 별도다.'),
 ('운영 결정·롤백 조건',('같은 검증 코드를 작업 코드에 선별 통합하고 MAIN 승격·포인터·실제 service 진입점을 확인한다.' if passed else '현재 후보는 승격하지 않는다. 후속 수정·재평가는 새 ADR에서 진행한다.')+' 사용자 기존 MAIN 지시와 현재1~4수정 지시가 승인이다. 원문 세대와 캐시는 바꾸지 않는다. 이전 포인터와 파일별 백업을 보존한다.'),
 ('재현 명령','06_TOOLS/EXPERIMENTS/adr_0753/run_all.py, audit.py, report.py, archive.py. Completed run과 부모 결과는 덮어쓰지 않는다.')]
front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: '+('Accepted' if passed else 'Rejected'))
(A/'README.md').write_text('---'+front+'---\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{b}' for i,(h,b) in enumerate(sections,1))+'\n')
(A/'실험/README.md').write_text('# 공개2문항 비교\n\n'+table+'\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
put(D/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen inputs, exact outputs, integrity and restore evidence','contains_raw_prompts_and_outputs':p.name in ('raw.tar.gz','result.json')} for p in D.rglob('*') if p.is_file() and p.name!='manifest.json' and not any(x in p.parts for x in ('provider','runtime','binding-runtime','sessions','working-backup','setup-check'))]})
print('Report',passed,failed)
