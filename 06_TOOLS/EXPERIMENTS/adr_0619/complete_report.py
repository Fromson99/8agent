"""Recover received judge dictionaries and add full inherited call evidence.

No new model invocation, no revised prompt/rubric, no replacement product answer.
"""
import importlib.util,json
from pathlib import Path
from common import ROOT,ADR,DESIGN,RUN,read,put,sha

def main():
    original=read(RUN/'offline-judge/scores.json');recovered=[]
    for score in original:
        x={**score};judges=[]
        if score['product_complete']:
            for repeat in (1,2):
                suffix=f"-{score['case_id']}-{score['arm']}-{score['turn']}-judge{repeat}"
                paths=[p for p in (RUN/'offline-judge/provider').glob('call-*') if p.name.endswith(suffix)]
                assert len(paths)==1
                judges.append(read(paths[0]/'output.json'))
        x.update(judges=judges,source_supported_resolution=len(judges)==2 and all(j['source_supported_resolution'] and not j['unsupported_facts'] for j in judges),
            reference_agreement=len(judges)==2 and all(j['reference_agreement'] for j in judges),
            disagreement=len(judges)==2 and judges[0]['source_supported_resolution']!=judges[1]['source_supported_resolution'])
        recovered.append(x)
    put(RUN/'offline-judge/scores-recovered.json',recovered)
    put(RUN/'offline-judge/recovery-receipt.json',{'raw_scores_sha256':sha(RUN/'offline-judge/scores.json'),
        'recovered_scores_sha256':sha(RUN/'offline-judge/scores-recovered.json'),
        'cause':'ExperimentClient.generate returns a parsed dict, not a (dict,receipt) tuple. The wrapper unpacking produced ValueError after successful calls.',
        'actual_calls':12,'additional_model_calls':0,'raw_votes_unchanged':True,'prompt_schema_rubric_unchanged':True})
    path=ROOT/'06_TOOLS/EXPERIMENTS/adr_0619/finalize.py';spec=importlib.util.spec_from_file_location('frozen_report',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    frozen_read=module.read
    module.read=lambda p:read(RUN/'offline-judge/scores-recovered.json') if Path(p)==RUN/'offline-judge/scores.json' else frozen_read(p)
    module.main()
    # Include the exact pre-interruption calls inline as required by the standard.
    m=read(ADR/'실험/manifest.json')
    for q in m['questions']:
        cid=q['case_id'];parts=['### 중단 전 실제 모델 호출 전문 — 승계 원본']
        for arm in ('baseline','unguided','guided'):
            for folder in sorted((RUN/cid/arm/'inherited-provider').glob('call-*')):
                parts.append('#### '+str(folder.relative_to(RUN)))
                for name in ('request.json','validation-schema.json','binding.json','response.json','output.json','error.json'):
                    if (folder/name).exists():parts+=['##### '+name,module.block(read(folder/name))]
        p=ADR/'실험'/q['file'];text=p.read_text();marker='## 6. 중간 LLM 호출'
        assert marker in text;text=text.replace(marker,'\n'.join(parts)+'\n\n'+marker,1);p.write_text(text);q['sha256']=sha(p)
    observation=read(DESIGN/'manual-source-observation.json')
    s=read(RUN/'cm-003/guided/secondary.json');eid=s['confirmation']['output']['experience_id']
    observation.update(reuse_also_contains_incorrect_statute_name='상법 제165조의6' in s['reuse']['output']['answer']['text'],
        same_experience_id_in_both_wikis=all(any(p['experience_id']==eid for p in s['queries'][kind]['output'].get('pages',[])) for kind in ('user_wiki','legal_wiki')),
        experience_id=eid,reuse_status=s['reuse']['output']['status'],
        reuse_executed=s['reuse']['output'].get('executed'))
    put(RUN/'manual-source-audit.json',observation)
    result=read(RUN/'result.json');result['manual_source_audit']=observation
    result['whole_answer_verified_success']={'baseline':0,'unguided':'CM003 conditional classification passed; complete extra-source citation audit not performed','guided':0}
    result['measurement_notes']=['Baseline and completed pre-interruption outputs carried over exactly. New ADR resumes only pending/unexecuted requests.',
        'Latency values mix completed original turns and continuation segment times; not ordinary uninterrupted end-to-end performance.',
        'Offline source judge saw decisive originals and evaluates core rule structure. Its positive verdict does not validate every extra citation; both judges noted unsupported external-law content in guided CM003 final.']
    put(RUN/'result.json',result);m['runs'][0]['sha256']=sha(RUN/'result.json')
    m['results']['manual_source_audit']=observation;m['results']['evaluation_recovery']=str((RUN/'offline-judge/recovery-receipt.json').relative_to(ROOT))
    m['results']['error_taxonomy'].append({'type':'other','classification':'manual_incorrect_statute_name_propagated_to_reuse','case_id':'cm-003','arm':'guided','detail':observation})
    m['results']['latency']['caveat']='Interrupted spans are not ordinary uninterrupted end-to-end latency; no GENOS performance inference.'
    put(ADR/'실험/manifest.json',m)
    summary='''# CM 사용자 가이드 실험 결과

가이드로 일부 오류를 고치는 가능성은 확인했지만, 두 사례 모두를 완전한 정답으로 확정하는 사전 기준은 충족하지 못했다. 구체 가이드의 우월성도 확인하지 못했다.

| 사례 | 최초 실패 | 가이드 후 | 최종 판정 |
|---|---|---|---|
| CM-051 보유비율 산정 | 필요한 두 원문을 읽고도 최종 근거를 선택하지 못해 답변 실패 | 1차는 시행규칙의 세부 산정법이 빠짐. 2차는 두 원문을 선택·제시했지만 예외 조항 해석 오류로 내부 검증이 거부 | 미해결 |
| CM-003 제3호·제4호 구분 | 재무적투자자의 법적 자격을 근거 없이 단정 | 1차는 자격·기간에 따른 조건부 판단으로 교정. 2차는 핵심 분류를 유지했지만 자본시장법 조문을 상법으로 쓰는 오류 추가 | 핵심 분류 개선, 전체 답변 정확도 미충족 |

CM-003의 일반 재검토 최종 답변도 조건부 분류 평가를 통과했다. 구체 가이드를 주는 것만이 유효하거나 더 낫다고 볼 수 없다. CM-051의 일반 재검토는 답변을 완료했지만 세부 산정법이 빠졌다.

CM-003은 확정 경험이 user_wiki·legal_wiki·정확한 경험 조회에 동일 ID로 나타나고, 새 대화에서 REUSED로 연결됐다. 그러나 잘못된 법령명도 새 답변에 다시 나타났다. 저장·재사용 성공과 법률 정확도는 별개다. 사용자의 확정만으로 잘못된 설명이 정답이 되지는 않는다.

외부 Qwen3.8 / Parasail FP8 / reasoning none / temperature0로 알려진 공개 CM 2사례를 실행했다. 최초 상태를 복제해 일반 재검토2회와 사전 고정 가이드2회를 비교했다. 제품 코드·가이드·채점 원문은 중단 전후 동일하다. 전체 이력 JSON 복제 중 종료된 실행은 ADR-0618에 보존하고, ADR-0619에서 중단·미실행 요청만 재개했다. 완료 응답은 저장소에서 복구했으며 채점 반환형 오류는 저장된 실제 응답을 읽어 바로잡았다. 추가 재채점 호출은 없었다.

핵심 판단 자동평가(각2회 동일 판정): 최초0/2, 일반 재검토1/2, 가이드 최종1/2. 이는 모든 인용·법령명을 검증한 점수가 아니다. 가이드 최종 전체 성공은0/2다. 과거 기준답의 무조건 제4호 결론과 조건부 원문 판단의 일치는 별도 지표다.

실제 선택·원문·답변·모델 입출력·비용은 [실험 기록](README.md)과 [질문별 인덱스](실험/README.md)에 보존했다. 저장된 원문 버전과 두 사례만 확인했으며 현재 법령 전수 정확도·GENOS 내부 모델 성능은 미확인이다. MAIN·GENOS 미반영.
'''
    summary+='\n보고된 실제 호출 비용 합계: $'+f"{result['costs']['reported_cost_usd']:.6f}"+'.\n'
    (ADR/'RESULT.md').write_text(summary)
    p=ADR/'README.md';text=p.read_text();text=text.replace('## 9. 해석','### 직접 원문 대조와 기억 전파\n\n'+
        'CM003 가이드2 및 새 대화 답변은 선택 원문 문서명과 달리 `상법 제165조의6`이라고 썼다. 실제 선택 원문은 `자본시장과 금융투자업에 관한 법률 제165조의6`이다. 핵심 판단 자동평가의 통과가 전체 인용 정확도를 보장하지 않는다. 동일 경험의 두 위키·재사용 연결은 확인됐지만 오류 전파도 확인됐다.\n\n'+
        '### 중단과 측정 범위\n\nADR0618 완료 응답을 승계하고 미완료 요청만 ADR0619에서 재개했다. 중단된 시간은 일반 지연으로 해석하지 않는다. 채점 집계의 반환형 오류는 저장된 실제12개 응답을 읽어 복구했으며 새로운 채점 호출은 없었다.\n\n## 9. 해석',1)
    p.write_text(text)
    # Rehash after evidence completion; frozen product/evaluator/design files remain untouched.
    artifact=read(ADR/'artifacts/manifest.json');existing={f['path']:f for f in artifact['files']}
    for p in [ADR/'RESULT.md',ROOT/'06_TOOLS/EXPERIMENTS/adr_0619/complete_report.py',*list((ADR/'artifacts').rglob('*.json'))]:
        if p==ADR/'artifacts/manifest.json':continue
        key=str(p.relative_to(ROOT));existing[key]={'path':key,'sha256':sha(p),'bytes':p.stat().st_size,'description':'Actual unchanged raw evidence or read-only report recovery','contains_raw_prompts_and_outputs':'provider/' in key}
    artifact['files']=list(existing.values());put(ADR/'artifacts/manifest.json',artifact)
    print(json.dumps({'by_arm':result['by_arm'],'costs':result['costs'],'manual_source_audit':observation},ensure_ascii=False))

if __name__=='__main__':main()
