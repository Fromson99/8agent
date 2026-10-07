"""One scoped format recovery, with all physical requests kept by ExperimentClient."""
from lawrag.research.experiment_client import ExperimentCallError,ExperimentFormatError

def generate(client,system,data,schema,phase,receipt):
 try:return client.generate(system,data,schema,phase=phase)
 except ExperimentCallError as exc:
  raw=((getattr(exc,'response',None) or {}).get('body_json') or {})
  finishes=[c.get('finish_reason') for c in raw.get('choices',[])]
  recoverable=(isinstance(exc,ExperimentFormatError) and finishes==['length']) or str(exc).startswith(('output is not complete JSON','schema:'))
  if not recoverable:raise
  receipt({'phase':phase,'error_type':type(exc).__name__,'reason':str(exc)[:400],'finish_reasons':finishes,'repair_limit':1})
  return client.generate(system+'\n직전 응답은 출력 한도 또는 JSON 스키마 위반으로 수락되지 않았다. 같은 입력으로 짧고 완전한 JSON 하나를 출력한다. 검색어는 최대4개다. 변경하지 않는 필드는 null, 불필요한 목록은 생성하지 않는다. 원문 인용과 의미 검사는 유지한다. 오류: '+str(exc)[:300],data,schema,phase=phase+'-format-repair')
