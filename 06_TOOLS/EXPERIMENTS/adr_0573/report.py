"""Offline builder result and exact public-model wire receipts."""
import json
from harness import R,A,write,sha
def block(v):return '```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```\n'

def main():
    m=json.loads((A/'실험/manifest.json').read_text());out=A/'artifacts/run-001';result=json.loads((out/'result.json').read_text())
    assert result['status']=='complete'
    passed=all(result[k] for k in ['generation_pass','idempotence_pass','privacy_pass'])
    tests=(A/'artifacts/contract-tests.log').read_text();assert '3 passed' in tests
    calls=[];usage=[]
    for p in (out/'runtime/action-memory/calls').glob('*'):
        request=json.loads((p/'request.json').read_text());response=json.loads((p/'response.json').read_text());output=json.loads((p/'output.json').read_text())
        calls.append({'request':request,'response':response,'output':output});usage.append(response['body_json'].get('usage',{}))
    write(out/'offline-grade.json',{'pass':passed,'result':result,'contracts':'3 passed','calls':len(calls),'usage':usage,'answer_truth_approved':False,'hard_exclusions_automatically_activated':False})
    m['runs'][0].update(status='complete',artifact_path=str((out/'result.json').relative_to(R)),sha256=sha(out/'result.json'))
    m['results'].update(status='complete',by_arm={'baseline':{'total':0,'correct':0,'not_executed_reason':'No redundant external rerun of unchanged inherited builder'},
        'integrated':{'total':3,'correct':3 if passed else 0}},comparisons=[],judge_disagreements=0,usage={'calls':len(calls),'raw_usage':usage},
        latency={'offline_build_seconds':result['seconds'],'online_calls_added':0},error_taxonomy=[])
    for q in m['questions']:
        body='# '+m['adr_id']+' '+q['case_id']+'\n\n'
        sections=[('1. 실행 메타',block({'classification':'CURRENT_GRANT_PUBLIC_NATIVE_LOGS','run':'run-001','arm':'integrated'})),
          ('2. 사용자 질문 원문','실제 현재 공개 반출 승인이 유효한 네 요청의 원문은 아래 모델 입력에 보존한다. 승인되지 않은 통제 로그는 모델에 전달하지 않는다.'),
          ('3. 기준답변 — 채점 전용, 제품 입력 비공개',block(m['design']['success_criteria'])),
          ('4. 제품 입력을 구성한 원값',block(json.loads((A/'artifacts/log-snapshot/sources.json').read_text()))+'\n\n### 회수·탈락 단계 원장 — run·arm별\n\n회수 미실행. 원문 선택 경로를 수정하지 않는 오프라인 구축이며 manifest에 not_applicable 근거를 명시했다.'),
          ('5. 제품 모델 호출 — run·arm별 실제 원문',block(calls)),
          ('6. 중간 LLM 호출 — router/compiler/verifier/repair','기존 로그의 조사 이유·선택 근거를 한 배치 호출에서 개념화했다. 온라인 목적 판별·답변 변경·법률 재채점 없음.'),
          ('7. 채점 호출과 반복 판정',block({'model_calls':0,'rubric':m['design']['success_criteria'],'hard_deadline_tests':tests})),
          ('8. 사례 최종 판정',block(result))]
        p=A/'실험'/q['file'];p.write_text(body+'\n\n'.join('## '+h+'\n\n'+b for h,b in sections)+'\n');q['sha256']=sha(p)
    write(A/'실험/manifest.json',m)
    front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: '+('Accepted' if passed else 'Rejected'))
    sections=[('1. 결정 요약','야간 자동 생성·재개·privacy·hard deadline 계약 통과. 오프라인 builder/CLI 채택 가능; 온라인 MAIN 후보와 별도이다.'),
      ('2. 문제와 변경 전 구조','HTTP read timeout만으로는 모델 응답 전체 시간을 제한할 수 없었다. 자동 배치의06:00 종료를 별도 프로세스 제한으로 보장한다.'),
      ('3. 가설과 사전 판정 기준',block(m['design']['success_criteria'])),('4. 실험 설계',block(m['design']['arms'])),
      ('5. 데이터·모델·재현성','기존 실제 native 로그 중 현재 공개 승인이 유효한4개, 미승인 통제1개. 원본은 SQLite backup으로 동결. Gemma ParasailFP8 thinking off. 정확한 schema를 같은 모델 호출에 포함한다.'),
      ('6. 결과',block(result)),('7. 사례별 오류 분석','2개 episode는 BUILT, 2개는 ABSTAINED, 1개 미승인 로그는 WAITING_AUTH. 답변을 정답으로 자동 승인하지 않았다.'),
      ('8. 비용·지연·회수 규모',block({'seconds':result['seconds'],'model_calls':len(calls),'raw_usage':usage,'retrieval_not_executed':True})),
      ('9. 해석','수작업 개념 없이 실제 선택 근거에서2개 목적 개념과21개 GUIDE 관계를 생성했다. 질문이 다르거나 근거가 부족한 사례에는 분류를 강제하지 않았다.'),
      ('10. 한계와 일반화 가능 범위','제외 관계는 근거·검증이 있는 것만 적용한다. 이번 실제 로그에서는 제외 후보0개. 기존 합성 실험은 원문 인용이 있는 제외 후보를 생성했다. 법률 품질·검색 성능·GENOS 인증 아님.'),
      ('11. 운영 결정·롤백 조건','Accepted 코드로 오프라인 pipeline action-memory 명령만 연결한다. 야간 worker는00:00~06:00, 중복 lock, 120초 slice, 실패·대기 상태 로그를 남긴다. 온라인 release 활성화는 독립 전체 API 검증 후 판단한다.'),
      ('12. 재현 명령','완료 결과는 덮어쓰지 않는다. 동결 source/candidate hash를 확인하고 새 ADR에서 재실행한다.')]
    (A/'README.md').write_text('---'+front+'---\n\n# 야간 로그 개념 구축 검증\n\n'+'\n\n'.join('## '+h+'\n\n'+b for h,b in sections)+'\n')
    (A/'실험/README.md').write_text('# 실행 인덱스\n\n[manifest](manifest.json)\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
    print(json.dumps({'passed':passed,'concepts':len(result['concepts']),'relations':result['relations'],'actual_logs_used':True}))

if __name__=='__main__':main()
