"""Readable projections of the inherited source annotations, equal in both arms.
These are research notes, not approved answers. Original structured values and
their precise source bindings remain in curated-source-values.json.
"""
from common import *
notes={
 'joint.threshold':'공동주관 보유비율은 금융투자회사와 그 이해관계인의 보유분을 합산해 검토한다. 기본 5%와 특례 10%의 적용 범위, 기업인수목적회사·규정상 외국기업 예외를 구분한다. 10% 특례의 제15조제4항제2호 단서 원문은 이 저장 묶음에 포함되지 않았다.',
 'joint.counting_scope':'주식등 보유수의 산정에 준용하는 대상은 자본시장과 금융투자업에 관한 법률 시행규칙 제14조 제1항이다. 제2항·제3항까지 자동으로 준용한다고 확대하지 않는다.',
 'joint.conversion':'주권은 주식 수, 신주인수권증권·증서는 대상 주식 수 또는 발행가액총액을 발행가격으로 나눈 수, 전환사채는 권면액을 전환으로 발행할 주식의 발행가격으로 나눈 수(1 미만 단수 제외), 신주인수권부사채는 신주인수권 대상 주식 수로 확인한다. 교환사채·파생결합증권·증권예탁증권은 각각 교환대상·기초자산·기초 증권의 수를 확인한다. 공동주관 보유비율의 전체 분모식은 이 저장 묶음만으로 확정하지 않는다.',
 'joint.exclusion':'코스닥시장 상장규정 제13조제5항제1호에 따라 취득한 주식과 지정자문인 계약의 효력이 유지되는 상태에서 취득한 코넥스 주식은 인수규정 제6조제1항의 보유비율 산정에서 보유한 것으로 보지 않는 범위를 확인한다. 이 보유제외를 분모 자동 차감으로 확대하지 않는다.',
 'joint.lookthrough':'중소기업창업투자조합·신기술사업투자조합·한국벤처투자조합 및 해당 환매금지 사모집합투자기구를 통한 간접보유는 출자·투자비율에 조합등의 보유 주식등을 곱하는 방식과 적용 대상을 확인한다. 조합등이라는 이유만으로 보유비율 검토 전체가 면제되는 것으로 처리하지 않는다.',
 'joint.commitment':'확약서에 의한 조건부 보유제외는 IPO의 상장예비심사신청일 전 취득과 비상장 공모의 대표주관계약체결일 전 취득을 구분한다. 예탁결제원 의무보유등록 또는 해당 보호예수 확약서의 협회 제출, 5영업일 제출·6개월 등록·10영업일 증명 관련 요건을 각각 원문에서 확인한다.',
 'listing.quantities':'상장주선인 의무인수의 수량·기간은 대상별로 구분한다. 국내 일반기업은 3%·10억원 한도·3개월, 국내 신속이전은 5%·25억원 한도·6개월, 외국 혁신기업은 5%·50억원 한도·1년, 그 밖의 외국기업은 5%·25억원 한도·1년을 확인한다. 국내 신속이전 중 제31조제1항제3호마목·바목의 1년 특례와 6개월 후 매월 최초 취득수량 5%까지 매각 규정을 확인한다. 외국기업에도 6개월 후 매월 최초 취득수량 5%까지 매각 범위가 있고 국내소재외국지주회사는 외국기업 분기로 분류한다. 기간의 기준은 상장일, 취득가격은 모집·매출가격과 같은 가격이다.',
 'listing.extension':'일반 국내기업의 보유기간 연장에서는 현재 상장신청인이 혁신기술기업이고 상장주선인이 시행세칙 제15조제5항 사유에 해당하는 두 조건을 모두 확인한다. 이 AND 조건에 따른 6개월 연장과 일반적인 3개월을 구분한다.',
 'listing.past_event':'주선인의 연장 사유는 현재 상장예비심사 신청일 기준 최근 3년 안에 상장을 주선한 기술성장기업이 그 기업의 상장 이후 2년 안에 투자주의 환기종목 또는 관리종목으로 지정되거나, 형식적 상장폐지 또는 상장적격성 실질심사에 따른 상장폐지 사유가 발생했는지 확인한다.',
 'listing.acquisition':'의무인수 주식의 취득방법은 사모발행주식 취득이고, 상장예비심사 신청일부터 신규상장 신청일까지의 취득 시기를 확인한다. 취득 수량에는 미청약 잔여수량을 상장주선인이 취득한 수량이 포함되는지 확인한다.',
 'listing.exemption':'대형법인(외국기업·특정 신속이전기업 제외)과 적격 해외증권시장 상장 후 3년이 지난 외국기업 등의 경우 거래소가 의무인수 규정을 적용하지 않을 수 있는 범위를 확인한다. 이를 모든 경우의 자동 면제로 단정하지 않는다.'
}
checks={c['id']:c for p in read(DES/'curated-source-values.json')['packs'] for c in p['checks']}
assert set(notes)==set(checks)
put(DES/'display-notes.json',{'schema_version':'source-review-note-projection-v1','both_arms_identical':True,
    'source_annotations_sha256':sha(DES/'curated-source-values.json'),'expert_approved':False,
    'notes':{k:{'text':v,'source_check_sha256':hashlib.sha256(json.dumps(checks[k],ensure_ascii=False,sort_keys=True).encode()).hexdigest()} for k,v in notes.items()}})
p=Path(__file__).with_name('e2e.py');s=p.read_text()
old="labels=[c['id']+': '+json.dumps(c['value'],ensure_ascii=False,separators=(',',':')) for c in note['source_checks']]"
new="labels=[read(DES/'display-notes.json')['notes'][c['id']]['text'] for c in note['source_checks']]"
assert s.count(old)==1;s=s.replace(old,new);p.write_text(s)
criteria=read(DES/'criteria.json');criteria['controls']+=' Both arms use the same readable projection of inherited structured source annotations; projection source checks and text are frozen.'
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['design']['execution']=criteria
for arm in m['design']['arms']:arm['controls']=criteria['controls']
put(ADR/'실험/manifest.json',m)
print('11 source note projections fixed identically in both arms')
