"""Shared complete citation grammar. Resolution uses actual stored anchor paths."""
import re
from .legal_coordinate import MOK_LETTERS
LETTERS=MOK_LETTERS
PART=re.compile(r'\s*(?:제\s*(?P<n>\d+)\s*(?P<role>항|호)(?:\s*의\s*(?P<branch>\d+))?|(?P<letter>['+LETTERS+r'])\s*목|(?P<detail>\d+)\)|\((?P<paren>\d+)\)|\((?P<hangul>['+LETTERS+r'])\))')
JOIN=re.compile(r'\s*(?:및|또는|과|와|,|ㆍ|·)\s*')
RANGE=re.compile(r'\s*(?:부터|내지|[~～∼])\s*')
QUALIFIER=re.compile(r'\s*(각\s*(?:호|목)\s*외의\s*부분)?\s*(전단|후단|단서|본문)?')
ORDER=('항','호','목','세목','세세목','세세세목')

def part(m):
    if m['role']:return m['role'],[int(m['n'])]+([int(m['branch'])] if m['branch'] else [])
    if m['letter']:return '목',[LETTERS.index(m['letter'])+1]
    if m['detail']:return '세목',[int(m['detail'])]
    if m['paren']:return '세세목',[int(m['paren'])]
    return '세세세목',[LETTERS.index(m['hangul'])+1]

def path(text,start=0):
    parts=[];end=start
    while (m:=PART.match(text,end)):
        p=part(m)
        if parts and ORDER.index(p[0])<=ORDER.index(parts[-1][0]):break
        parts.append(p);end=m.end()
    return parts,end

def inherit(prefix,own):
    if not own:return prefix
    rank=ORDER.index(own[0][0]);return [p for p in prefix if ORDER.index(p[0])<rank]+own

def expression(text,start=0,prefix=()):
    own,end=path(text,start)
    if not own:
        q=QUALIFIER.match(text,start)
        if q and any(q.groups()):
            inherited=list(prefix)
            return {'paths':[inherited],'ranges':[],'last_path':inherited,'end':q.end(),
                    'qualifiers':[re.sub(r'\s+','',x) for x in q.groups() if x]}
        return None
    current=inherit(list(prefix),own);paths=[current];ranges=[]
    while True:
        r=RANGE.match(text,end);j=JOIN.match(text,end)
        connector=r or j
        if not connector:break
        nxt,stop=path(text,connector.end())
        if not nxt:break
        target=inherit(current,nxt)
        if r:ranges.append((current,target));paths.pop()
        else:paths.append(target)
        current=target;end=stop
        until=re.match(r'\s*까지',text[end:])
        if until:end+=until.end()
    q=QUALIFIER.match(text,end);qualifiers=[]
    if q and any(q.groups()):qualifiers=[re.sub(r'\s+','',x) for x in q.groups() if x];end=q.end()
    return {'paths':paths,'ranges':ranges,'last_path':current,'end':end,'qualifiers':qualifiers}
