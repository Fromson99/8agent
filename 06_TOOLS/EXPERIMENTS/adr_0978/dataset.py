"""Fresh expressions and gold-free structure fixtures, frozen before calls."""
from common import *
cases=[
('h01','상법 기준으로 주주가 총회에서 행사하는 의결권을 정리해줘',['상법']),
('h02','법인세법에 적힌 신고 절차를 찾아 설명해줘',['법인세법']),
('h03','개인정보 보호법에 따른 정보주체의 권리를 알아보고 싶어',['개인정보 보호법']),
('h04','상법 시행령 안에서 관련 서류 보관 규칙을 찾아줘',['상법 시행령']),
('h05','외국환거래법과 외국환거래규정 두 문서에서 신고 규칙을 비교해줘',['외국환거래법','외국환거래규정']),
('h06','법인세법은 회의 배경이고, 실제 질문은 상법의 이사회 권한이야',['상법']),
('h07','상법은 이번 조사에서 빼고 소득세법만 살펴봐줘',['소득세법']),
('h08','검색 대상을 특정하지 않을게. 회사 의사결정의 일반 원칙을 알려줘',[]),
('h09','어제 상법 교육을 들었어. 오늘은 문서를 제한하지 않고 보고 절차를 조사해줘',[]),
('h10','민법에 정한 대리의 효과를 설명해줘',['민법']),
('h11','상법을 봤다는 건 배경이고 지금은 민법만 대상으로 찾아줘',['민법']),
('h12','개인정보 보호법과 그 시행령 둘에서 동의 규칙을 확인해줘',['개인정보 보호법','개인정보 보호법 시행령']),
('h13','기록검수규정 제21조와 제24조의 내용을 함께 설명해줘',['기록검수규정']),
('h14','안전점검규정 제24조부터 제26조까지를 읽고 요약해줘',['안전점검규정']),
('h15','기록검수규정 제21조제2항에서 제2호와 제5호만 확인해줘',['기록검수규정']),
('h16','안전점검규정 제24조제2항 중 제3호를 제외한 내용을 설명해줘',['안전점검규정']),
('h17','기록검수규정 전체를 범위로 검수 책임을 찾아줘',['기록검수규정']),
('h18','기록검수규정은 배경이고 안전점검규정 전체에서 점검 절차를 찾아줘',['안전점검규정']),
('h19','기록검수규정 제21조와 안전점검규정 제26조를 나란히 설명해줘',['기록검수규정','안전점검규정']),
('h20','문서 종류는 상관없어. 검수 책임자를 정하는 기준을 찾아줘',[]),
('h21','상법 제361조와 제362조를 함께 설명해줘',['상법']),
('h22','기록검수규정 제21조제2항제4호가 적용되지 않는 상황을 가정하고 제21조제2항 전체를 설명해줘',['기록검수규정']),
('h23','기록검수규정 제999조를 읽고 설명해줘',['기록검수규정']),
('h24','상법과 법인세법 중 오늘은 법인세법에서만 근거를 찾아줘',['법인세법'])]
docs=[]
titles=['기록검수규정','안전점검규정']
for did,title in zip(('SYN_A','SYN_B'),titles):
 nodes=[]
 for art in (21,24,25,26):
  aid=str(art);nodes.append({'id':aid,'parent':None,'surface':f'제{art}조','title':'검수 책임' if art==21 else '기록 확인' if art==24 else '점검' if art==25 else '보관', 'family':'kr_article','coordinate_scope':'body','span':[len(nodes),len(nodes)+1]})
  pid=f'{art}-2';nodes.append({'id':pid,'parent':aid,'surface':'②','title':'','family':'kr_paragraph','coordinate_scope':'body','span':[len(nodes),len(nodes)+1]})
  for n in range(1,6):nodes.append({'id':f'{art}-2-{n}','parent':pid,'surface':f'{n}.','title':'','family':'kr_item','coordinate_scope':'body','span':[len(nodes),len(nodes)+1]})
 docs.append({'id':did,'title':title,'nodes':nodes})
save(ART/'documents.json',docs)
products=[{'id':cid,'question':q,'retrieval_input':{'document_id':'SYN_A' if i%2==0 else 'SYN_B','query':['검수 절차','기록 확인 담당','점검','아무런 제목 일치 없음'][i%4]}} for i,(cid,q,_) in enumerate(cases)]
gold={cid:{'names':sorted(want),'unresolved':cid in ('h10','h11','h23')} for cid,_,want in cases}
gold['h13']['units']={'SYN_A':['21','24']};gold['h14']['units']={'SYN_B':['24','25','26']}
gold['h15']['units']={'SYN_A':['21-2-2','21-2-5']};gold['h16']['units']={'SYN_B':['24-2-1','24-2-2','24-2-4','24-2-5']}
gold['h19']['units']={'SYN_A':['21'],'SYN_B':['26']};gold['h21']['coordinates']=['제361조','제362조'];gold['h22']['units']={'SYN_A':['21-2']}
save(ART/'cases.json',products);save(ART/'grading-only.json',gold)
print('Frozen input authored: 24 fresh expressions, 8 synthetic articles, 56 nodes')
