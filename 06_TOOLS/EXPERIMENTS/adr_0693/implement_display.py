from pathlib import Path
R=Path(__file__).resolve().parents[3]
S=R/'02_BACKEND/lawrag/research/candidates/adr_0693/safe-display/snapshot'
def edit(path,old,new):
 p=S/path;t=p.read_text();assert old in t,(path,old[:80]);p.write_text(t.replace(old,new))
# Keep standalone workflow self-contained. Backend consumers import these pure helpers
# through their existing, release-bound views() loader.
p='08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
t=(S/p).read_text();lo=t.index('def render_error(');hi=t.index('\n\ndef render(',lo)
t=t[:lo]+'''DISPLAY_POLICY_REVISION = 'public-display-v1'


def public_failure(request_id=None):
    ident = str(request_id or '')
    if not re.fullmatch(r'[A-Za-z0-9_:.\\-]{1,128}', ident):
        ident = uuid.uuid4().hex
    return {'request_id': ident, 'answer_status': 'failed',
            'message': '답변을 완료하지 못했습니다.',
            'display_policy_revision': DISPLAY_POLICY_REVISION}


def public_event(event):
    """Only activity and committed judgment are public; diagnostics stay in logs."""
    if not isinstance(event, dict) or event.get('schema_version') != 'rag-progress-v1':
        return None
    basis = event.get('basis') or {}
    if basis.get('detail_mode') == 'full_error':
        return None
    if basis.get('kind') in {'ATTEMPT_FINISHED', 'COMPLETION_ASSESSMENT_REJECTED',
            'MODEL_OUTPUT_INVALID', 'LAW_DECISION_REJECTED', 'SOURCE_INVESTIGATION_INCOMPLETE',
            'REFERENCE_NAVIGATION_STATUS', 'UNIT_CANDIDATE_ACQUISITION_STOPPED'}:
        return None
    if basis.get('kind') == 'OBS_EVENT' and basis.get('name') not in {
            'request.started', 'request.finished'}:
        return None
    if basis.get('detail_mode') == 'judgment' and (
            basis.get('kind') != 'CASE_JUDGMENT_ACCEPTED' or basis.get('state') not in {'COMPLETED', 'REBOUND'}):
        return None
    if event.get('kind') not in {'phase','candidate','reading','read_complete','selected',
            'revised','review','decision','model_wait','heartbeat','overflow'}:
        return None
    # Do not forward caller-added debug fields, model payloads or exception objects.
    out = {k:event[k] for k in ('schema_version','request_id','run_id','seq','kind','label','elapsed_ms','count','details') if k in event}
    out['basis'] = {k:basis[k] for k in ('kind','name','journal_seq','stage','state','detail_mode','judgment_revision','payload_hash') if k in basis}
    out['display_policy_revision'] = DISPLAY_POLICY_REVISION
    return out


def public_response(body, *, status=200, request_id=None):
    if not isinstance(body, dict):
        return public_failure(request_id)
    if status >= 400 or (isinstance(body.get('_gateway_status'), int) and body['_gateway_status'] >= 400):
        return public_failure(request_id or body.get('request_id'))
    # Legacy raw diagnostics may be present in successful, recovered responses.
    # Domain reason/limitations are produced separately from these journal records.
    private = {'diagnostics','failure_diagnostics','error_diagnostics','traceback','error',
               'error_type','error_message','rejected_decisions','rejected_assessment',
               'repair_feedback','normalization','retry_history','http_error_diagnostics',
               'failure','blockers','observations','structure_recovery'}
    def project(value):
        if isinstance(value, dict):
            return {k:project(v) for k,v in value.items() if k not in private}
        if isinstance(value, list): return [project(v) for v in value]
        return value
    return project(body)


def render_error(body, *, question=''):
    """A terminal failure is visible without exposing diagnostic content."""
    safe = public_failure(body.get('request_id') if isinstance(body, dict) else None)
    return safe['message'] + '\\n\\n조회 번호: ' + safe['request_id']
''' +t[hi:];(S/p).write_text(t)
edit(p,"    async def progress(self, event):\n        if not self.show_progress", "    async def progress(self, event):\n        event = public_event(event)\n        if event is None:\n            return\n        if not self.show_progress")
edit(p,"        'request_id': request_id,\n        'response_sha256'", "        'request_id': request_id,\n        'display_policy_revision': DISPLAY_POLICY_REVISION,\n        'response_sha256'")
edit(p,"    if (value.get('schema_version') != 'genos-workflow-display-v1'", "    if (value.get('display_policy_revision') != DISPLAY_POLICY_REVISION\n            or value.get('schema_version') != 'genos-workflow-display-v1'")
edit(p,"            'schema_version', 'producer', 'response_sha256', 'content_sha256')", "            'schema_version', 'producer', 'response_sha256', 'content_sha256', 'display_policy_revision')")
edit(p,'"http_error_diagnostics": error_diagnostics,\n            "code_serving_transport"','"code_serving_transport"')
edit(p,'"failure_kind": "client_exception",\n            "error_type": type(exc).__name__,','"failure_kind": "client_exception",')
edit(p,'"answer_status": "incomplete" if failure.get("code")=="SOURCE_INVESTIGATION_INCOMPLETE" else "unavailable" if failure.get("code")=="MODEL_UPSTREAM_UNAVAILABLE" else "failed",','"answer_status": "failed",')
edit(p,"    status = body.get(\"_gateway_status\")\n    if isinstance(status, int) and status >= 400:","    status = body.get(\"_gateway_status\")\n    if body.get('answer_status') == 'failed' or isinstance(status, int) and status >= 400:")
edit(p,"failure = {'text':'AD_MODE_CHECK_FAILED: '+_redact_http_error(str(exc),question),'answer_status':'failed','request_id':request_id}","failure = {'text':render_error({'request_id':request_id}),'answer_status':'failed','request_id':request_id}")
# Back-end API records the original before applying public response policy.
p='02_BACKEND/semantic_runtime/app.py';t=(S/p).read_text();lo=t.index('def legal_error_payload(');hi=t.index('\n\ndef external_documents',lo)
t=t[:lo]+'''def legal_error_payload(exc, request_id=None):
    from .legal_agent.investigation_diagnostics import exception_diagnostics
    from .chat_adapter import views
    request_id = request_id or obs._CONTEXT.get().get('request_id')
    public = views().public_failure(request_id)
    obs.event(log, 'request.error', level=40, request_id=public['request_id'],
              error_type=type(exc).__name__, failure_diagnostics=exception_diagnostics(exc))
    return public
'''+t[hi:];(S/p).write_text(t)
edit(p,"return JSONResponse(status_code=404,content={'detail':'요청한 데이터 좌표가 없습니다.'})","return JSONResponse(status_code=404,content=legal_error_payload(exc))")
# Progress producer and each consumer share the same public allowlist.
p='02_BACKEND/semantic_runtime/progress.py'
edit(p,'        try:\n            self.sink(event)','        from .chat_adapter import views\n        event = views().public_event(event)\n        if event is None:\n            return\n        try:\n            self.sink(event)')
edit(p,'        name = record.getMessage()\n        if record.levelno',"        name = record.getMessage()\n        if record.levelno >= logging.ERROR or name in {'model.output.invalid', 'model.attempt.failed'}:\n            return  # Original record remains in the diagnostic handlers.\n        if record.levelno")
edit(p,"if fields.get('ok') is False:label='요청 처리 실패 · 오류 로그를 확인해 주세요'","if fields.get('ok') is False:return")
# Accepted events cannot be replayed from an earlier stage revision.
edit(p,'        self.seen_reads = set()','        self.seen_reads = set()\n        self.judgment_sequences = {}')
edit(p,'        payload = json.loads(row[0])\n        actual = hashlib.sha256',"        newest = db.execute(\"SELECT MAX(created_seq) FROM entity_version WHERE kind='case_stage' AND entity_id=?\", (\"case:\" + stage,)).fetchone()[0]\n        if seq != newest or seq <= self.judgment_sequences.get(stage, -1):\n            return\n        payload = json.loads(row[0])\n        actual = hashlib.sha256")
edit(p,'        rebound = isinstance(event.get("origin"), dict)','        self.judgment_sequences[stage] = seq\n        rebound = isinstance(event.get("origin"), dict)')
edit(p,'"detail_mode": "judgment"}','"detail_mode": "judgment", "judgment_revision": seq, "payload_hash": actual}')
p='02_BACKEND/semantic_runtime/chat_adapter.py'
edit(p,'        def sink(event):\n            if len(events)',"        def sink(event):\n            event = view.public_event(event)\n            if event is None:return\n            if len(events)")
edit(p,"answer_status='failed',error_type=type(exc).__name__)","answer_status='failed')")
# Do not echo arbitrary input diagnostics/debug in the response envelope.
edit(p,"return {'code':0,'data':{**public_fields(data),**result}}","return {'code':0,'data':result}")
p='main_workflow.py'
edit(p,'    def sink(event):\n        if len(events)',"    def sink(event):\n        event = views().public_event(event)\n        if event is None:return\n        if len(events)")
edit(p,"    body = view.unwrap(response)\n    body.pop('workflow_display', None)","    raw_body = view.unwrap(response)\n    if response.get('status', 200) >= 400:\n        from semantic_runtime import observability as obs\n        obs.event(obs.get_logger('workflow'), 'workflow.backend.failed', level=40,\n            request_id=data['request_id'], failure_diagnostics=raw_body)\n    body = view.public_response(raw_body, status=response.get('status', 200), request_id=data['request_id'])\n    body.pop('workflow_display', None)")
edit(p,"return {**response, 'body': {**response['body'], 'workflow_display': rendered}}","return {**response, 'body': {**{k:v for k,v in body.items() if k != '_gateway_status'}, 'workflow_display': rendered}}")
p='08_DEPLOYMENT/GENOS/stream_app.py'
edit(p,'        def sink(value):\n            # The separate',"        def sink(value):\n            from semantic_runtime.chat_adapter import views\n            value = views().public_event(value)\n            if value is None:return\n            # The separate")
edit(p,"            if not detached.is_set():\n                await put_required('result', result)","            if isinstance(result, dict) and 'body' in result:\n                from semantic_runtime.chat_adapter import views\n                result = {**result, 'body': views().public_response(result['body'],\n                    status=result.get('status', 200), request_id=data['request_id'])}\n            if not detached.is_set():\n                await put_required('result', result)")
# Root service logs/reports raw result, then projects only failures at its boundary.
p='service.py'
edit(p,'    if report:\n        report.complete(result)\n    return result',"    if report:\n        report.complete(result)\n    if isinstance(body, dict) and status >= 400:\n        from semantic_runtime.chat_adapter import views\n        obs.event(log, 'request.failure_retained', level=logging.ERROR,\n                  request_id=request_id, failure_diagnostics=body)\n        result = {**result, 'body': views().public_response(body, status=status, request_id=request_id)}\n    return result")
print('Display boundaries implemented in isolated snapshot')
