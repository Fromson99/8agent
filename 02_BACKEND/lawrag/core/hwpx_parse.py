"""OWPML -> native Elements, with source anchors, cell spans and nested tables.

Uses only Python's standard library to read HWPX; Hancom is not required.
Physical PDF coordinates are deliberately not inferred from reflow XML.
"""
from __future__ import annotations
import base64
import hashlib
import mimetypes
import posixpath
import re
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

VERSION = 'hwpx-native-elements-v1'

def local(e):
    return e.tag.rsplit('}', 1)[-1]

def children(e, tag):
    return [c for c in e if local(c) == tag]

def first(e, tag):
    return next((c for c in e if local(c) == tag), None)


def parse(path):
    from .parse_adapter import ParseResult, Element, Table, Cell
    path = Path(path);elements=[];images={};warnings=[]
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or any(PurePosixPath(n).is_absolute() or '..' in PurePosixPath(n).parts or '\\' in n for n in names):
            raise ValueError('unsafe/duplicate HWPX member')
        if sum(i.file_size for i in z.infolist()) > 256 * 1024 * 1024:
            raise ValueError('HWPX expanded document exceeds 256 MiB')
        def xml(name):
            raw=z.read(name)
            if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
                raise ValueError('HWPX XML DTD/entity is not accepted')
            return ET.fromstring(raw)
        manifest={};sections=[]
        if 'Contents/content.hpf' in names:
            hpf=xml('Contents/content.hpf')
            for e in hpf.iter():
                if local(e)=='item' and e.get('id') and e.get('href'):
                    href=e.get('href')
                    member=href if href in names else posixpath.normpath(posixpath.join('Contents',href))
                    if member not in names:raise ValueError('HWPX package member absent: '+member)
                    manifest[e.get('id')]=member
            for e in hpf.iter():
                if local(e)=='itemref':
                    member=manifest.get(e.get('idref'))
                    if not member:raise ValueError('HWPX spine member absent')
                    if re.fullmatch(r'Contents/section\d+\.xml',member):sections.append(member)
        if not sections:
            sections=sorted((n for n in names if re.fullmatch(r'Contents/section\d+\.xml',n)),key=lambda n:int(re.search(r'(\d+)\.xml$',n).group(1)))
            warnings.append('HWPX spine 없음: 구역 번호 순서 사용')
        if not sections or len(sections)!=len(set(sections)):raise ValueError('invalid HWPX sections')
        styles={};chars={}
        if 'Contents/header.xml' in names:
            for e in xml('Contents/header.xml').iter():
                if local(e)=='style':styles[e.get('id')]=dict(e.attrib)
                if local(e)=='charPr':chars[e.get('id')]={**e.attrib,'bold':first(e,'bold') is not None}
        def text(e):
            tag=local(e)
            if tag=='t':return ''.join(e.itertext())
            if tag in ('lineBreak','br'):return '\n'
            if tag=='tab':return '\t'
            if tag=='equation':
                warnings.append('HWPX 수식은 원본 스크립트로 보존; 시각 대조 필요')
                return ''.join(c.text or '' for c in e.iter() if local(c)=='script')
            result=[text(c) for c in e]
            return ('\n' if tag in ('subList','tc') else '').join(x for x in result if x)
        table_pictures=[]
        def table(node, anchor):
            cells=[];nested=[];cell_metadata=[];nr=nc=0
            for ri,tr in enumerate(children(node,'tr')):
                for ci,tc in enumerate(children(tr,'tc')):
                    addr=first(tc,'cellAddr');span=first(tc,'cellSpan')
                    r=int(addr.get('rowAddr',ri)) if addr is not None else ri
                    c=int(addr.get('colAddr',ci)) if addr is not None else ci
                    rs=int(span.get('rowSpan',1)) if span is not None else 1
                    cs=int(span.get('colSpan',1)) if span is not None else 1
                    if min(r,c)<0 or min(rs,cs)<1 or max(r+rs,c+cs)>10000:raise ValueError('invalid HWPX cell span')
                    sub=first(tc,'subList')
                    value=text(sub) if sub is not None else ''
                    cell_metadata.append({'row':r,'col':c,'attributes':dict(tc.attrib),
                        'paragraphs':[{'attributes':dict(p.attrib),'runs':[dict(x.attrib) for x in children(p,'run')]} for p in children(sub,'p')] if sub is not None else []})
                    cells.append(Cell(value,r,c,rs,cs,is_col_header=tc.get('header') in ('1','true')))
                    nr=max(nr,r+rs);nc=max(nc,c+cs)
                    # Stop at each nested table; deeper levels are kept recursively.
                    def descend(e):
                        for n in e:
                            if local(n)=='tbl':
                                nt,meta=table(n,anchor+f'/cell[{r},{c}]/table[{len(nested)}]')
                                nested.append({'parent_cell':[r,c],'table':nt.dump(),**meta})
                            elif local(n)=='pic':
                                table_pictures.append((n,anchor+f'/cell[{r},{c}]/picture[{len(table_pictures)}]',[r,c]))
                            else:descend(n)
                    if sub is not None:descend(sub)
            return Table(nr,nc,cells),{'source_anchor':anchor,'nested_tables':nested,'attributes':dict(node.attrib),'cell_metadata':cell_metadata}
        def emit(kind,value,anchor,**kwargs):
            e=Element(index=len(elements),type=kind,text=value,meta={'source_format':'hwpx','source_anchor':anchor,'coordinate_source':'reflow_xml',**kwargs.pop('meta',{})},**kwargs)
            elements.append(e);return e
        def picture(node,anchor,parent_cell=None):
            e=emit('picture','',anchor,meta={'attributes':dict(node.attrib),'parent_cell':parent_cell})
            image=next((x for x in node.iter() if local(x)=='img'),None)
            ref=image.get('binaryItemIDRef') if image is not None else None
            member=manifest.get(ref)
            if not member and ref:member=next((n for n in names if n.startswith('BinData/') and PurePosixPath(n).stem==ref),None)
            if member:
                payload=z.read(member);e.meta['binary_member']=member;e.meta['binary_sha256']=hashlib.sha256(payload).hexdigest()
                e.meta['has_image']=True
                mime=mimetypes.guess_type(member)[0] or 'application/octet-stream'
                images[e.index]='data:'+mime+';base64,'+base64.b64encode(payload).decode()
            else:warnings.append('HWPX 그림 참조 미해결: '+str(ref))
        def paragraph(p,anchor,kind='text'):
            style=styles.get(p.get('styleIDRef'),{})
            formatting={'paragraph_attributes':dict(p.attrib),'style':style,'runs':[{'attributes':dict(r.attrib),'character_properties':chars.get(r.get('charPrIDRef'),{})} for r in children(p,'run')]}
            pending=[];part=0
            def flush():
                nonlocal part
                if any(pending):emit(kind,''.join(pending),anchor+f'/text[{part}]',meta=formatting);part+=1
                pending.clear()
            def walk(node):
                tag=local(node)
                if tag=='tbl':
                    flush();t,meta=table(node,anchor+f'/table[{len(elements)}]');emit('table',t.text(),meta['source_anchor'],table=t,meta=meta)
                    for node_,anchor_,cell_ in table_pictures:picture(node_,anchor_,cell_)
                    table_pictures.clear()
                elif tag in ('footNote','endNote','header','footer'):
                    flush()
                    def paragraphs(parent):
                        for pp in parent:
                            if local(pp)=='p':yield pp
                            else:yield from paragraphs(pp)
                    for n,pp in enumerate(paragraphs(node)):
                        paragraph(pp,anchor+f'/{tag}[{n}]',kind='footnote' if tag in ('footNote','endNote') else ('page_header' if tag=='header' else 'page_footer'))
                elif tag=='pic':
                    flush();picture(node,anchor+f'/picture[{len(elements)}]')
                elif tag in ('t','tab','lineBreak','br','equation'):pending.append(text(node))
                else:
                    if tag not in ('run','p','ctrl','secPr','colPr') and list(node):
                        # Attributes and source XML remain available for unsupported controls.
                        formatting.setdefault('control_types',[]).append(tag)
                    if tag in ('ole','chart','textart','container','video'):
                        warnings.append('HWPX 복합 개체 '+tag+': 원본/PDF 시각 검토 필요')
                    for child in node:walk(child)
            for run in children(p,'run'):walk(run)
            flush()
        for member in sections:
            for n,p in enumerate(children(xml(member),'p')):paragraph(p,member+f'/p[{n}]')
    return ParseResult(str(path),hashlib.sha256(path.read_bytes()).hexdigest()[:16],
        'hwpx(zip) → native XML elements ('+VERSION+')',True,elements,
        list(dict.fromkeys(warnings)),{'elements':len(elements),'tables':sum(e.is_table for e in elements),
        'pictures':len(images),'coordinate_source':'reflow_xml','native_metadata_preserved':True,'parser_version':VERSION},images)
