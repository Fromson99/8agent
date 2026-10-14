"""Request-local answer channel and incremental Draft paragraph projection.

Only paragraphs[*].text leaves the structured model channel. Reasoning, IDs,
source quotes and other fields never become chat tokens.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import json

REVISION = 'answer-stream-20260929-r1'
_sink = ContextVar('legal_answer_sink', default=None)


@contextmanager
def capture(request_id, sink):
    seq = 0

    def send(text):
        nonlocal seq
        send.started = True
        seq += 1
        sink({'schema_version': 'rag-answer-delta-v1', 'request_id': request_id,
              'seq': seq, 'text': text})

    token = _sink.set(send)
    try:
        yield
    finally:
        _sink.reset(token)


def current_sink():
    return _sink.get()


class DraftText:
    """Small streaming JSON lexer; full JSON/schema validation stays in Gateway."""
    def __init__(self, sink):
        self.sink = sink
        self.stack = []
        self.mode = None
        self.key = False
        self.target = False
        self.string = ''
        self.escape = ''
        self.surrogate = ''
        self.paragraphs = 0
        self.first = False
        self.emitted = False

    def _path(self):
        if not self.stack:
            return ()
        frame = self.stack[-1]
        return frame['path'] + (frame['key'] if frame['kind'] == '{' else frame['index'],)

    def _done(self):
        if self.stack:
            self.stack[-1]['state'] = 'comma'

    def feed(self, fragment):
        out = []
        def decoded(char):
            if self.key:
                self.string += char
            elif self.target:
                if not self.first:
                    if self.paragraphs:
                        out.append('\n\n')
                    self.paragraphs += 1
                    self.first = True
                out.append(char)

        for char in fragment:
            if self.mode == 'string':
                if self.escape:
                    self.escape += char
                    if self.escape == '\\u' or (self.escape.startswith('\\u') and len(self.escape) < 6):
                        continue
                    try:
                        value = json.loads('"' + self.escape + '"')
                    except ValueError:
                        raise ValueError('invalid Draft string escape') from None
                    self.escape = ''
                    if len(value) == 1 and 0xD800 <= ord(value) <= 0xDBFF:
                        self.surrogate = value
                        continue
                    if self.surrogate:
                        if not (len(value) == 1 and 0xDC00 <= ord(value) <= 0xDFFF):
                            raise ValueError('invalid Draft surrogate pair')
                        value = chr(0x10000 + ((ord(self.surrogate)-0xD800) << 10) + ord(value)-0xDC00)
                        self.surrogate = ''
                    decoded(value)
                elif char == '\\':
                    self.escape = '\\'
                elif char == '"':
                    if self.surrogate:
                        raise ValueError('incomplete Draft surrogate pair')
                    self.mode = None
                    if self.key:
                        self.stack[-1].update(key=self.string, state='colon')
                    else:
                        self._done()
                else:
                    if self.surrogate or ord(char) < 32:
                        raise ValueError('invalid Draft string')
                    decoded(char)
                continue
            if self.mode == 'primitive':
                if char not in ',]} \n\r\t':
                    continue
                self.mode = None
                self._done()
            if char.isspace():
                continue
            frame = self.stack[-1] if self.stack else None
            if char == '"':
                self.mode = 'string'
                self.key = bool(frame and frame['kind'] == '{' and frame['state'] == 'key')
                path = self._path()
                self.target = not self.key and len(path) == 3 and path[0] == 'paragraphs' and type(path[1]) is int and path[2] == 'text'
                self.string = ''; self.first = False
            elif char in '{[':
                self.stack.append({'kind': char, 'path': self._path(), 'key': None, 'index': 0,
                                   'state': 'key' if char == '{' else 'value'})
            elif char in '}]':
                if not frame or (frame['kind'], char) not in (('{', '}'), ('[', ']')):
                    raise ValueError('invalid Draft nesting')
                self.stack.pop(); self._done()
            elif char == ':':
                if not frame or frame['state'] != 'colon':
                    raise ValueError('invalid Draft key')
                frame['state'] = 'value'
            elif char == ',':
                if not frame or frame['state'] != 'comma':
                    raise ValueError('invalid Draft separator')
                frame['index'] += 1
                frame['state'] = 'key' if frame['kind'] == '{' else 'value'
            else:
                self.mode = 'primitive'
        if out:
            self.emitted = True
            self.sink(''.join(out))
