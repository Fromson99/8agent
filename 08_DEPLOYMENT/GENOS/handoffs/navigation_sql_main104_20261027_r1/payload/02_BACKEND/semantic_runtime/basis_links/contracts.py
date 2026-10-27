"""System-owned review and exact-source contracts, independent of model schemas."""
from datetime import datetime, timezone, date
import hashlib
import json


def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def digest(value):return hashlib.sha256(encoded(value).encode()).hexdigest()
def text_hash(value):return hashlib.sha256(value.encode()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()


class BasisError(ValueError):
    def __init__(self,code,message,status=422):
        super().__init__(message);self.code=code;self.http_status=status


class BasisUnavailable(BasisError):
    def __init__(self,message='근거 원장 연결을 확인할 수 없습니다. 같은 요청 ID로 상태를 확인해 주세요.'):
        super().__init__('BASIS_STORAGE_UNAVAILABLE',message,503)


def require(condition,code,message,status=422):
    if not condition:raise BasisError(code,message,status)


def principal(value,review=False):
    require(isinstance(value,dict),'BASIS_IDENTITY','인증된 실행 주체가 필요합니다.',403)
    require(all(isinstance(value.get(k),str) and value[k].strip() for k in ('user_id','team_id')),
            'BASIS_IDENTITY','인증된 사용자·팀이 필요합니다.',403)
    require(isinstance(value.get('document_ids'),list),'BASIS_SCOPE','문서 권한 범위가 필요합니다.',403)
    if review:require(value.get('basis_review') is True,'BASIS_REVIEW_DENIED','근거 관계 검토 권한이 필요합니다.',403)
    return value


def request_id(value):
    require(isinstance(value,str) and 0<len(value)<=256,'BASIS_REQUEST_ID','안정적인 request_id가 필요합니다.')
    return value


def as_of(value):
    if value is not None:
        try:require(date.fromisoformat(value).isoformat()==value,'BASIS_DATE','기준일 형식이 잘못되었습니다.')
        except (ValueError,TypeError) as exc:raise BasisError('BASIS_DATE','기준일은 YYYY-MM-DD입니다.') from exc
    return value


def visible(link,who):
    if link['team_id']!=who['team_id']:return False
    ends=[*link['internal'],*link['external']]
    return {e['document_id'] for e in ends}<=set(who['document_ids'])


def view_hash(link,binding):
    return digest({'link':link,'binding':binding})
