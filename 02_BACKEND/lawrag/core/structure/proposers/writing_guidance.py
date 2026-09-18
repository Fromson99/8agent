"""Standalone authoring-guidance labels; source offsets are never rewritten."""
import re

from . import scan

ID = 'writing_guidance'
ROLE = 'proposer'
LANG = 'ko'
FAMILY = 'writing_guidance'
SURFACE = '【 작성지침 】'

_LABEL = re.compile(r'(?m)^[ \t]*(?:【[ \t]*작성지침[ \t]*】|\[[ \t]*작성지침[ \t]*\])[ \t]*(?=\r?$)')


def propose(block, lex):
    if block.kind != 'text':
        return []
    out = scan(block, FAMILY, _LABEL, lambda m: None)
    for c in out:
        # Leading whitespace is outside the preserved marker coordinate.
        c.offset += len(block.text[c.offset:c.end]) - len(block.text[c.offset:c.end].lstrip())
        c.end = c.offset + len(c.surface)
        if block.text[:c.offset].strip():
            c.construction = 'fragment'
    return out
