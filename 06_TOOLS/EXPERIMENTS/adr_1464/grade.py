"""Per-question grades by this session (direct comparison with grading-only.json and stored originals; no judge model)."""
from common import *
import csv,statistics,collections
G={
'cm-001':('PASS','','"각각" 100분의 10을 투자자별 한도로 해석, 제26조①4 인용 일치'),
'cm-002':('PARTIAL','INCOMPLETE','투자기간 기준일(상장예비심사신청일)만, 자본금 기준(상장신청일 현재) 누락'),
'cm-003':('PASS','','세칙 제23조④2로 제3호 제외·제4호 적용'),
'cm-004':('PASS','','세칙 제23조⑥ 취득가격·공모가격(인수규정 제5조①)·괴리율 산식 일치'),
'cm-005':('PARTIAL','CONCLUSION_WITHHELD','제27조에 벤처금융 표현 없음을 확인했지만 결론을 유보하고 되물음'),
'cm-006':('PASS','','세칙 제21조②1 투자 목적 전문투자자 수량 제외 일치'),
'cm-007':('PASS','','코스닥 제13조⑤ 국내·신속이전·외국기업 수량·기간, 유가 제13조③ 외국주권 5%·50억·6개월 일치'),
'cm-008':('PASS','','제13조⑤1나 단서·세칙 제15조⑤ 상장주선인 과거 주선 실적 요건 일치'),
'cm-009':('FAIL','NOT_READ','제13조⑥ 미확보, 제16조 의무보유 예외로 답하고 되물음'),
'cm-010':('FAIL','MISREAD','인수규정 제6조를 읽었지만 ③(제13조⑤1 취득분 제외) 대신 ⑤(확약서 제출분)로 답함'),
'cm-011':('PASS','','코스닥 제29조①2·② 세칙 위임 일치'),
'cm-012':('FAIL','PROCESSING_ERROR','"판단 처리 오류" 안내, 답변 없음'),
'cm-013':('PASS','','제16조의3① 결의(434 준용)·대상, ③ 50%/10%, ④ 행사가격, 제16조의6 일치'),
'cm-014':('PARTIAL','INCOMPLETE','시가 평가방법(시행령 제11조의3②)만, 제16조의3⑤ 저가 부여·시행령 ⑤ 20억원 요건 누락'),
'cm-015':('PASS','','제16조의6① 중기부장관 신고·시행령 제11조의5① 첨부서류 일치'),
'cm-016':('PASS','','제16조의5① 결의일·이사회 정한 날부터 2년, 시행령 제11조의4① 예외·정년 제외 일치'),
'cm-017':('PASS','','시행령 제11조의3② 상증법 제60조·시행령 제49조 준용, 전 6개월 일치'),
'cm-018':('PASS','','제49조① 본문 각 호와 단서(평가심의위원회 심의·신청) 일치'),
'cm-019':('PASS','','제49조의2① 국세청·지방국세청 평가심의위원회 일치'),
'cm-020':('PASS','','상증법 제63조②·시행령 제57조① 기간(6개월/3개월)과 큰 가액 평가 일치'),
'cm-021':('FAIL','PROCESSING_ERROR','"판단 처리 오류" 안내, 답변 없음'),
'cm-022':('FAIL','MISLABEL','제54조를 읽었지만 ⑥(평가심의위원회 신청 방법)을 보충적 평가방법으로 설명, ① 3:2 가중평균·80% 하한 누락'),
'cm-023':('PASS','','제41조의3 요건·5년·정산기준일 일치'),
'cm-024':('PASS','','시행령 제31조의3③ 기준금액(30%와 3억원 중 적은 금액) 저장 원문과 일치'),
'cm-025':('PARTIAL','CONCLUSION_WITHHELD','제31조의3① 차감 구조 설명, 제35조·제39조 과세분 별도 조정 규정 없음은 밝히지 않고 되물음'),
'cm-026':('PASS','','제41조의3⑦ 신주 인수·배정 포함 일치'),
'cm-027':('PASS','','조특법 제16조의2 연 2억·누적 5억 비과세와 대상(벤처법·상법 코넥스) 일치(제16조의4도 함께 설명)'),
'cm-028':('PASS','','제16조의4①② 요건·양도소득세·시가 이하 발행이익 행사 시 과세 일치'),
'cm-029':('FAIL','NOT_READ','소득세법 시행령 제163조⑬ 미확보, 제97조 실지거래가액(행사가액)으로 답함'),
'cm-030':('FAIL','NOT_READ','증발공 제2-4조⑤3라 정의 미확보, 제2-6조⑧1라를 근거로 첨부해야 한다고 반대 결론'),
'cm-031':('FAIL','NOT_READ','코스닥 상장규정 제5조④ 미확보, 시행세칙 재무서류 조문으로 답함'),
'cm-032':('PASS','','자본시장법 제160조① 45일·연결기준 최초 2개 사업연도 60일 일치'),
'cm-033':('PASS','','"최초"가 연결기준 작성을 수식, 처음 전환 법인도 60일 일치'),
'cm-034':('PASS','','제160조② 5일 이내·제출기간 중이면 그 기한·증권신고서 공시 시 면제 일치'),
'cm-035':('PASS','','외감법 제8조① 단서·시행령 제9조①3 5천억원 미만과 제외 대상 일치'),
'cm-036':('PASS','','제8조③ 상근이사 1명, 등기 여부 직접 규정 없음 일치'),
'cm-037':('PASS','','제8조⑥ 검토 원칙·주권상장법인(1천억원 미만 제외) 감사 일치'),
'cm-038':('PASS','','제8조④ 단서 이사회·감사 보고만 위임 가능 일치'),
'cm-039':('PARTIAL','CONCLUSION_WITHHELD','제361조·제393조 확보, 이사회 결의사항일 여지까지 쓰고 결론 유보·되물음'),
'cm-040':('PASS','','제434조 3분의 2·3분의 1 일치'),
'cm-041':('PASS','','제383조① 3명 이상·자본금 10억원 미만 예외, 상장 여부 무관 일치'),
'cm-042':('PASS','','제542조의8 독립이사 명칭 변경·정의·3분의 1·3명 과반수 일치'),
'cm-043':('FAIL','NOT_READ','상법 제415조(제388조 준용) 미확보, 감사 보수 규정을 못 찾았다며 결론 없이 되물음'),
'cm-044':('PASS','','제542조의12② 단서 1명(정관 2명 이상) 일치'),
'cm-045':('PASS','','제341조의4 ①~④ 일치'),
'cm-046':('PASS','','제342조①~③·제341조의4② 2~5호 일치'),
'cm-047':('PASS','','자본시장법 제165조의7① 상법 제418조에도 불구한 20% 배정·단서 일치'),
'cm-048':('PASS','','상법 제416조 이사회 결정·단서 일치'),
'cm-049':('PASS','','제6조① 5%(10%)·제2조9호 라목 계열회사=이해관계인으로 공동주관 의무 결론(확인 질문은 선택 사항)'),
'cm-050':('PASS','','제15조④2 단서 가~라목·창업지원법 업종 제외 일치'),
'cm-051':('PASS','','제6조② 시행규칙 제14조① 준용·④ 조합 출자비율 귀속 일치'),
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
 w=csv.writer(f);w.writerow(['case_id','grade','failure_type','adr1461_grade','adr1461_failure','main161_grade','required_acquired','required_cited','required_total','seconds','physical_calls','question','reason','answer'])
 for r in rows:
  g=G[r['case_id']];w.writerow([r['case_id'],g[0],g[1],r['adr1461']['grade'],r['adr1461']['failure_type'],r['main161']['grade'],r['required_acquired'],r['required_cited'],r['required_total'],round(r['request_seconds'],1),r['physical_calls'],r['question'],g[2],r['answer']])
print(json.dumps(stats,ensure_ascii=False))
moves=collections.Counter((r['adr1461']['grade'],G[r['case_id']][0]) for r in rows);print(dict(moves))
print('better',[r['case_id'] for r in rows if ['FAIL','PARTIAL','PASS'].index(G[r['case_id']][0])>['FAIL','PARTIAL','PASS'].index(r['adr1461']['grade'])])
print('worse',[r['case_id'] for r in rows if ['FAIL','PARTIAL','PASS'].index(G[r['case_id']][0])<['FAIL','PARTIAL','PASS'].index(r['adr1461']['grade'])])
print('with required',collections.Counter(G[r['case_id']][0] for r in rows if r['required_total'] and r['case_id'] not in ('cm-012','cm-025','cm-033','cm-036','cm-039','cm-043','cm-044','cm-005')))
