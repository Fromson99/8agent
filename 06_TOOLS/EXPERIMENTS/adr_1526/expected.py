"""ADR-1526: what each step is checked against, written before any vector or model result (observation only, not a gold set).
From earlier 대사 targets (ADR-1515~1524 grading) and the internal text read by hand on 2026-11-13."""
from common import *
put(ART/'expected.json',{
 'note':'Expected counterparts for three internal articles; other articles are read by hand. A hit = the expected external article is in the top 10 vector candidates, chosen by the model, or one connection step from a top-5 candidate.',
 'pairs':[{'internal':'제2-1조 건전성비율','external':[{'document':'금융투자업규정','article':'제3-24조의4'},{'document':'금융투자업규정','article':'제3-6조'}]},
          {'internal':'제6-4조 단기유동성지표','external':[{'document':'금융투자업규정','article':'제3-24조의4'},{'document':'금융투자업규정시행세칙','article':'제2-8조의3'},{'document':'금융투자업규정','article':'별표 10'}]},
          {'internal':'제11-6조 외국환 포지션 한도','external':[{'document':'금융투자업규정시행세칙','article':'제2-15조'},{'document':'외국환거래규정','article':None}]}],
 'expected_documents':['금융투자업규정','금융투자업규정시행세칙','자본시장과 금융투자업에 관한 법률','외국환거래규정'],
 'written_before_results':True})
print('ok')
