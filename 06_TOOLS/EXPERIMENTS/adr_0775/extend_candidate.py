from pathlib import Path
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0775/guidance/snapshot'
def change(p,old,new):
 s=p.read_text();assert s.count(old)==1,(p,old[:90],s.count(old));p.write_text(s.replace(old,new,1))
p=C/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
change(p,"DISPLAY_POLICY_REVISION = 'public-display-v3'","DISPLAY_POLICY_REVISION = 'public-display-v4'")
change(p,"    statuses = [status, body.get('_gateway_status'), body.get('http_status')]", """    statuses = [status, body.get('_gateway_status'), body.get('http_status')]
    nested = body.get('error')
    if isinstance(nested, dict):
        types.extend([nested.get('type'), nested.get('error_type')])
        codes.append(nested.get('code'))""")
change(p,"        exc = exc.__cause__ or (reason if isinstance(reason, BaseException) else None)","        exc = exc.__cause__ or (reason if isinstance(reason, BaseException) else None) or (None if exc.__suppress_context__ else exc.__context__)")
change(p,"    if reason == 'technical' and isinstance(marker, str)","    if reason == 'budget' or 'BUDGET_EXHAUSTED' in codes:\n        return 'budget', 'limit'\n    if reason == 'technical' and isinstance(marker, str)")
change(p,"    message = REVIEW_INCOMPLETE_MESSAGE if reason == 'review_incomplete' else (\n        '현재 충분한 법률 검토를 하지 못했습니다. 잠시 후 다시 요청해 주세요. ('\n        + ('처리 오류' if marker == 'internal' else marker) + ')')", """    guidance = {
        '401': '로그인 상태와 접근 권한을 확인해 주세요.',
        '403': '이 자료와 기능에 대한 접근 권한을 확인해 주세요.',
        '409': '요청 상태가 변경되었거나 처리 중입니다. 최신 대화 상태를 확인해 주세요.',
        '413': '질문이나 첨부 자료의 분량을 줄여 다시 요청해 주세요.',
        'limit': '검토 가능한 처리 한도에 도달했습니다. 법률 쟁점을 나누어 질문해 주세요.',
    }.get(marker, '잠시 후 다시 요청해 주세요.')
    message = REVIEW_INCOMPLETE_MESSAGE if reason == 'review_incomplete' else (
        '현재 충분한 법률 검토를 하지 못했습니다. ' + guidance + ' ('
        + ('처리 오류' if marker == 'internal' else marker) + ')')""")
# Errors projected upstream sometimes retain the older error status spelling.
s=p.read_text().replace("body.get('answer_status') == 'failed'", "body.get('answer_status') in {'failed', 'error'}").replace('body.get("answer_status") == "failed"','body.get("answer_status") in {"failed", "error"}')
p.write_text(s)
change(p,"        except (TypeError, ValueError):\n            return {}\n    if not isinstance(payload, dict):\n        return {}", "        except (TypeError, ValueError):\n            return public_failure(status=502)\n    if not isinstance(payload, dict):\n        return public_failure(status=502)")
change(p,'    for key in ("body", "data", "result"):\n        if key in payload', '    for key in ("body", "data", "result"):\n        if key in payload and not isinstance(payload[key], (dict, str)):\n            return public_failure(payload.get("request_id"), status=502)\n        if key in payload')
change(p,'    return dict(payload)\n\n\ndef _request_body', '    result = dict(payload)\n    if type(payload.get("status")) is int and payload["status"] >= 400:\n        result["_gateway_status"] = payload["status"]\n    return result\n\n\ndef _request_body')
# Do not continue into legal RAG when the preflight returned a failed envelope.
change(p,"            if probe.get('response_schema')=='ad-mode-v1':", """            if (probe.get('answer_status') in {'failed','error'}
                    or isinstance(probe.get('_gateway_status'),int) and probe['_gateway_status'] >= 400):
                result = {'text':render_error({**probe,'request_id':request_id}),
                          'answer_status':'failed','request_id':request_id}
                await display.finish(result['text'])
                return result
            if probe.get('response_schema')=='ad-mode-v1':""")
# Terminal display failure must still close the existing socket stream once.
s=p.read_text();start=s.index('    server_display = _bound_workflow_display(body, request_id)',s.index('async def _run_once'))
end=s.index('\n\n\nasync def run(data):',start);section=s[start:end]
s=s[:start]+'    try:\n'+''.join('    '+line if line.strip() else line for line in section.splitlines(True))+'''\n    except Exception as exc:
        _log_event('workflow.display.failed', level='ERROR', request_id=request_id,
                   error_type=type(exc).__name__, traceback=traceback.format_exc())
        result = {'text':render_error({'request_id':request_id},exc=exc),
                  'answer_status':'failed','request_id':request_id}
        await display.finish(result['text'])
        return result
'''+s[end:];p.write_text(s)
change(p,'    return await _run_once(data)', '''    try:
        return await _run_once(data)
    except Exception as exc:
        ident = data.get('request_id') if isinstance(data,dict) else None
        safe = public_failure(ident,exc=exc)
        _log_event('workflow.entry.failed', level='ERROR', request_id=safe['request_id'],
                   error_type=type(exc).__name__, traceback=traceback.format_exc())
        return {'text':render_error(safe),'answer_status':'failed','request_id':safe['request_id']}''')
p=C/'02_BACKEND/semantic_runtime/chat_adapter.py'
change(p,"        return {'code':0,'data':{**result,'answer_status':'error','text':'AD_GATEWAY: existing platform gateway access required.'}}", "        return {'code':0,'data':{**result,'answer_status':'failed','text':view.render_error({'request_id':ident,'_gateway_status':403})}}")
s=p.read_text();start=s.index('    if ad_allowed:\n');end=s.index('        operation=str(data.get',start);pre=s[start:s.index('    started=time.perf_counter()',start)]
s=s[:start]+s[s.index('    started=time.perf_counter()',start):end]+''.join('    '+line if line.strip() else line for line in pre.splitlines(True))+s[end:];p.write_text(s)
change(p,"            ad=view.unwrap(probe)\n            if ad.get('response_schema')", """            ad=view.unwrap(probe)
            if (ad.get('answer_status') in {'failed','error'}
                    or isinstance(ad.get('_gateway_status'),int) and ad['_gateway_status'] >= 400):
                return {'code':0,'data':{**result,'answer_status':'failed',
                    'text':view.render_error({**ad,'request_id':ident})}}
            if ad.get('response_schema')""")
print(C)
