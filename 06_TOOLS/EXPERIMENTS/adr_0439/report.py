"""Read-only full model IO report and probe completion records."""
from pathlib import Path
import base64, hashlib, json
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0439-internal-mock-v33-gemini'
ART=ADR/'artifacts'
def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def block(v):return '\n```json\n'+(v if isinstance(v,str) else json.dumps(v,ensure_ascii=False,indent=2))+'\n```\n'
def main():
 r=read(ART/'results.json'); m=read(ADR/'실험/manifest.json'); rows=[];sections=[]
 for c,q in zip(r['cases'],m['questions']):
  cid=c['case_id']; section='\n## '+cid+'\n'+block({k:v for k,v in c.items() if k not in ['usage','cached_meta']})
  for d in sorted((ART/'runs'/cid/'provider').glob('call-*')):
   req=read(d/'request.json');raw=read(d/'response.json');u=raw.get('usageMetadata',{});mods={v['modality']:v['tokenCount'] for v in u.get('promptTokensDetails',[])}
   phase=d.name.split('-',2)[2]; row={'case':cid,'phase':phase,'input_tokens':u.get('promptTokenCount',0),'output_tokens':u.get('candidatesTokenCount',0),'text_tokens':mods.get('TEXT',0),'image_tokens':mods.get('IMAGE',0),'cached_input_tokens':u.get('cachedContentTokenCount',0),'finish':raw.get('candidates',[{}])[0].get('finishReason')};rows.append(row)
   section+='\n### '+d.name+'\n'+block(row)+'\n**System 전체**\n'+block(req['systemInstruction']['parts'][0]['text'])+'\n**User 전체**\n'+block(req['contents'][0]['parts'][0]['text'])+'\n**API 설정·스키마**\n'+block(req['generationConfig'])+'\n**로컬 검증 스키마**\n'+block(read(d/'validation-schema.json'))+'\n**실제 이미지 입력**\n'
   for part in req['contents'][0]['parts']:
    if 'inlineData' not in part:continue
    data=base64.b64decode(part['inlineData']['data']);p=ART/'report-images'/(hashlib.sha256(data).hexdigest()+'.png');p.parent.mkdir(exist_ok=True)
    if not p.exists():p.write_bytes(data)
    section+=f'\n![실제 입력]({p})\n'
   section+='\n**원응답 전체**\n'+block(raw)+f'\n[실제 전송 JSON]({d}/request.json)\n'
   if (d/'output.json').exists():section+='\n**해석한 출력**\n'+block(read(d/'output.json'))
  sections.append(section)
  qtext=f"# {cid}\n\n## 1. 실행 메타\n\nrun-001 / v33 / Gemini 실제 호출.\n\n## 2. 사용자 질문 원문\n\n한 번의 토큰 초과와 장문 처리 여부를 내규 목업으로 확인. 외부 반출 허용, Gemini 실험 요청.\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n"+block(c['expected_parents'])
  qtext+='\n## 4. 제품 입력을 구성한 원값\n\n### 회수·탈락 단계 원장 — run·arm별\n\n검색 없음. 모의 PDF·blocks는 artifacts/dataset, 아래 provider 요청은 실제 전송 원문. 정답은 전송하지 않았다.\n'
  qtext+='\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n'+section+'\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n위 기록이 모든 제품 호출이다. baseline은 동일한 파싱 블록으로 기본 엔진을 새로 실행했다. 별도 judge 호출 없음.\n\n## 7. 채점 호출과 반복 판정\n\n조문·원문자 항목의 원문상 직접 부모를 독립 정답과 exact 비교, 모든 제품 호출 종료 후 채점. 각1회.\n\n## 8. 사례 최종 판정\n'+block({k:c.get(k) for k in ['pass','final_correct','false_visual_approval','error','source_unchanged','replay_identical','cache_calls']})
  (ADR/'실험'/q['file']).write_text(qtext)
 totals={k:sum(x[k] for x in rows) for k in ['input_tokens','output_tokens','text_tokens','image_tokens','cached_input_tokens']};totals.update(calls=len(rows),passed=sum(bool(c['pass']) for c in r['cases']),documents=len(r['cases']),seconds=r['seconds'],false_approvals=sum(c['false_visual_approval'] for c in r['cases']),body_checks=sum('-body-review' in x['phase'] for x in rows),reinspections=sum('-reconsider-' in x['phase'] and '-vlm-review' in x['phase'] for x in rows),cutoffs=sum(x['finish']=='MAX_TOKENS' for x in rows))
 write(ART/'token-audit.json',{'totals':totals,'calls':rows})
 header='# 내규 목업5종 — 실제 Gemini 토큰·시간·입력·출력\n\n'+block(totals)+'\n'+(ART/'interpretation.md').read_text()+'\n\n이미지 base64만 이미지로 표시했다. system/user/스키마/응답은 생략 없이 기록했다. 키/인증 헤더 없음.\n'
 (ADR/'GEMINI_INPUT_OUTPUT_AUDIT.md').write_text(header+'\n'+(ART/'summary-table.md').read_text()+''.join(sections))
 m['runs'][0].update(status='complete',sha256=sha(ART/'results.json'))
 m['results']={'status':'complete','by_arm':{'baseline':{'anchor_parent_correct':sum(c['baseline_correct'] for c in r['cases']),'total':len(r['cases']),'model_calls':0,'scope':'article and circled anchors only; not a claim of valid full spans/tree'},'v33':{'final_pipeline_pass':totals['passed'],'total':len(r['cases'])}},'comparisons':[{'case':c['case_id'],'baseline_anchor_correct':c['baseline_correct'],'candidate_pass':c['pass']} for c in r['cases']],'judge_disagreements':None,'usage':totals,'latency':{'seconds':r['seconds']},'error_taxonomy':['other:decimal_body_text_misclassified_as_heading','other:invalid_zero_length_span','other:body_visual_disagreement','other:visual_block_reference_drift']}
 write(ADR/'실험/manifest.json',m)
 manifest=read(ART/'manifest.json');files=[p for p in ART.rglob('*') if p.is_file() and p.name!='manifest.json']+[ADR/'GEMINI_INPUT_OUTPUT_AUDIT.md',Path(__file__),Path(__file__).with_name('run_audit.py')]+[ROOT/p for p in read(ART/'freeze.json')['files']]
 manifest['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen experiment source, provider IO or audit report','contains_raw_prompts_and_outputs':p.name in ['request.json','response.json','GEMINI_INPUT_OUTPUT_AUDIT.md']} for p in sorted(set(files))];write(ART/'manifest.json',manifest)
 print(json.dumps(totals))
if __name__=='__main__':main()
