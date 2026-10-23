from common import *
cases=[
 {'id':'e01','phase':'assessment','question':'모의운영규정에서 운영위원회 일반 안건의 의결 요건을 알려줘.','originals':['제18조(일반 안건의 의결) 운영위원회 일반 안건은 재적위원 과반수 출석과 출석위원 3분의 2 이상의 찬성으로 의결한다.']},
 {'id':'e02','phase':'assessment','question':'모의지원규정에서 지원금의 산정 방법을 알려줘.','originals':['제6조(지원금) 지원금은 제9조의 산식으로 계산한다.']},
 {'id':'e03','phase':'assessment','question':'모의회의규정의 일반회의와 긴급회의 의결 요건을 각각 비교해줘.','originals':['제2조(일반회의) 일반회의는 재적 구성원 과반수의 찬성으로 의결한다.']},
 {'id':'e04','phase':'assessment','question':'모의신고규정에서 변경신고의 제출 기한은?','originals':['제4조 변경신고는 변경일 다음 날부터 12일 이내에 제출하여야 한다.','제8조 신규등록은 신청 접수일부터 30일 이내에 처리한다.'],'previous_claim':'변경신고는 변경일 다음 날부터 12일 이내에 제출해야 한다.','old_gap':'신규등록의 처리 기한 원문이 없다.'},
 {'id':'e05','phase':'navigation','question':'모의회의규정에서 운영위원회의 의결 기준은?','originals':['운영위원회는 재적위원 과반수 출석과 출석위원 과반수 찬성으로 의결한다.'],'previous_claim':'운영위원회 의결은 재적위원 과반수 출석과 출석위원 과반수 찬성이 필요하다.','old_gap':'자문위원회의 의결 기준 원문도 아직 없다.','candidates':[{'target':'T1','heading':'제25조 자문위원회 의결','preview':'자문위원회의 의결'}]},
 {'id':'e06','phase':'navigation','question':'모의재무규정의 준비금 계산 방법을 설명해줘.','originals':['제7조 준비금은 제12조의 산정식에 따라 계산한다.'],'candidates':[{'target':'T1','heading':'제12조 준비금 산정식','preview':'준비금은 다음 식으로 산정한다.'}]},
 {'id':'e07','phase':'navigation','question':'모의출장규정의 교통비 지급 기준을 알려줘.','originals':['제3조 직원은 출장 전에 출장계획서를 제출하여야 한다.'],'candidates':[{'target':'T1','heading':'제15조 숙박비','preview':'숙박비 지급 기준'}]},
 {'id':'e08','phase':'navigation','question':'모의보존규정 제11조의 보존기간을 확인해줘.','originals':['제10조 보존기간은 제11조에 따른다.'],'candidates':[]}
]
gold={
 'e01':{'kind':'answer','required':['과반수','3분의 2'],'forbidden_material':True},
 'e02':{'kind':'gap','required_target':'산','necessary':True},
 'e03':{'kind':'partial','required':['과반수'],'required_target':'긴급','necessary':True},
 'e04':{'kind':'answer','required':['12일'],'forbidden_material':True,'exclude_claim':['신규등록']},
 'e05':{'kind':'finish','allowed':['FINISH'],'sufficient':True},
 'e06':{'kind':'navigate','allowed':['READ','FOLLOW_CONNECTION','LOCATE'],'necessary':True},
 'e07':{'kind':'navigate','allowed':['SEARCH_BODY','RESEARCH'],'necessary':True},
 'e08':{'kind':'navigate','allowed':['LOCATE','FOLLOW_CONNECTION'],'necessary':True}
}
save(ART/'cases.json',cases);save(ART/'grading-only.json',gold)
