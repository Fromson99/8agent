"""Candidate-only patch; parent and working serving code stay immutable."""
from pathlib import Path
import shutil,subprocess
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0679/integrated';S=C/'snapshot';B=S/'02_BACKEND/semantic_runtime/legal_agent'
client='02_BACKEND/lawrag/research/experiment_client.py';p=S/client;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(R/client,p)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str((C/'candidate.json').relative_to(R)),'--target',client,'--upstream-state','present'],cwd=R,check=True)
s=p.read_text().replace('class ExperimentFormatError(ExperimentCallError):\n    """The provider replied, but the model output violated its contract."""', 'class ExperimentFormatError(ExperimentCallError):\n    """The provider replied, but the model output violated its contract."""\n    format_error = True')
s=s.replace("envelope={'status_code':response.status_code,'body_json':raw,'body_text':None,", "envelope={'status_code':response.status_code,'retry_after':response.headers.get('retry-after'),'body_json':raw,'body_text':None,")
p.write_text(s)
p=B/'gateway.py';s=p.read_text();old="""                        status=response['status_code']
                        raise TransportError('model provider rejected request',response=response,
                            retryable=status==429 and bool(getattr(adapter_error,'retryable',False)),
                            unknown=status>=500) from adapter_error"""
new="""                        status=response['status_code']
                        if 200 <= status < 300:
                            if getattr(adapter_error,'format_error',False) is True:
                                body=response.get('body_json') or {}
                                if body.get('model') != self.transport.binding['model']:
                                    raise ContractError('actual response model differs from pinned model') from adapter_error
                                error=ProposalError('model response is incomplete or invalid')
                                error.format_error=True
                                error.response=response
                                raise error from adapter_error
                            # Successful HTTP does not waive an adapter policy/binding rejection.
                            raise ContractError('adapter rejected successful response policy') from adapter_error
                        raise TransportError('model provider rejected request',response=response,
                            retryable=status==429 and bool(getattr(adapter_error,'retryable',False)),
                            unknown=status>=500) from adapter_error"""
assert old in s;s=s.replace(old,new)
old="""            except Exception as exc:
                self.repo.finish_attempt(ident, 'UNKNOWN', None, {'model': self.transport.binding['model'], 'usage': None, 'error': type(exc).__name__})"""
new="""            except ContractError as exc:
                self.repo.finish_attempt(ident, 'FAILED', getattr(exc, 'response', None),
                                         {'model': self.transport.binding['model'], 'usage': None, 'error': exc.code})
                raise
            except Exception as exc:
                self.repo.finish_attempt(ident, 'UNKNOWN', None, {'model': self.transport.binding['model'], 'usage': None, 'error': type(exc).__name__})"""
assert old in s;s=s.replace(old,new)
old="""                message = body['choices'][0]['message']
                content = message.get('content')"""
new="""                from .completion_contracts import enabled
                if enabled(self.profile) and body['choices'][0].get('finish_reason') in ('length', 'content_filter'):
                    raise ProposalError('model response did not complete normally')
                message = body['choices'][0]['message']
                content = message.get('content')"""
assert old in s;s=s.replace(old,new);p.write_text(s)
p=B/'completion_execution.py';s=p.read_text()
s=s.replace('사용자 사실 부족은 MISSING_FACT와 REQUEST_FACT다. 규칙은 조건부로 설명할 수 있다.', '''일반 규칙·정의·절차를 묻는 질문은 특정 회사나 사람의 실제 사실 확인을 요구하지 않는다. 사용자가 특정 사건에 적용해 달라고 요청한 경우에만, 그 결론을 바꾸는 미제공 사실을 MISSING_FACT와 REQUEST_FACT로 기록한다.
법령·시행령·다른 항의 내용이 없다는 것은 사용자 사실 부족이 아니다. MISSING_SOURCE/MISSING_SCOPE/UNREAD_SAVED/UNRESOLVED_REFERENCE 중 맞는 gap과 자료 조사 행동을 선택한다. MISSING_FACT의 material_id는 null이며 법령 목록·적용 범위·규정 내용은 사용자에게 묻지 않는다.
일반 규칙의 조건과 예외를 조건부로 설명하는 것만으로 요청을 충족하면, 실제 적용 사실이 주어지지 않았다는 이유로 gap을 만들지 않는다.
예: 모의 규정의 신고 기한 질문은 규정의 기한을 설명한다. 특정 신청이 기한을 넘겼는지 판단해 달라는 질문에서 신청일이 없으면 사용자 사실 부족이다. 위임된 세부 서류 목록의 원문이 없으면 원문 조사 부족이다.''')
s=s.replace("'찾을 수 있을 법한 질문으로 축소하지 않는다. issues에는 요청한 요구사항만 넣고 '", "'찾을 수 있을 법한 질문으로 축소하지 않는다. 일반 규칙 설명과 특정 사건에 대한 적용 판단을 목적에서 구분한다. 일반 규칙 질문에 특정 회사나 인물의 사실 확인 요구를 추가하지 않는다. issues에는 요청한 요구사항만 넣고 '")
p.write_text(s)
p=B/'completion_contracts.py';s=p.read_text();old="""        if gap['kind'] == 'MISSING_FACT' and gap['suggested_action'] != 'REQUEST_FACT':
            errors.append('Missing user facts require REQUEST_FACT, not source research.')"""
new="""        if gap['kind'] == 'MISSING_FACT':
            if gap['suggested_action'] != 'REQUEST_FACT':
                errors.append('Missing user facts require REQUEST_FACT, not source research.')
            if gap['material_id'] is not None:
                errors.append('MISSING_FACT cannot target a saved legal material. If a law/decree/list/scope is missing, select a source gap and source research action; only an unprovided fact needed for a requested case application is a user fact.')
        elif gap['suggested_action'] == 'REQUEST_FACT':
            errors.append('A legal source gap requires source research, not REQUEST_FACT.')"""
assert old in s;s=s.replace(old,new)
s=s.replace("errors.append(f'{row[\"issue_id\"]}: COVERED conflicts with a material gap')", "errors.append(f'{row[\"issue_id\"]}: COVERED conflicts with a material gap. Preserve the gap and mark PARTIAL/INSUFFICIENT; use NEEDS_INVESTIGATION for missing legal text. Do not mark a missing requested requirement non-material to evade repair.')")
p.write_text(s)
p=R/'06_TOOLS/EXPERIMENTS/adr_0679/run_case.py';s=p.read_text();s=s.replace("R/'02_BACKEND/lawrag/research/experiment_client.py'", "R/'02_BACKEND/lawrag/research/candidates/adr_0679/integrated/revisions/rev-001/snapshot/02_BACKEND/lawrag/research/experiment_client.py'");p.write_text(s)
print('Isolated adapter output classification, native finish boundary, typed gap rules and intent/assessment guidance implemented.')
