from common import *
from openpyxl import load_workbook
import math,unicodedata,collections
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261104-multiturn-repair';OUT.mkdir(exist_ok=True)
R3=ROOT/'09_ARTIFACTS/REPORTS/DOCUMENTS/20261104-integration-template-r3'
book=read(R3/'작성데이터.json');rows=[];receipts=[]
for agent in (3,5):
 src=next(R3.glob(f'Agent8_과제{agent}_*.xlsx'));wb=load_workbook(src);ws=wb[f'A8_ITE_00{agent}']
 for n,item in enumerate(book[str(agent)],1):
  status='미실행';note='최종 수정본의 개별 실모델 답변은 미확인. 제공자 UNKNOWN 뒤 추가 전송을 중단함.'
  if (agent==3 and n in (1,2,26)) or (agent==5 and n in (1,2,8,17,22,23,30)):
   note='GENOS 현장 화면 미실행. API/모의 검사로 클릭·화면 통과 판정하지 않음.'
  elif agent==5 and n in (*range(9,20),21,24,25):
   note='내규/혼합 범위의 실제 내부 모델 답변은 미확인. 내규→외규 전환은 합성 원문을 이용한 실제 API 계약으로만 확인.'
  elif agent==5 and n in (26,27,28,29):
   note='내규 기반 대사 실제 답변·화면 미실행. 기존 원문 내용에 맞춘 R3 질문과 기대 결과를 유지.'
  if agent==3 and n==27:
   status='미통과(중간본 실험)';note='중간수정본: 첫 응답349.559초/원문전용, 같은 질문 반복54.499초/설명2주장·같은목표 유지. 두 응답 모두 완료 조건은 미충족. 동일요청 재조회는 추가모델0. 이후 지침·검토진단 추가수정본은 실답 미검증.'
  if agent==3 and n==16:
   note='27번 반복시험에서 같은 문장을 관찰: 첫 응답 원문전용, 두 번째 설명2주장. 16번 독립 시험은 미실행이며 별도 통과로 중복 집계하지 않음.'
  if agent==3 and n==25:
   note='이 문항의 내부회계관리자 후속 질문은 미실행. 별도 임시총회 후속 실험에서 지침 누락·새목표 분리·시간초과를 확인했고 추가 수정함. 최종본 실답 검증은 남음.'
  row=n+3;ws.cell(row,9,status);ws.cell(row,10,' / '.join(filter(None,[item.get('note'),note])))
  widths=[ws.column_dimensions[c].width for c in 'ABCDEFGHIJ']
  def lines(text,width):return sum(max(1,math.ceil(sum(2 if unicodedata.east_asian_width(ch) in 'WF' else 1 for ch in line)/max(1,width-2))) for line in str(text or '').split('\n'))
  ws.row_dimensions[row].height=max(ws.row_dimensions[row].height or 60,15*max(lines(ws.cell(row,c).value,widths[c-1]) for c in range(1,11))+6)
  rows.append({'agent':agent,'number':n,'title':item['title'],'status':status,'note':note,'final_model_test_passed':False})
 history=wb['개정이력'];history['A13']='v2.3-R3 수정후점검';history['D13']='R3 질문·기대 결과 유지. 실제 중간본 결과와 최종본 미실행을 구분.';history['E13']='통과 기재0 / 현장 미검증'
 target=OUT/f'Agent8_과제{agent}_통합테스트30_수정후점검_20261104.xlsx';wb.save(target)
 checked=load_workbook(target);assert len(checked.sheetnames)==3 and checked[ws.title].max_row==33
 for n,item in enumerate(book[str(agent)],1):
  assert checked[ws.title].cell(n+3,9).value!='통과'
 receipts.append({'path':str(target.relative_to(ROOT)),'sha256':sha(target),'source_sha256':sha(src),'sheets':checked.sheetnames,'cases':30,'passed':0})
put(OUT/'60개_점검상태.json',{'rows':rows,'final_live_passed':0,'independently_executed_R3_cases':1,'actual_probe_turns':3,'rest_independently_unexecuted':59,'source_question_actions_unchanged':True});put(OUT/'수정후_엑셀검증.json',receipts)
print('Two30-case v2.3-format result workbooks; final-model passes0')
