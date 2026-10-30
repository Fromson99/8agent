"""GENOS model SSE framing shared by synchronous and asynchronous transports.

[DONE] closes the transport. JSON/schema/claim validation remains in Gateway;
neither valid JSON, a usage event nor EOF alone certifies a completed answer.
"""
import hashlib
import json

from .errors import TransportError

REVISION = 'genos-model-stream-20261013-r1'


class ModelEventStream:
    def __init__(self):
        self.events = []
        self.frame = []
        self.event_type = ''
        self.done = False
        self.eof = False
        self.trailing_frame_seen = False
        self.trailing_frame = False
        self.size = 0
        self.digest = hashlib.sha256()
        self.finish_reason = None

    def diagnostics(self):
        return {'revision': REVISION, 'done_marker': self.done,
                'eof_received': self.eof, 'trailing_frame_parsed': self.trailing_frame,
                'trailing_frame_seen': self.trailing_frame_seen,
                'pending_frame_lines': len(self.frame), 'finish_reason': self.finish_reason,
                'event_count': len(self.events)}

    def _decode(self):
        raw = '\n'.join(self.frame)
        event_type = self.event_type
        self.frame = []
        self.event_type = ''
        if event_type == 'error':
            raise TransportError('model stream returned an error', unknown=True)
        if raw.strip() == '[DONE]':
            self.done = True
            return None
        event = json.loads(raw)
        if not isinstance(event, dict):
            raise TransportError('invalid model stream event', unknown=True)
        self.events.append(event)
        if event.get('error'):
            raise TransportError('model stream returned an error', unknown=True)
        choices = event.get('choices', [])
        if not isinstance(choices, list):
            raise TransportError('invalid model stream choices', unknown=True)
        for choice in choices:
            if not isinstance(choice, dict):
                raise TransportError('invalid model stream choice', unknown=True)
            delta = choice.get('delta')
            if delta is not None and not isinstance(delta, dict):
                raise TransportError('invalid model stream delta', unknown=True)
            reason = choice.get('finish_reason')
            if reason is not None:
                if reason not in ('stop', 'tool_calls', 'function_call', 'length', 'content_filter'):
                    raise TransportError('unknown model stream finish reason', unknown=True)
                self.finish_reason = reason
                if reason in ('length', 'content_filter'):
                    raise TransportError('model response did not complete normally: ' + reason,
                                         unknown=True)
        return event

    def _line(self, line):
        line = line.rstrip('\r\n')
        raw = (line + '\n').encode('utf-8')
        self.size += len(raw)
        self.digest.update(raw)
        if self.size > 16 * 1024 * 1024:
            raise TransportError('model stream exceeds response limit', unknown=True)
        if line.startswith('data:'):
            self.frame.append(line[5:].removeprefix(' '))
        elif line.startswith('event:'):
            self.event_type = line[6:].strip()
        elif not line:
            if self.frame:
                return self._decode()
            self.event_type = ''
        return None

    def _eof(self):
        self.eof = True
        # GENOS compatibility: a complete last data frame can lack its blank
        # separator. Never execute this path after a timeout/network exception.
        if self.frame:
            self.trailing_frame_seen = True
            event = self._decode()
            self.trailing_frame = True
            return event
        return None

    def iter_events(self, lines):
        for line in lines:
            event = self._line(line)
            if event is not None:
                yield event
            if self.done:
                return
        event = self._eof()
        if event is not None:
            yield event

    async def aiter_events(self, lines):
        async for line in lines:
            event = self._line(line)
            if event is not None:
                yield event
            if self.done:
                return
        event = self._eof()
        if event is not None:
            yield event

    def require_complete(self):
        if not self.done:
            raise TransportError('model stream ended before completion', unknown=True)
