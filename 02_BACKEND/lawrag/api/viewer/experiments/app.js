(function(){
"use strict";
const $=(s)=>document.querySelector(s),state={data:null,module:"",selected:""};
const esc=(v)=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt=(v)=>Number(v||0).toLocaleString("ko-KR");
const when=(v)=>{const d=new Date(Number(v)*1000);return Number.isNaN(d.getTime())?"—":new Intl.DateTimeFormat("ko-KR",{month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"}).format(d)};
async function api(url){const r=await fetch(url);if(!r.ok)throw new Error(`${r.status} ${await r.text()}`);return r.json()}
function statusClass(v){return v==="기각"?"rejected":v==="진행 중"?"active":""}
async function load(){
  $("#reloadBtn").disabled=true;$("#status").textContent="실험 정본 읽는 중";
  try{state.data=await api("/v1/experiments/catalog");const d=state.data;
    $("#moduleCount").textContent=fmt(d.module_count);$("#groupCount").textContent=fmt(d.experiment_count);$("#artifactCount").textContent=fmt(d.artifact_count);
    $("#cmCount").textContent=fmt(d.artifacts.filter(x=>x.name.startsWith("cm_")).length);$("#status").textContent=`모듈 ${d.module_count} · 실험 ${d.experiment_count} · 산출물 ${d.artifact_count}`;
    renderModules();renderArtifacts();
  }catch(e){$("#status").textContent=`연결 실패 · ${e.message}`;$("#artifacts").innerHTML=`<div class="list-empty">${esc(e.message)}</div>`}
  finally{$("#reloadBtn").disabled=false}
}
function renderModules(){
  const box=$("#modules");box.innerHTML=state.data.modules.map(m=>`<button class="module-card${state.module===m.key?" on":""}" data-key="${esc(m.key)}"><div class="top"><span class="section-code">${esc(m.key)}</span><span class="state ${statusClass(m.status)}">${esc(m.status)}</span></div><h3>${esc(m.title)}</h3><p>${esc(m.purpose)}</p><footer><span>${esc(m.decision)}</span><b>산출물 ${fmt(m.artifact_count)}</b></footer></button>`).join("");
  box.querySelectorAll(".module-card").forEach(b=>b.onclick=()=>{state.module=state.module===b.dataset.key?"":b.dataset.key;renderModules();renderArtifacts()});
}
function filtered(){const q=$("#query").value.trim().toLowerCase(),kind=$("#kind").value;return(state.data?.artifacts||[]).filter(a=>(!state.module||a.module_key===state.module)&&(!kind||a.kind===kind)&&(!q||`${a.name} ${a.experiment} ${a.path}`.toLowerCase().includes(q)))}
function renderArtifacts(){
  const rows=filtered(),box=$("#artifacts");$("#visibleCount").textContent=fmt(rows.length);
  const af=$("#activeFilter");af.classList.toggle("hidden",!state.module);af.textContent=state.module?`모듈 필터 · ${state.module} ×`:"";af.onclick=()=>{state.module="";renderModules();renderArtifacts()};
  box.innerHTML=rows.map(a=>`<button class="artifact-row${state.selected===a.path?" on":""}" data-path="${esc(a.path)}"><div class="row-top"><span class="kind">${esc(a.kind)}</span><span class="date">${esc(when(a.updated_at))}</span></div><strong>${esc(a.experiment)}</strong><small>${esc(a.name)} · ${fmt(a.case_count)} cases</small></button>`).join("")||'<div class="list-empty">조건에 맞는 산출물이 없습니다.</div>';
  box.querySelectorAll(".artifact-row").forEach(b=>b.onclick=()=>openArtifact(b.dataset.path));
}
function previewRows(rows){if(!rows.length)return'<div class="list-empty">대표 문항이 없는 요약 산출물입니다.</div>';return`<div class="preview-list">${rows.map((r,i)=>{const id=r.id||r.case_no||`row-${i+1}`,q=r.question||r.source_question||r.label||r.reason||"";return`<div class="preview-row"><b>${esc(id)}</b><span>${esc(String(q).slice(0,260)||JSON.stringify(r).slice(0,260))}</span></div>`}).join("")}</div>`}
async function openArtifact(path){state.selected=path;renderArtifacts();const box=$("#artifactDetail");box.innerHTML='<div class="detail-empty"><span class="section-code">LOADING</span><h2>산출물 읽는 중</h2></div>';
  try{const d=await api(`/v1/experiments/artifact?path=${encodeURIComponent(path)}`),a=d.artifact;
    box.innerHTML=`<header class="detail-head"><div class="badges"><span>${esc(a.kind)}</span><span>${fmt(a.case_count)} CASES</span>${a.module_key?`<span>${esc(a.module_key)}</span>`:""}</div><h2>${esc(a.experiment)}</h2><p>${esc(a.path)} · ${(a.size/1024).toFixed(1)} KB · ${esc(when(a.updated_at))}</p></header><div class="metric-grid">${(a.metrics||[]).map(m=>`<div class="metric"><span>${esc(m.key)}</span><b>${esc(m.value)}</b></div>`).join("")||'<div class="metric"><span>SUMMARY</span><b>구조형 결과</b></div>'}</div><section class="detail-section"><h3>실행 설정</h3><pre class="json-view">${esc(JSON.stringify(d.configuration,null,2))}</pre></section><section class="detail-section"><h3>요약 원문</h3><pre class="json-view">${esc(JSON.stringify(d.summary,null,2))}</pre></section><section class="detail-section"><h3>대표 문항 · 최대 12건</h3>${previewRows(d.rows_preview||[])}</section>`;
  }catch(e){box.innerHTML=`<div class="detail-empty"><span class="section-code">READ ERROR</span><h2>산출물을 읽지 못했습니다</h2><p>${esc(e.message)}</p></div>`}
}
$("#query").addEventListener("input",renderArtifacts);$("#kind").addEventListener("change",renderArtifacts);$("#reloadBtn").addEventListener("click",load);
const initial=new URLSearchParams(location.search).get("q")||"";$("#query").value=initial;load();
})();
