"""Export the visible user example layout without claiming an original XLSX clone."""
import hashlib
import json
import math
import unicodedata

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


def build_example_workbook(root, out, mapping, table_rows, column_rows):
    wb = Workbook()
    wb.remove(wb.active)
    dark = '595959'
    edge = Side(style='thin', color='BFBFBF')
    base_font = Font(name='맑은 고딕', size=10, color='222222')
    header_font = Font(name='맑은 고딕', size=10, bold=True, color='FFFFFF')
    marker = '미승인 후보 · 명칭/스키마/표준 확정 전 · 실제 메타 신청·DB 생성 미수행'
    refs = root/'07_DOCS/REFERENCE/ARCHITECTURE/DATAIKU_GOLD_METADATA_20261022/images/gold_table_workbook'

    def sheet(name, widths, zoom=85):
        ws = wb.create_sheet(name)
        ws.sheet_view.showGridLines = True
        ws.sheet_view.zoomScale = zoom
        for col, width in widths.items():
            ws.column_dimensions[col].width = width
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.orientation = 'landscape'
        ws.page_setup.paperSize = ws.PAPERSIZE_A3
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.oddFooter.center.text = '예시 사진 기반 검토본 | 미승인 후보 | &P / &N'
        return ws

    def banner(ws, row, first, last, text, *, title=False):
        ws.merge_cells(start_row=row, start_column=first, end_row=row, end_column=last)
        c = ws.cell(row, first, text)
        c.font = Font(name='맑은 고딕', size=12 if title else 10, bold=title,
                      color='222222' if title else '9C6500')
        c.alignment = Alignment(vertical='center', wrap_text=True)
        ws.row_dimensions[row].height = 25 if title else 31

    def text_width(s):
        return sum(2 if unicodedata.east_asian_width(c) in {'W','F'} else 1 for c in s)

    def table(ws, headers, rows, row, col=1, *, autofilter=True):
        for j, header in enumerate(headers, col):
            c = ws.cell(row, j, header)
            c.fill = PatternFill('solid', fgColor=dark)
            c.font = header_font
            c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            c.border = Border(left=edge, right=edge, top=edge, bottom=edge)
        ws.row_dimensions[row].height = 30
        for i, values in enumerate(rows, row+1):
            lines = 1
            for j, value in enumerate(values, col):
                c = ws.cell(i, j, value)
                c.font = base_font
                c.alignment = Alignment(vertical='top', wrap_text=True)
                c.border = Border(left=edge, right=edge, top=edge, bottom=edge)
                c.fill = PatternFill('solid', fgColor='FFFFFF' if (i-row)%2 else 'F2F2F2')
                width = max(8, ws.column_dimensions[get_column_letter(j)].width-2)
                lines = max(lines, sum(max(1,math.ceil(text_width(s)/width)) for s in str(value or '').split('\n')))
            ws.row_dimensions[i].height = min(400, max(27, lines*15+8))
        if autofilter:
            ws.auto_filter.ref = f'{get_column_letter(col)}{row}:{get_column_letter(col+len(headers)-1)}{row+len(rows)}'
        ws.freeze_panes = f'{get_column_letter(col)}{row+1}'
        ws.print_title_rows = f'1:{row}'
        ws.print_area = f'{get_column_letter(col)}1:{get_column_letter(col+len(headers)-1)}{row+len(rows)}'

    # Photo 01: five columns B:F; all extra engineering columns stay in the full review workbook.
    ws = sheet('과제별활용테이블목록', {'A':3,'B':15,'C':23,'D':31,'E':25,'F':83})
    banner(ws,1,2,6,'과제별 활용테이블 목록 — 법규 파이프라인',title=True)
    banner(ws,2,2,6,marker+' | 스키마 칸은 목표 owner이며 미확정. 현재 SIDDA는 비고에 기록.')
    inventory = []
    for r in table_rows:
        candidate = '후보(미승인)' if r['골드후보']=='Y' else '제외 제안(미요청)'
        inventory.append(['확인 필요','확인 필요',r['후보테이블명'],candidate,
                          r['후보논리명']+' | 현재 '+r['현재스키마']+'.'+r['현재테이블명']+'\n'+r['레이어선정이유']])
    table(ws,['에이전트번호','스키마','테이블명','골드레이어 후보 테이블','비고'],inventory,3,2)
    ws['E3'].comment=Comment('사진의 O/0 표기 범례는 확인되지 않아 후보/제외 제안 문구를 사용합니다. 승인 상태가 아닙니다.','설계 근거')
    for i,r in enumerate(table_rows,4):
        ws.cell(i,4).hyperlink=f"#'{r['후보테이블명']}'!A1"
        ws.cell(i,4).font=Font(name='맑은 고딕',size=10,color='0563C1',underline='single')

    # Photo 02: nine fields, in the visible order, with an instruction block above.
    ws = sheet('과제별활용테이블_bizmeta',{'A':3,'B':7,'C':15,'D':22,'E':30,'F':54,'G':43,'H':17,'I':60,'J':34},70)
    banner(ws,1,2,10,'과제별 활용 데이터 Bizmeta — 법규 파이프라인',title=True)
    banner(ws,2,2,10,marker)
    guide = [
        ('데이터논리명','어떤 업무 데이터를 담는지 한글 설명을 작성. 컬럼 논리명과 구분.'),
        ('데이터출처','실제 원천과 구조화/색인 경로를 작성.'),
        ('데이터유형','MASTER / HISTORY / SNAPSHOT / SUMMARY 중 현재 저장 성격에 따른 후보.'),
        ('데이터 가공 프로세스 설명','입력·변환·결합·적재 과정을 작성. 상세 이유는 셀 메모와 상세 검토본 참조.'),
        ('생성시각','목표 배치 흐름과 미확정 운영 시각을 구분. 사진의 예시 시각을 복사하지 않음.'),
    ]
    banner(ws,4,2,10,'작성 항목 설명 — 사진에서 확인한 항목을 우리 데이터에 맞게 정리',title=True)
    for i,(label,text) in enumerate(guide,5):
        ws.merge_cells(start_row=i,start_column=2,end_row=i,end_column=5)
        ws.merge_cells(start_row=i,start_column=6,end_row=i,end_column=10)
        ws.cell(i,2,label).font=Font(name='맑은 고딕',size=10,bold=True)
        ws.cell(i,6,text).font=base_font
        for j in (2,6):
            ws.cell(i,j).alignment=Alignment(vertical='center',wrap_text=True)
            ws.cell(i,j).fill=PatternFill('solid',fgColor='F2F2F2')
        ws.row_dimensions[i].height=30
    banner(ws,11,2,10,'현재 9개 사용 테이블 전체 목록이며 Gold 후보·제외 제안은 첫 시트와 등록대상 시트에서 구분합니다.')
    biz = [[i,'확인 필요','확인 필요',r['후보테이블명'],r['업무설명'],r['출처'],r['데이터유형'],r['가공과정'],r['생성시각']]
           for i,r in enumerate(table_rows,1)]
    table(ws,['No.','에이전트번호','스키마','테이블명','데이터논리명','데이터출처','데이터유형','데이터 가공 프로세스 설명','생성시각'],biz,13,2)
    for i,r in enumerate(table_rows,14):
        ws.cell(i,5).comment=Comment('한글명: '+r['후보논리명']+'\n명칭 선정 이유: '+r['명칭선정이유'],'설계 근거')
        ws.cell(i,8).comment=Comment(r['데이터유형선정이유'],'설계 근거')

    # Photo 03: side-by-side first and further review lists. Exclusion requests are not invented.
    ws=sheet('메타등록대상',{'A':37,'B':4,'C':40,'D':62})
    banner(ws,1,1,4,'등록 차수는 우리 설계 제안입니다. 실제 신청·승인·제외 요청은 아직 하지 않았습니다.')
    first=[r for r in table_rows if r['등록차수']=='1차']
    later=[r for r in table_rows if r['등록차수']!='1차']
    table(ws,['1차 메타 등록 대상'],[[r['후보테이블명']] for r in first],3,1,autofilter=False)
    table(ws,['2차 추가 검토후 등록대상','비고'],
          [[r['후보테이블명'],('제외 제안(미요청)' if r['등록차수']=='제외 제안' else '추가 검토 후보')+'\n'+r['레이어선정이유']] for r in later],3,3,autofilter=False)
    ws.freeze_panes='A4'
    ws.print_area=f'A1:D{3+max(len(first),len(later))}'

    # Photo 04 has unknown type-conversion direction; explicitly label ours current/candidate.
    ws=sheet('컬럼타입대조',{'A':34,'B':30,'C':8,'D':34,'E':4,'F':28,'G':27,'H':34,'I':48},75)
    banner(ws,1,1,9,'컬럼 타입 대조 — 현재 타입 / 목표 후보 타입',title=True)
    banner(ws,2,1,9,'사진 4의 좌우 타입 대조 배치를 참고. 원본의 변환 방향은 미확인. 우리 안은 현행 타입 보존, 표준 승인 전입니다.')
    compared=[[r['현재테이블명'],r['현재컬럼명'],r['순번'],r['현재타입'],'',r['후보테이블명'],r['후보컬럼명'],r['1차후보타입'],'기존 값·타입 유지; 표준 승인 필요'] for r in column_rows]
    table(ws,['현재 테이블명','현재 컬럼명','순번','현재 타입','','목표 테이블명','목표 컬럼명','목표 타입(후보)','비고'],compared,3)
    for i,r in enumerate(column_rows,4):
        ws.cell(i,9).comment=Comment(r['타입유지변경이유']+'\n'+r['검토사항'],'타입 검토')

    for r in table_rows:
        ws=sheet(r['후보테이블명'],{'A':9,'B':35,'C':31,'D':43},90)
        banner(ws,1,1,4,r['후보테이블명']+' / '+r['후보논리명'],title=True)
        banner(ws,2,1,4,'미승인 후보 | 현행 타입 보존 | 물리명 셀 메모: 업무 설명·선정 이유 / 타입 셀 메모: PK·NULL·기본값')
        selected=[c for c in column_rows if c['후보테이블명']==r['후보테이블명']]
        table(ws,['순번','물리명','논리명','데이터 타입'],
              [[c['순번'],c['후보컬럼명'],c['후보논리명'],c['1차후보타입']] for c in selected],4)
        ws['A1'].comment=Comment(r['테이블Description'],'테이블 설명')
        for i,c in enumerate(selected,5):
            ws.cell(i,2).comment=Comment('현재 컬럼: '+c['현재컬럼명']+'\n'+c['컬럼Description'],'컬럼 설명')
            ws.cell(i,4).comment=Comment('NULL 허용: '+c['NULL허용']+'\nPK 순번: '+(c['PK순번'] or '해당 없음')+
                                        '\n기본값: '+(c['기본값'] or '없음')+'\n'+c['타입유지변경이유'],'컬럼 계약')

    # An explicit provenance sheet prevents this reconstruction being mistaken for an approved template.
    ws=sheet('양식대조안내',{'A':31,'B':58,'C':78})
    banner(ws,1,1,3,'제공 사진과 이번 파일의 대응',title=True)
    correspondence=[
        ['사진 1','과제별활용테이블목록','5개 열 순서와 B:F 배치 반영. 후보 표기는 범례 미확인으로 문구 사용.'],
        ['사진 2','과제별활용테이블_bizmeta','9개 열 순서 및 상단 작성 설명 반영. 필수 여부의 미확인 내용을 확정하지 않음.'],
        ['사진 3','메타등록대상','1차/추가 검토 목록의 좌우 배치 반영. 우리 제외 건은 제안이며 미요청.'],
        ['사진 4','컬럼타입대조','현재/목표 후보 타입 대조. 원본의 미확인 변환 방향을 재사용하지 않음.'],
        ['사진 5·6','테이블명별 9개 시트','순번 → 물리명 → 논리명 → 데이터 타입 순서. 설명·이유는 셀 메모에 보존.'],
        ['사진 7','별도 열 순서의 참고 사례','사진 7은 타입/논리명 순서가 다름. 이번 통일 순서는 사진 5·6 기준.'],
        ['원본 확보 범위','엑셀 화면 사진 7장','XLSX 원본의 숨은 열·수식·정확한 서식·전체 시트는 확인하지 못함. 원본 파일 복제본이 아님.'],
        ['한글명·설명·선정 이유','테이블 및 컬럼 셀 메모 + 상세 검토본','열 구성을 늘리지 않고 설명을 보존. 상세 검토본은 TABLE_COLUMN_MAPPING_PLAN.xlsx.'],
        ['우리 코드와의 정합성','physical_mapping.draft.yaml에서 동일 후보명 사용','9개 테이블·46개 컬럼·타입 동일성 정적 대조. 실행 코드 연결·DB 생성은 미수행.'],
        ['예시 테이블과 분리','사진의 타 과제·A06 행을 그대로 복사하지 않음','우리 현행 9개 테이블에 적용. 에이전트번호·목표 owner·표준 명칭은 확인 필요.'],
    ]
    table(ws,['근거/항목','반영 위치','반영 범위와 차이'],correspondence,3)
    wb.active=0
    target=out/'DATAIKU_GOLD_EXAMPLE_FORMAT.xlsx'
    wb.save(target)

    # Inspect the saved artifact, including comments; do not claim rendered visual verification.
    book=load_workbook(target)
    assert len(book.sheetnames)==14
    assert [book['과제별활용테이블목록'].cell(3,c).value for c in range(2,7)]==['에이전트번호','스키마','테이블명','골드레이어 후보 테이블','비고']
    assert [book['과제별활용테이블_bizmeta'].cell(13,c).value for c in range(2,11)]==['No.','에이전트번호','스키마','테이블명','데이터논리명','데이터출처','데이터유형','데이터 가공 프로세스 설명','생성시각']
    assert book['과제별활용테이블목록'].max_row==12
    assert book['과제별활용테이블_bizmeta'].max_row==22
    count=0
    for key,t in mapping['tables'].items():
        s=book[t['candidate_name']]
        assert tuple(s.cell(4,c).value for c in range(1,5))==('순번','물리명','논리명','데이터 타입')
        expected=[c for c in column_rows if c['후보테이블명']==t['candidate_name']]
        assert s.max_row==4+len(expected)
        assert s['A1'].comment and s['A1'].comment.text==t['metadata']['description_plain_text']
        for i,(c,m) in enumerate(zip(expected,t['columns'].values()),5):
            assert [s.cell(i,j).value for j in range(1,5)]==[c['순번'],m['candidate_name'],m['logical_name_ko_candidate'],m['candidate_type']]
            assert m['metadata']['description_plain_text'] in s.cell(i,2).comment.text
            count+=1
    assert count==46
    assert len(first)==4 and len(later)==5
    book.close()
    validation={'status':'DRAFT_EXAMPLE_LAYOUT_NOT_ORIGINAL_XLSX','table_count':9,'column_count':count,
                'sheet_count':14,'mapping_revision':mapping['mapping_revision'],
                'checks':['photo 01/02 visible column order','photo 03 side-by-side grouping',
                          'photo 05/06 per-table four-column order','all 46 names/types agree with YAML',
                          'all 9 table and 46 column descriptions preserved in comments'],
                'not_verified':['original XLSX hidden sheets/columns/formulas','exact original formatting','rendered Excel/LibreOffice appearance','official standard approval','field database execution'],
                'source_images':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(refs.glob('*.jpg'))},
                'input_mapping_sha256':hashlib.sha256((out/'physical_mapping.draft.yaml').read_bytes()).hexdigest(),
                'output_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    (out/'EXAMPLE_FORMAT_VALIDATION.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
    return validation
