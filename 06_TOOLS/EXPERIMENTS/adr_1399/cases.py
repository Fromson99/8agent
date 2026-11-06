"""Prospectively fixed synthetic boundary inputs; expectations saved separately."""
from copy import deepcopy

def obj(props):return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}
def text():return {'type':'string','minLength':1,'maxLength':800}
def enum(*values):return {'enum':list(values)}
def cases():
 rows=[];gold={}
 def add(number,group,stage,context,proposal,schema,expected,decision_paths,repair=False):
  key=f'case-{number:02d}';rows.append(dict(id=key,group=group,stage=stage,context=deepcopy(context),proposal=deepcopy(proposal),schema=schema))
  gold[key]={'expected_review':expected,'decision_paths':decision_paths,'repair_planned':repair}
 common={'source_kind':'SYNTHETIC_NONLEGAL','document_version':'v1','permission':'current authorized originals'}
 conversation={**common,'previous':{'goal_id':'G1','task':'가상 업무 승인 절차 확인','facts':['승인권자는 부서장이다.']},'current_request':'그럼 같은 업무의 승인 서류는 무엇인가요?','meaning':'같은 업무를 이어 묻고 조건과 권한은 바뀌지 않았다.'}
 cp={'relation':'FOLLOW_UP','action':'START_NEW','goal_id':None,'reason':'이전 질문의 같은 업무를 이어 묻는 후속 질문이며 목표를 유지한다.'}
 cs=obj({'relation':enum('FOLLOW_UP','NEW_TOPIC'),'action':enum('CONTINUE','START_NEW'),'goal_id':enum('G1',None),'reason':text()})
 add(1,'conversation','CONVERSATION',conversation,cp,cs,'REPAIR',['/action','/goal_id'],True)
 investigation={**common,'request':'가상 계약의 효력 발생 조건을 모두 확인한다.','read_originals':[{'id':'S1','text':'효력은 별도 승인 규정의 조건을 충족할 때 발생한다.'}],'available_actions':{'READ':'S2 승인 규정 원문을 읽는다','FINISH':'추가 조사 없이 충분 판정으로 조사를 종료한다'},'missing_original':'S2 승인 규정은 아직 읽지 않았다.'}
 ip={'action':'READ','target':'S2','sufficiency':'NEEDS_SOURCE','reason':'효력 조건을 확정하려면 S2 승인 규정 원문이 추가로 필요하다.'}
 ins=obj({'action':enum('READ','FINISH'),'target':enum('S2',None),'sufficiency':enum('NEEDS_SOURCE','SUFFICIENT'),'reason':text()})
 add(2,'investigation','INVESTIGATION',investigation,ip,ins,'PASS',[])
 assessment={**common,'request':'가상 계약이 유효하다고 확정할 수 있나요?','originals':[{'id':'S1','text':'서면 승인이 확인된 경우에만 유효하다.'}],'facts':['서면 승인 여부는 미확인이다.'],'scope':'유효성 확정 판단이며 조건부 일반 안내가 아니다.'}
 ap={'status':'COVERED','conclusion':'유효하다.','reason':'핵심 근거인 서면 승인 사실이 없으므로 유효성을 확정할 근거가 부족하다.'}
 ass=obj({'status':enum('COVERED','INSUFFICIENT'),'conclusion':text(),'reason':text()})
 add(3,'assessment','ASSESSMENT',assessment,ap,ass,'REPAIR',['/status','/conclusion'],True)
 accumulation={**common,'originals':[{'id':'S1','text':'가상 업무 X는 서면 승인을 받아야 한다.'}],'existing_knowledge':{'node_id':'N1','text':'가상 업무 X는 구두 승인만으로 진행할 수 있다.'},'new_judgment':'가상 업무 X는 서면 승인을 받아야 한다.','field_meanings':{'verdict':'원문이 새 판단을 지지하는가','relation':'기존 지식과 새 판단의 관계'}}
 kp={'relation':'CONTRADICTION','verdict':'SUPPORTED','reason':'새 판단은 S1 원문이 지지하지만 구두 승인만으로 된다는 기존 지식과 충돌한다.'}
 ks=obj({'relation':enum('SAME','CONTRADICTION','NEW'),'verdict':enum('SUPPORTED','CONTRADICTED','UNKNOWN'),'reason':text()})
 add(4,'accumulation','ACCUMULATE',accumulation,kp,ks,'PASS',[])
 usage={**common,'request':'가상 업무의 승인 필요성을 설명한다.','originals':[{'id':'S1','text':'가상 업무 X는 서면 승인을 받아야 한다.'}],
  'approved_paths':[{'path_id':'P1','node_ids':['N1'],'source_refs':['S1'],'text':'서면 승인이 있어야 진행 가능'}],
  'field_meanings':{'ontology_usage':'실제 특정 주장에 쓴 승인 경로의 명시적 사용 기록. 빈 배열은 사용 기록 없음.'}}
 up={'claim_id':'C1','claim':'가상 업무 X는 서면 승인을 받아야 한다.','ontology_usage':[],
     'reason':'승인 경로 P1의 N1을 이 답변의 C1 판단에 실제 사용했다.'}
 us=obj({'claim_id':enum('C1'),'claim':text(),'ontology_usage':{'type':'array','maxItems':1,'items':obj({'path_id':enum('P1'),'node_ids':{'type':'array','items':enum('N1'),'minItems':1,'maxItems':1},'claim_id':enum('C1')})},'reason':text()})
 add(5,'usage','ASSESSMENT',usage,up,us,'REPAIR',['/ontology_usage'],True)
 add(6,'conversation','CONVERSATION',conversation,{**cp,'action':'CONTINUE','goal_id':'G1'},cs,'PASS',[])
 add(7,'investigation','INVESTIGATION',investigation,{**ip,'action':'FINISH','target':None},ins,'REPAIR',['/action'],True)
 add(8,'assessment','ASSESSMENT',assessment,{**ap,'status':'INSUFFICIENT','conclusion':'서면 승인 사실이 확인되지 않아 유효성을 확정할 수 없다.'},ass,'PASS',[])
 add(9,'accumulation','ACCUMULATE',accumulation,{**kp,'relation':'SAME'},ks,'REPAIR',['/relation'],True)
 add(10,'usage','ASSESSMENT',usage,{**up,'reason':'승인 경로 P1은 제공받았지만 사용하지 않았고, S1 원문을 직접 확인해 C1을 작성했다.'},us,'PASS',[])
 partial={**common,'request':'승인 방식과 승인 기한을 알려주세요.','originals':[{'id':'S1','text':'서면 승인을 받아야 한다.'}],'missing':'승인 기한을 정한 원문은 아직 없다.'}
 pp={'status':'PARTIAL','covered':['승인 방식'],'unresolved':['승인 기한'],'reason':'승인 방식은 S1로 확인되어 서면 승인이라고 답하고, 기한은 원문 부족으로 미확인으로 남긴다.'}
 ps=obj({'status':enum('PARTIAL','COVERED'),'covered':{'type':'array','items':text()},'unresolved':{'type':'array','items':text()},'reason':text()})
 add(11,'normal-boundaries','ASSESSMENT',partial,pp,ps,'PASS',[])
 handoff={**common,'request':'가상 업무 승인 요건을 설명한다.','execution_contract':{'FINISH':'원문 조사를 종료하고 별도 ASSESS 단계에서 근거 충분성과 최종 답변을 판단한다.'},'originals':[{'id':'S1','text':'서면 승인을 받아야 한다.'}]}
 hp={'action':'FINISH','assessment_status':'PENDING','reason':'선택한 원문 조사는 끝났으며 답변의 충분성은 다음 ASSESS에서 검토해야 한다.'}
 hs=obj({'action':enum('READ','FINISH'),'assessment_status':enum('PENDING','COVERED'),'reason':text()})
 add(12,'normal-boundaries','INVESTIGATION',handoff,hp,hs,'PASS',[])
 return rows,gold
