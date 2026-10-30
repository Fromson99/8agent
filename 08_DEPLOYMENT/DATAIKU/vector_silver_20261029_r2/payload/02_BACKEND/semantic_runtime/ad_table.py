"""Escaped HTML representation of AD Markdown tables for chat renderers.

No stored value becomes HTML, CSS, a link, or executable code. Markdown remains
available in the response for renderers that sanitize the scroll container.
"""
import html
import re

REVISION='ad-scroll-table-v1-20261006-r2'


def cells(line):
    return [html.unescape(v.strip().replace(r'\|','|').replace('<br>','\n'))
            for v in re.split(r'(?<!\\)\|',line.strip()[1:-1])]


def render(text):
    lines=text.splitlines();out=[];found=False;i=0
    def escaped(value):return html.escape(value,quote=True)
    while i<len(lines):
        if (lines[i].startswith('|') and i+1<len(lines)
                and re.fullmatch(r'\|[\s|:\-]+\|',lines[i+1])):
            found=True;headers=cells(lines[i]);i+=2;rows=[]
            while i<len(lines) and lines[i].startswith('|') and lines[i].rstrip().endswith('|'):
                rows.append(cells(lines[i]));i+=1
            out.append('<div role="region" aria-label="AD 자료 표: 가로·세로 스크롤" tabindex="0" '
                       'style="max-height:480px;max-width:100%;overflow:auto;border:1px solid #cbd5e1;">')
            out.append('<table style="border-collapse:collapse;width:100%;min-width:640px;">'
                       '<thead style="position:sticky;top:0;background:#f1f5f9;"><tr>')
            out.extend('<th scope="col" style="padding:8px;text-align:left;border-bottom:1px solid #cbd5e1;">'+escaped(v)+'</th>' for v in headers)
            out.append('</tr></thead><tbody>')
            for row in rows:
                out.append('<tr>')
                out.extend('<td style="padding:8px;vertical-align:top;white-space:pre-wrap;overflow-wrap:anywhere;min-width:100px;border-bottom:1px solid #e2e8f0;">'+escaped(v)+'</td>' for v in row)
                out.append('</tr>')
            out.append('</tbody></table></div>')
        else:
            if lines[i]:out.append('<p>'+escaped(lines[i])+'</p>')
            i+=1
    return ''.join(out) if found else None
