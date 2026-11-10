"""Per-question grades by this session (direct comparison with grading-only.json and stored originals; no judge model)."""
from common import *
import csv,statistics,collections
G={
'cm-001':('PASS','','"각각" 100분의 10을 개별 한도로 해석, 제26조①4 일치'),
'cm-002':('PASS','','투자기간 기준일(상장예비심사 신청일)과 자본금 기준(상장신청일 현재) 모두 일치'),
'cm-003':('PASS','','세칙 제23조④2로 제3호 제외·제4호 적용(사실 확인 질문은 선택 사항)'),
'cm-004':('PASS','','세칙 제23조⑥ 취득가격·공모가격(인수규정 제5조①)·괴리율 산식 일치'),
'cm-005':('PARTIAL','CONCLUSION_WITHHELD','벤처금융 표현 없음을 확인했지만 결론을 유보하고 되물음'),
'cm-006':('PASS','','세칙 제21조②1 투자 목적 전문투자자 수량 제외 일치'),
'cm-007':('PARTIAL','INCOMPLETE','코스닥 제13조⑤ 수량·기간 일치, 유가 제13조③(외국주권 5%·50억·6개월) 대신 제27조로 답함'),
'cm-008':('FAIL','NOT_READ','제13조⑤1나 단서·세칙 제15조⑤ 미확보, 제26조①5 괴리율로 답함'),
'cm-009':('PASS','','코스닥 제13조⑥ 대형법인·적격해외상장 3년 외국기업 면제 일치'),
'cm-010':('FAIL','MISREAD','인수규정 제6조 ③ 대신 ⑤(확약서 제출분)로 답함'),
'cm-011':('PASS','','코스닥 제29조①2·② 세칙 위임 일치'),
'cm-012':('FAIL','NO_ANSWER','원문 0건, "외규가 어느 문서인가" 되물음'),
'cm-013':('PASS','','제16조의3①~④ 일치(제16조의6③ 상법 특례 언급 없음)'),
'cm-014':('PARTIAL','INCOMPLETE','제16조의3④⑤ 저가 부여와 시가 평가 일치, 시행령 제11조의3⑤ 20억원 요건 누락'),
'cm-015':('PASS','','제16조의6① 중기부장관 신고·시행령 제11조의5① 첨부서류 일치'),
'cm-016':('PASS','','제16조의5① 2년, 시행령 제11조의4① 예외·정년 제외 일치'),
'cm-017':('PASS','','시행령 제11조의3② 상증법 제60조·시행령 제49조 준용, 전 6개월 일치'),
'cm-018':('PASS','','제49조① 본문 각 호와 단서 일치'),
'cm-019':('PASS','','제49조의2① 국세청·지방국세청 평가심의위원회 일치'),
'cm-020':('PASS','','시행령 제57조① 기간·큰 가액 평가 일치'),
'cm-021':('PASS','','시행령 제57조 괄호: 증여세 3개월, 그 외 6개월 일치'),
'cm-022':('FAIL','MISLABEL','제54조⑥을 보충적 평가방법으로 설명, ① 3:2 가중평균·80% 하한 누락'),
'cm-023':('PASS','','제41조의3 요건·5년·정산기준일 일치'),
'cm-024':('PASS','','시행령 제31조의3③ 기준금액 일치'),
'cm-025':('PARTIAL','CONCLUSION_WITHHELD','제31조의3① 차감 구조 설명, 별도 조정 규정 없음은 밝히지 않고 되물음'),
'cm-026':('PASS','','제41조의3⑦ 신주 인수·배정 포함 일치'),
'cm-027':('PASS','','조특법 제16조의2 연 2억·누적 5억 비과세와 대상 일치'),
'cm-028':('PASS','','제16조의4①② 요건·효과 일치'),
'cm-029':('FAIL','NOT_READ','소득세법 시행령 제163조⑬ 미확보, 실지거래가액(행사가액)·조특법 B로 답하고 되물음'),
'cm-030':('PARTIAL','CONCLUSION_WITHHELD','제2-4조의 "금융기관·주권상장법인 분기재무제표 확정 이후" 한정을 찾았지만 제2-6조에 잇지 못하고 상장 여부를 되물음'),
'cm-031':('PASS','','코스닥 제5조④ 반기 45일 반기재무제표·검토보고서, ⑤ 외국기업 분기 일치'),
'cm-032':('PASS','','자본시장법 제160조① 45일·연결 최초 2개 사업연도 60일 일치'),
'cm-033':('PASS','','처음 전환 법인도 최초·다음 사업연도 60일 일치'),
'cm-034':('PASS','','제160조② 5일·제출기간 중 그 기한·공시 시 면제 일치'),
'cm-035':('PASS','','외감법 제8조① 단서·시행령 제9조① 면제 기준 일치'),
'cm-036':('PARTIAL','MISREAD','제8조③ 상근이사 1명은 맞지만 상근이사가 집행임원을 포함한다며 등기임원이어야 한다고 단정'),
'cm-037':('PASS','','제8조⑥ 검토·감사 구분 일치'),
'cm-038':('PASS','','제8조④ 단서 이사회·감사 보고만 위임 가능 일치'),
'cm-039':('PARTIAL','CONCLUSION_WITHHELD','제361조·제393조 확보, 결론 유보·정관 되물음'),
'cm-040':('PASS','','제434조 3분의 2·3분의 1 일치'),
'cm-041':('PARTIAL','CONCLUSION_WITHHELD','"근거 선택 결정을 확정하지 못해" 제한 답변, 제383조① 규정은 쓰고 상장회사 적용은 확정 못함'),
'cm-042':('PASS','','제542조의8 독립이사 정의·3분의 1·3명 과반수 일치'),
'cm-043':('FAIL','NOT_READ','상법 제415조(제388조 준용) 미확보, 감사 보수 규정을 못 찾았다며 되물음'),
'cm-044':('PASS','','제542조의12② 단서 1명(정관 2명 이상) 일치'),
'cm-045':('PASS','','제341조의4 ①~④ 일치'),
'cm-046':('PASS','','제342조①~③·제341조의4② 2~5호 일치'),
'cm-047':('PARTIAL','BASIS_DIFFERS','20% 배정을 인수규정 제9조·근로복지기본법으로 설명, 자본시장법 제165조의7①(상법 제418조에도 불구한 강제배정)은 단서만 언급'),
'cm-048':('PASS','','상법 제416조 이사회 결정·단서 일치'),
'cm-049':('PARTIAL','CONCLUSION_WITHHELD','제6조①·제2조9호 계열회사=이해관계인을 쓰고도 "포함될 수 있다"로 유보하고 되물음'),
'cm-050':('PASS','','제15조④2 단서 가~라목 일치'),
'cm-051':('PASS','','제6조② 시행규칙 제14조① 준용·③④⑤ 일치'),
}
rows=read(ART/'review-input.json')['rows'];audit={c['case_id']:c for c in read(ART/'source-wire-audit.json')['cells']}
assert set(G)=={r['case_id'] for r in rows}
counts=collections.Counter(g[0] for g in G.values())
req=[r for r in rows if r['required_total']]
stats={'grades':dict(counts),'physical_calls':sum(audit[c]['physical_calls'] for c in audit),'unknown':sum(audit[c]['unknown'] for c in audit),
 'reported_cost_usd':round(sum(audit[c]['reported_cost_usd'] for c in audit),6),'request_seconds_median':round(statistics.median(r['request_seconds'] for r in rows),1),
 'request_seconds_total':round(sum(r['request_seconds'] for r in rows)),'required_acquired':sum(r['required_acquired'] for r in rows),'required_cited':sum(r['required_cited'] for r in rows),
 'required_total':sum(r['required_total'] for r in rows),'source_mismatches':sum(len(audit[c]['source_mismatches']) for c in audit),'acl_violations':sum(len(audit[c]['acl_violations']) for c in audit)}
put(ART/'grades.json',{'grades':{k:list(v) for k,v in G.items()},'stats':stats,'grader':'this session, direct comparison with grading-only.json and stored originals; no judge model','rule':read(DES/'criteria.json')['grading_rule']})
with (ART/'CM51_결과.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['case_id','grade','failure_type','adr1464_grade','adr1464_failure','main161_grade','required_acquired','required_cited','required_total','seconds','physical_calls','question','reason','answer'])
 for r in rows:
  g=G[r['case_id']];w.writerow([r['case_id'],g[0],g[1],r['adr1464']['grade'],r['adr1464']['failure_type'],r['main161']['grade'],r['required_acquired'],r['required_cited'],r['required_total'],round(r['request_seconds'],1),r['physical_calls'],r['question'],g[2],r['answer']])
print(json.dumps(stats,ensure_ascii=False))
moves=collections.Counter((r['adr1464']['grade'],G[r['case_id']][0]) for r in rows);print(dict(moves))
print('better',[r['case_id'] for r in rows if ['FAIL','PARTIAL','PASS'].index(G[r['case_id']][0])>['FAIL','PARTIAL','PASS'].index(r['adr1464']['grade'])])
print('worse',[r['case_id'] for r in rows if ['FAIL','PARTIAL','PASS'].index(G[r['case_id']][0])<['FAIL','PARTIAL','PASS'].index(r['adr1464']['grade'])])
print('with required',collections.Counter(G[r['case_id']][0] for r in rows if r['required_total'] and r['case_id'] not in ('cm-012','cm-025','cm-033','cm-036','cm-039','cm-043','cm-044','cm-005')))
