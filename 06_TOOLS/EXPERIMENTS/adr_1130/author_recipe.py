from common import *
data=read(ART/'build-input.json');originals={s['id']:s for s in data['originals']};components=[]
def part(id,text,sources,requires=()):
 components.append({'id':id,'text':text,'requires':list(requires),'basis':[{'source':s,'quote':originals[s]['text']} for s in sources]});return id
part('scope','최대주주등의 특수관계인이 해당 법인의 주식등을 증여받거나 취득한 경우를 대상으로 한다. 최대주주등에는 제22조제2항에 따른 최대주주·최대출자자와, 특수관계인 보유분을 합하여 내국법인의 발행주식총수 또는 출자총액의 25% 이상을 소유하는 해당 주주등이 포함된다.',['P1','P2','P3','P23'])
part('acquisition','취득 경로는 다음 중 하나이다: 최대주주등으로부터 해당 법인의 주식등을 증여받거나 유상 취득한 경우, 또는 유상 취득일 전 3년 이내에 최대주주등으로부터 증여받은 재산으로 최대주주등이 아닌 자로부터 해당 법인의 주식등을 취득한 경우.',['P4','P5','P6'])
part('listing','증여·취득일부터 5년 이내에 유가증권시장 또는 코스닥시장에 상장됨에 따라 주식등의 가액이 증가한 경우이다.',['P1','P19'])
part('gain_condition','당초 증여세 과세가액 또는 취득가액을 초과하는 이익이 발생해야 한다. 제2항제2호에 따른 증여재산을 사용한 취득의 가액 처리 범위는 해당 원문을 함께 따른다.',['P1'])
part('date','상장일은 증권시장에서 최초로 매매거래를 시작한 날이다. 정산기준일은 상장일부터 3개월이 되는 날이다. 그 전에 사망·증여·양도한 경우 해당 사망일·증여일·양도일을 기준으로 한다.',['P7','P9'])
part('value','평가가액 = 정산기준일 현재 1주당 평가가액(법 제63조에 따른 평가). 최초가액 = 증여일 현재 1주당 증여세 과세가액 또는 취득일 현재 1주당 취득가액. 기업가치 증가분 = 1주당 기업가치의 실질적인 증가로 인한 이익.',['P16','P17','P18'],['date'])
part('enterprise','기업가치 증가분 = (증여·취득일이 속한 사업연도 개시일부터 상장일 전일까지의 1주당 순손익액 합계 ÷ 해당 기간 월수) × 증여·취득일부터 정산기준일까지의 월수. 각 1개월 미만 월수는 1개월로 본다. 납세자 제시 서류로 확인하며, 결손금 등으로 이 방식이 불합리한 경우 제55조에 따라 계산한 1주당 순자산가액 증가분으로 계산할 수 있다.',['P24','P25','P26'],['date'])
part('gain_formula','이익 = (정산기준일 현재 1주당 평가가액 − 증여·취득일 현재 1주당 최초가액 − 1주당 기업가치 증가분) × 증여받거나 유상 취득한 주식등의 수.',['P15','P16','P17','P18'],['value','enterprise'])
part('threshold','기준금액 = 다음 두 금액 중 적은 금액: ① (1주당 최초가액 + 1주당 기업가치 증가분) × 증여받거나 유상 취득한 주식등의 수 × 30%, ② 3억원.',['P20','P21','P22'],['value','enterprise'])
part('above','산정된 이익이 기준금액 미만인 제외 경우에 해당하지 않아야 한다.',['P1','P20','P21','P22'],['gain_formula','threshold'])
part('below','산정된 이익이 위 기준금액보다 작은 경우이다.',['P1','P20','P21','P22'],['gain_formula','threshold'])
part('normal_result','위 성립 요건을 충족한 이익에 상당하는 금액을 이익을 얻은 자의 증여재산가액으로 한다. 제1항에 따른 이익을 당초 증여세 과세가액에 가산하여 증여세 과세표준과 세액을 정산한다. 증여받은 재산으로 취득한 경우의 당초 과세가액은 그 증여받은 재산의 증여세 과세가액이다.',['P1','P8'])
part('excluded_result','이익이 기준금액 미만인 경우에는 법 제41조의3제1항의 적용에서 제외한다. 다른 과세 규정의 적용까지 배제한다는 뜻으로 확대하지 않는다.',['P1'])
part('refund_scope','법 제41조의3제4항 단서의 환급을 검토하는 경우로서, 정산기준일 현재 주식등의 가액이 당초 증여세 과세가액보다 적어야 한다.',['P8'],['date'])
part('refund_threshold','그 차액이 대통령령으로 정하는 기준 이상이어야 한다. 시행령 제31조의3제6항은 이를 제1항에 따라 계산한 금액이 제3항의 기준금액 이상인 경우로 정한다. 단순히 상장이익이 기준금액 미만이라는 사유와 구분한다.',['P8','P27'],['gain_formula','threshold'])
part('refund_result','위 환급 조건에 해당하면 그 차액에 상당하는 증여세액을 환급받을 수 있다. 여기서 증여세액은 증여받을 때 납부한 당초의 증여세액을 말한다.',['P8'])
part('mixed_condition','증여받은 재산으로 최대주주등이 아닌 자에게서 주식을 취득하는 경로를 적용할 때, 증여재산과 다른 재산이 섞여 있어 증여재산으로 취득한 것인지 불분명한 경우이다.',['P6','P10'])
part('mixed_result','그 증여받은 재산으로 주식등을 취득한 것으로 추정한다. 담보 차입 취득에 관한 별도의 간주 문구와 구분한다.',['P10'])
part('loan_condition','증여받은 재산을 담보로 한 차입금으로 주식등을 취득한 경우이다.',['P10'])
part('loan_result','증여받은 재산으로 취득한 것으로 본다. 혼재재산의 불분명한 취득에 관한 추정 문구와 구분한다.',['P10'])
part('limits','이 묶음 밖의 법 제63조 평가 방법, 제22조제2항의 세부 정의, 관련 서류 및 순자산가액 산정 세부는 별도 원문 확인 대상이다. 현재 경로는 사건 사실 충족이나 수치 계산 결과를 확정하지 않는다.',['P2','P16','P24'])
part('separate_routes','가액 하락 환급은 별도 조건을 가진 경로이다. 신주·전환사채·부정행위·무상주 관련 확장은 이번 5개 시나리오에 펼치지 않았으며 해당 업무에는 추가 경로가 필요하다.',['P8','P11','P12','P13','P28'])
def path(id,title,use,conditions,calculations,outcomes,notes):return dict(id=id,title=title,business_use=use,conditions=conditions,calculations=calculations,outcomes=outcomes,notes=notes)
recipe={'version':'ontology-scenarios-v1','bundle_id':data['concept']['label'],'authority':'EXPERIMENT_SOURCE_AUTHORED_NOT_APPROVED','authoring':{'by':'Codex explicit source recipe','basis':'Originals from1124; known failures informed this in-sample implementation, no reference answer input','automatic_extraction':False,'human_approved':False,'source_input_sha256':sha(ART/'build-input.json')},'components':components,'paths':[
 path('PATH1','시나리오 1 — 상장차익 증여의제 성립과 정산','상장차익 증여의제의 성립 요건과 정상 정산을 검토하는 업무',['scope','acquisition','listing','gain_condition','above'],['gain_formula','threshold'],['normal_result'],['limits','separate_routes']),
 path('PATH2','시나리오 2 — 기준금액 미달에 따른 제외','상장 이익이 기준금액보다 작은 경우의 제외와 기준금액 산정',['scope','acquisition','listing','gain_condition','below'],['gain_formula','threshold'],['excluded_result'],['limits']),
 path('PATH3','시나리오 3 — 가액 하락에 따른 환급','정산기준일 가액 하락에 따른 환급 조건·연결 계산 기준',['refund_scope','refund_threshold'],['gain_formula','threshold'],['refund_result'],['limits']),
 path('PATH4','시나리오 4 — 혼재재산 취득의 추정','증여재산과 다른 재산이 섞인 자금으로 취득했을 때의 처리',['mixed_condition'],[],['mixed_result'],[]),
 path('PATH5','시나리오 5 — 담보 차입 취득의 간주','증여재산을 담보로 차입한 자금으로 주식을 취득했을 때의 처리',['loan_condition'],[],['loan_result'],[])], 'unused_components':{}}
put(ART/'recipe.json',recipe)
r=read(ART/'rubric.json')
for row in r['cases'].values():
 for k in ('required_paths','forbidden_paths'):
  if k in row:row[k]=[v.replace('S','PATH') for v in row[k]]
put(ART/'rubric.json',r)
print('Authored',len(components),'components,',len(recipe['paths']),'paths; no compiled output yet')
