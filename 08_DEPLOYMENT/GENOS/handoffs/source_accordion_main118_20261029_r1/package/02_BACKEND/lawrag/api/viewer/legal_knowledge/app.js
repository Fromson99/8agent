/* No credentials, knowledge text or operation payloads are stored in the browser. */
'use strict';
const $ = id => document.getElementById(id);
let selected=null, build=null, status=null, nextCursor=null, lastCommand=null, advanced=null;
const show=(message,value)=>{$('message').textContent=message;$('result').textContent=value?JSON.stringify(value,null,2):'';};
async function api(path, body){
  const response=await fetch('/v1/legal-knowledge'+path,{method:body?'POST':'GET',credentials:'same-origin',headers:body?{'Content-Type':'application/json','X-Knowledge-Request':'1'}:{},body:body?JSON.stringify(body):undefined});
  const value=await response.json();
  if(!response.ok)throw new Error((value.message||'요청을 처리하지 못했습니다.')+(value.code?' ['+value.code+']':''));
  return value;
}
async function run(action){
  const buttons=[...document.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
  try{await action();}catch(error){show(error.message);}finally{buttons.forEach(b=>b.disabled=false);permissions();}
}
function permissions(){
  if(!status)return;
  const roles=status.roles;
  for(const id of ['save','send-feedback'])$(id).disabled=!roles.includes('edit');
  for(const id of ['prepare','publish','rollback','retire'])$(id).disabled=!roles.includes('publish');
}
async function refreshStatus(){status=await api('/status');$('connection').textContent=status.team_id+' · '+(status.publication_status==='PUBLISHED'?'게시됨':'미게시 / 사용 중지')+' · 질문 적용 '+status.consumer_mode;$('generation').value=status.source_binding.generation;$('source-hash').value=status.source_binding.store_sha256;$('index-hash').value=status.source_binding.unit_index_sha256||'';}
function fill(record){
  selected=record;advanced=null;build=null;
  const d=record?.definition;
  $('kind').value=d?.kind||'METHOD';$('kind').disabled=!!record;
  $('heading').textContent=d?.title||'새 검토 방법';$('version').textContent=record?'저장 버전 '+record.revision:'새 초안';
  $('title').value=d?.title||'';$('description').value=d?.description||'';$('business').value=d?.scope.business.values.join(', ')||'';
  $('business-mode').value=d?.scope.business.mode||'UNSPECIFIED';
  $('terms').value=d?.lookup_terms.join(', ')||'';$('steps').value=d?.content.steps?.map(s=>s.label).join('\n')||'';
  $('steps').disabled=!!d&&d.kind!=='METHOD';$('definition').value=d?JSON.stringify(d,null,2):'';
}
function definition(){
  const d=(advanced||selected)?structuredClone(advanced||selected.definition):{schema_version:'legal-knowledge-v1',kind:'METHOD',source_refs:[],dependencies:[],effective_from:null,effective_to:null,scope:Object.fromEntries(['business','product','role','action','jurisdiction'].map(k=>[k,{mode:'UNSPECIFIED',values:[]}])),content:{purpose:'',requested_outputs:[],inputs:[],evidence_needs:[],steps:[],policies:[]}};
  d.title=$('title').value.trim();d.description=$('description').value.trim();d.lookup_terms=$('terms').value.split(',').map(x=>x.trim()).filter(Boolean);
  const business=$('business').value.split(',').map(x=>x.trim()).filter(Boolean);d.scope.business={mode:$('business-mode').value,values:business};
  if(d.kind==='METHOD'){
    d.content.purpose=d.description;
    const labels=$('steps').value.split('\n').map(x=>x.trim()).filter(Boolean);
    // Preserve IDs/relationships of existing rows. Structural edits need explicit review.
    d.content.steps=labels.map((label,i)=>({...d.content.steps[i]||{id:'step-'+(i+1),capability:'READ_SOURCE',after:[]},label}));
  }
  return d;
}
function reference(){if(!selected)throw new Error('먼저 저장한 항목을 선택해 주세요.');return {kind:selected.definition.kind,id:selected.id,revision:selected.revision,content_hash:selected.content_hash};}
async function command(operation,args){
  lastCommand={schema_version:'legal-knowledge-v1',operation,operation_id:crypto.randomUUID(),arguments:args};
  return api('/commands',lastCommand);
}
async function list(append=false){
  const page=await api('/objects?namespace='+encodeURIComponent($('namespace').value)+(append&&nextCursor?'&cursor='+encodeURIComponent(nextCursor):''));
  if(!append)$('list').replaceChildren();
  for(const row of page.items){
    const button=document.createElement('button');button.textContent=row.definition?.title||row.review_note||row.reason||row.status;
    const caption=document.createElement('small');caption.textContent=(row.definition?.kind||row.status)+' · 버전 '+row.revision;button.append(caption);
    button.onclick=()=>{if(row.definition)fill(row);else{build=row.namespace==='release'?row:null;show('선택한 기록',row);}};$('list').append(button);
  }
  nextCursor=page.next_cursor;$('more').hidden=!nextCursor;
}
$('new').onclick=()=>{fill(null);show('새 초안을 작성해 주세요.');};
$('business').oninput=()=>{if($('business').value.trim())$('business-mode').value='VALUES';};
$('kind').onchange=()=>{
  const kind=$('kind').value;const d=definition();d.kind=kind;
  const target={kind:'WIKI',id:'선택할-기존-ID',revision:1,content_hash:''};
  const templates={FIELD:{value_type:'money',dimension:'KRW',legal_purpose:'',concept_refs:[],allowed_origins:['USER','SOURCE']},APPLICATION:{method_refs:[],wiki_refs:[],condition:{literal:{type:'boolean',value:true,unit:''}},input_refs:[],requested_outputs:[]},WIKI_LINK:{target,evidence_role:'원문 탐색 경로',reuse_capability:'LOCATION',application_refs:[]},SHORTCUT_LINK:{target:{...target,kind:'SHORTCUT'},application_refs:[]}};
  if(kind==='METHOD'){advanced=null;return;}
  d.content=templates[kind];advanced=d;$('definition').value=JSON.stringify(d,null,2);document.querySelector('#editor details').open=true;
  show('이 종류의 연결·입력 항목은 고급 편집에서 작성한 뒤 “고급 편집 내용 사용”을 눌러 주세요.');
};
$('namespace').onchange=()=>run(()=>list());$('more').onclick=()=>run(()=>list(true));
$('apply-json').onclick=()=>run(async()=>{advanced=JSON.parse($('definition').value);$('title').value=advanced.title;$('description').value=advanced.description;$('business').value=advanced.scope.business.values.join(', ');$('business-mode').value=advanced.scope.business.mode;$('terms').value=advanced.lookup_terms.join(', ');$('steps').value=advanced.content.steps?.map(s=>s.label).join('\n')||'';show('고급 편집 내용이 다음 저장에 사용됩니다.');});
$('editor').onsubmit=event=>{event.preventDefault();run(async()=>{const value=await command('save_draft',{object_id:selected?.id||null,expected_revision:selected?.revision||0,definition:definition()});fill(value);show('초안이 저장되었습니다. 게시 버전은 유지됩니다.',value);await list();});};
$('impact').onclick=()=>run(async()=>show('현재 게시 묶음의 직접 연결 영향',await api('/impact',reference())));
$('prepare').onclick=()=>run(async()=>{build=await command('prepare_publication',{refs:[reference()],source_binding:{generation:$('generation').value.trim(),store_sha256:$('source-hash').value.trim(),unit_index_sha256:$('index-hash').value.trim()||null},review_note:$('review-note').value.trim()});show('게시 준비가 완료되었습니다. 준비한 버전과 포함 항목을 확인해 주세요.',build);});
for(const operation of ['publish','rollback'])$(operation).onclick=()=>run(async()=>{
  if(!build)throw new Error('준비된 게시 버전 또는 게시 이력을 선택해 주세요.');
  const args={build_id:build.id,build_hash:build.content_hash,expected_revision:status.channel_revision};
  if(operation==='rollback')args.reason=$('review-note').value.trim();
  const value=await command(operation,args);await refreshStatus();show('게시 선택이 변경되었습니다.',value);
});
$('retire').onclick=()=>run(async()=>{const value=await command('retire',{expected_revision:status.channel_revision,reason:$('review-note').value.trim()});await refreshStatus();show('게시 지식의 사용을 중지했습니다.',value);});
$('send-feedback').onclick=()=>run(async()=>show('수정 의견을 후보로 등록했습니다.',await command('feedback',{target:reference(),request_ref:$('request-ref').value.trim(),reason:$('feedback').value.trim()})));
$('check-operation').onclick=()=>run(async()=>{if(!lastCommand)throw new Error('이번 화면에서 보낸 작업이 없습니다.');show('작업 처리 상태',await api('/operations/'+encodeURIComponent(lastCommand.operation_id)));await refreshStatus();});
run(async()=>{await refreshStatus();await list();});
