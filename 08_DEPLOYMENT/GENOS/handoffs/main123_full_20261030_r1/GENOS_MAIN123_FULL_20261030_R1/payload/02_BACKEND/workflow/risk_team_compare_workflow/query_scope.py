from copy import deepcopy
from .contracts import INTAKE, obj, text, array

POLICY='question-scoped-research-v2'

DEPENDENCY_SCOPE = (
    '조사 범위는 사용자 질문의 직접 요구와 그 답을 바꿀 수 있는 의존 원문으로 한정한다. '
    '의존 조사는 대상·업권·시점·의무·조건·예외·위임을 확인하지 않으면 요청의 답이 달라질 수 있을 때 수행한다. '
    '질문에 직접 쓰이지 않은 예외라도 적용 결과를 바꿀 수 있으면 연결 외규를 계속 탐색한다. '
    '단순 관련 주제나 참고 배경, 항목을 빠짐없이 채우려는 조사는 자동 추가 과제로 만들지 않는다. '
    '수치가 있다는 이유만으로 정의·분자·분모·산식을 새 요구로 늘리지 않는다. '
    '계산을 요청했거나 실제 원문상 그 의미를 확인해야 요청의 기준을 구별할 수 있을 때만 조사한다. '
    '이미 확보한 원문은 활용하고, 중요성이 불확실한 내용은 이유와 미확인 사항으로 보존한다. '
)


def enabled(ctx):
    return getattr(getattr(ctx,'definition',None),'manifest',{}).get('research_policy')==POLICY


def intake_contract():
    schema=deepcopy(INTAKE);issue=schema['properties']['issues']['items']
    issue['required']+=['work_type','requested_fields','requirements']
    issue['properties']['requested_fields']['minItems']=1
    issue['properties']['requirements']=array(obj(request_quote=text(),need=text()),1,8)
    return schema


def prepare(ctx):
    if not ctx.request['use_llm']:
        # Native use_llm=False performs scoped catalogue browsing, not semantic
        # query planning. Keep the request intact; do not fabricate short queries
        # or infer quantitative meaning from a word in its title.
        return {'issues':[{'id':'issue-1','label':ctx.request['question'],'numeric':False,'internal_task':ctx.request['question'],'external_task':ctx.request['question']}],
                'internal_queries':[],
                'external_queries':[],
                'scope_note':'모델 미사용: 질문 원문을 보존해 양쪽 허용 자료 목록을 조회합니다. 의미·수치·적용 판단은 수행하지 않아 numeric=false이며, 비수치 질문으로 판정했다는 뜻은 아닙니다.',
                'missing_user_facts':[],'facts':[]}
    def validate(value):
        if any(f['user_quote'] not in ctx.request['question'] for f in value['facts']):
            raise ValueError('user fact quote outside original question')
        ids=[i['id'] for i in value['issues']]
        if len(ids)!=len(set(ids)): raise ValueError('issue IDs must be unique')
        if enabled(ctx):
            for issue in value['issues']:
                if len(issue['requested_fields'])!=len(set(issue['requested_fields'])):
                    raise ValueError('comparison fields must be unique')
                if any(r['request_quote'] not in ctx.request['question'] for r in issue['requirements']):
                    raise ValueError('research requirement quote outside original question')
    policy=('요청한 업무를 해결하는 데 필요한 조사 요구를 requirements에 짧게 나누고 각각의 실제 질문 구절 request_quote를 연결한다. '
        '요구는 답해야 할 내용이며 예상 정답·조문·문서명을 만들지 않는다. work_type과 requested_fields를 반드시 직접 선택한다. '
        'numeric은 수치 포함 여부일 뿐 비율 계산 항목을 추가할 근거가 아니다. 분자·분모는 질문이 실제 비율의 구성이나 산식을 요구할 때만 선택한다. '
        '정의 차이는 definition, 해야 할 조치와 기준은 obligation, 적용 조건과 예외는 condition/exceptions 등으로 표현하고 불필요한 항목은 넣지 않는다. ') if enabled(ctx) else ''
    from .concepts import enabled as anchored
    scope_instruction=('먼저 질문과 관련된 내규를 찾기 위한 쟁점과 검색식을 만든다. '
        '이 단계의 external_task와 external_queries는 잠정 조사 목적이며 바로 실행하지 않는다. '
        '내규를 읽은 다음 개념·조항 범위를 정하고 그 내규에 근거해 외규 과제를 다시 만든다. ') if anchored(ctx) else (
        '질문을 공통 비교 항목과 내규 조사·외규 조사의 각각 독립적인 검색식으로 나눠라. 각 쪽 검색식은 해당 범위에서 답할 목적을 담아라. ')
    return ctx.model.decide('INTAKE', {'question':ctx.request['question'],'as_of':ctx.request['as_of']},
        intake_contract() if enabled(ctx) else INTAKE,policy+'work_type은 general/procedure/authority/ratio 중 선택한다. requested_fields에는 이 질문에서 필요한 비교 항목만 넣고, 정답 숫자나 조문은 만들지 않는다. '+scope_instruction+'회사·업권·기준일을 만들지 마라. '
        '각 issue의 internal_task는 내규에서 답할 질문만, external_task는 외규에서 답할 질문만 작성한다. 다른 쪽 조사와 양쪽 비교를 자식 과제로 넣지 않는다. 두 자식은 이 과제를 재해석하지 않고 그대로 수행한다. facts에는 사용자가 실제로 준 사실만 원문 user_quote와 기록한다. 법령 내용·메타데이터·추정 사실을 넣지 않는다. 일반 규정 질문은 facts=[]다. 양쪽의 같은 주제는 공통 비교 항목 하나로 묶어라. 질문에 없는 세부 항목을 별도 쟁점으로 늘리지 마라. 미확보 법령·내규는 사용자 사실 부족이 아니다. 수치·비율·산식 항목은 numeric=true.',validate)
