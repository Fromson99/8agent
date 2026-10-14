"""Preserve each field HTTP stack while installing the same model SSE parser."""
import ast


def rewrite(raw):
    text = raw.decode()
    start = text.index('    async def _stream_request(')
    tail = text.index('    def send_stream_once(', start)
    old = text[start:tail]
    if 'from .model_stream import ModelEventStream' in old:
        return raw
    asynchronous = 'response.aiter_lines()' in old
    indent = ' ' * (24 if asynchronous else 16)
    new = old.replace('        events, content, reasoning, arguments = [], [], [], []',
        '        from .model_stream import ModelEventStream\n'
        '        stream = ModelEventStream()\n        events = stream.events\n'
        '        content, reasoning, arguments = [], [], []')
    new = new.replace('        completed = False\n', '').replace(
        '        digest = hashlib.sha256()\n        size = 0\n',
        '        http_status = None\n        content_type = None\n')
    begin = new.index('        def partial():')
    finish = new.index('        try:\n' if asynchronous else '        def execute(', begin)
    new = new[:begin] + '''        def partial():
            return {'status_code': http_status, 'body_json': None, 'stream_events': list(events),
                    'body_sha256': stream.digest.hexdigest(), 'response_bytes': stream.size,
                    'stream_complete': False, 'content_type': content_type,
                    'stream_diagnostics': stream.diagnostics()}
''' + new[finish:]
    if not asynchronous:
        new = new.replace('nonlocal actual_model, usage, finish, call_id, call_name, completed, size',
            'nonlocal actual_model, usage, finish, call_id, call_name, http_status, content_type')
    at = new.index(' as response:\n') + len(' as response:\n')
    new = new[:at] + indent + 'http_status = response.status_code\n' + indent + \
        "content_type = response.headers.get('content-type', '').split(';', 1)[0].strip().lower()\n" + new[at:]
    new = new.replace('if response.status_code >= 400:', 'if response.status_code >= 300:')
    new = new.replace("if 'application/json' in response.headers.get('content-type', ''):",
                      "if content_type == 'application/json':")
    begin = new.index(indent + 'frame = []')
    end = new.index(indent + "    if event.get('model'):", begin)
    loop = ('async for event in stream.aiter_events(response.aiter_lines()):' if asynchronous
            else 'for event in stream.iter_events(response.iter_lines()):')
    new = new[:begin] + indent + "if content_type != 'text/event-stream':\n" + indent + \
        "    raise TransportError('unexpected model stream content type', unknown=True)\n" + indent + loop + '\n' + new[end:]
    new = new.replace(indent + "if not completed or finish is None:\n" + indent +
                      "    raise TransportError('model stream ended before completion', unknown=True)",
                      indent + 'stream.require_complete()')
    new = new.replace('response_bytes=size)', 'response_bytes=stream.size, **stream.diagnostics())')
    new = new.replace("'body_sha256': digest.hexdigest(), 'response_bytes': size,", 
                      "'body_sha256': stream.digest.hexdigest(), 'response_bytes': stream.size,")
    new = new.replace("'stream_events': events}",
                      "'stream_events': events, 'stream_complete': True,\n" + indent +
                      "        'content_type': content_type, 'stream_diagnostics': stream.diagnostics()}")
    assert 'completed' not in new and 'size += ' not in new and 'ModelEventStream' in new
    result = (text[:start] + new + text[tail:]).encode()
    ast.parse(result, feature_version=(3, 10))
    return result
