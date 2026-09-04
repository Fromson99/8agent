/* 배치 파이프라인 화면 — 라인업(무엇이 빠졌나)을 표로 보이고, 딸깍 한 번으로
 * 빠진 것만 순서대로 돌리며, 진행을 2초마다 그린다.
 *
 * 라인업은 서버가 센다(/v1/pipeline/lineup) — 화면은 그 수를 그리고, 실행 중에는
 * /v1/pipeline/status 의 단계별 done/total 로 막대를 채운다. 단계 줄의 "이것만"은
 * 그 단계 하나만 돌린다(디버깅·재시도). 모델(LLM·임베딩)이 없으면 그 단계는 건너뛰고
 * 이유가 note 에 남는다 — 실패가 아니다.
 */
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const S = { lineup: null, status: null, timer: null, runId: null, events: [] };

async function api(path, body) {
  const r = await fetch(path, body ? { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return r.json();
}

/* ---------------------------------------------------------------- 라인업 */
async function loadLineup() {
  $("summary").textContent = "라인업 세는 중…";
  try {
    S.lineup = await api("/v1/pipeline/lineup");
  } catch (e) {
    $("summary").textContent = "라인업 실패: " + e.message;
    return;
  }
  const L = S.lineup;
  const pend = L.order.reduce((n, k) => n + ((L.stages[k] || {}).pending || 0), 0);
  $("summary").textContent = `문서 ${L.documents} · 빠진 단계 항목 ${pend}`;
  $("models").innerHTML =
    `<span class="pill ${L.llm ? "on" : "off"}" title="프레임 단계가 쓴다">LLM ${L.llm ? "있음" : "없음"}</span>
     <span class="pill ${L.embedding ? "on" : "off"}" title="벡터 단계가 쓴다">임베딩 ${L.embedding ? "있음" : "없음"}</span>`;
  renderStages();
}

function stageRow(key) {
  const L = S.lineup, lu = (L.stages[key] || {}), st = ((S.status || {}).stages || {})[key] || {};
  const running = S.status && S.status.running;
  const label = L.labels[key] || key, kind = L.kinds[key] || "";
  const needModel = (key === "frames" && !L.llm) || (key === "embed" && !L.embedding);
  const pct = st.total ? Math.round(100 * (st.done || 0) / st.total) : (st.status === "done" ? 100 : 0);
  const units = lu.units ? (lu.units.pending != null ? `조 ${lu.units.pending.toLocaleString()}/${lu.units.total.toLocaleString()}`
                                                    : `구역 ${lu.units.fresh.toLocaleString()}/${lu.units.total.toLocaleString()}`) : "";
  const stateCls = st.status || "idle";
  const stateTxt = { queued: "대기", running: "실행 중", done: "완료", failed: "실패",
                     skipped: "건너뜀", stopped: "중지", idle: "" }[stateCls] || stateCls;
  return `
  <div class="stage ${stateCls} ${lu.pending ? "has" : "clean"}" data-stage="${key}">
    <div class="head">
      <span class="idx">${L.order.indexOf(key) + 1}</span>
      <b class="label">${esc(label)}</b>
      <span class="kind ${kind}">${esc(kind)}</span>
      ${needModel ? `<span class="pill off" title="모델이 없어 이 단계는 건너뛴다">모델 없음</span>` : ""}
      <span class="grow"></span>
      <span class="pending ${lu.pending ? "warn" : "ok"}" title="빠진 것 / 전체">
        ${lu.pending ? `빠짐 ${lu.pending}` : "빠짐 0"} / ${lu.total ?? "?"}${units ? ` · ${units}` : ""}</span>
      ${(lu.detail || []).length ? `<button class="ghost small" data-detail="${key}">목록</button>` : ""}
      <button class="ghost small" data-run="${key}" ${running ? "disabled" : ""}>이것만</button>
    </div>
    <div class="note">${esc(lu.note || "")}</div>
    <div class="bar"><div class="fill" style="width:${pct}%"></div></div>
    <div class="prog">
      <span class="state">${esc(stateTxt)}</span>
      ${st.total ? `<span>${(st.done || 0).toLocaleString()} / ${st.total.toLocaleString()}</span>` : ""}
      ${st.current ? `<span class="cur">${esc(st.current)}</span>` : ""}
      ${st.note && st.status && st.status !== "queued" ? `<span class="res">${esc(st.note)}</span>` : ""}
      ${(st.errors || []).length ? `<span class="err">오류 ${st.errors.length}: ${esc(st.errors[st.errors.length - 1])}</span>` : ""}
    </div>
  </div>`;
}

function renderStages() {
  if (!S.lineup) return;
  $("stages").innerHTML = S.lineup.order.map(stageRow).join("");
  document.querySelectorAll("[data-detail]").forEach((b) => b.onclick = () => showDetail(b.dataset.detail));
  document.querySelectorAll("[data-run]").forEach((b) => b.onclick = () => run([b.dataset.run]));
}

function showDetail(key) {
  const lu = S.lineup.stages[key] || {};
  $("detailTitle").textContent = `${S.lineup.labels[key]} — 빠진 목록 ${(lu.detail || []).length}`;
  const rows = (lu.detail || []).map((d) => {
    const extra = Object.entries(d).filter(([k]) => k !== "name" && k !== "doc_id")
      .map(([k, v]) => `${k}=${Array.isArray(v) ? v.join(",") : v}`).join(" · ");
    return `<div class="drow"><span>${esc(d.name || "")}</span><span class="sub">${esc(extra)}</span></div>`;
  });
  $("detailBody").innerHTML = rows.join("") || "<div class='sub'>없음</div>";
  $("detail").classList.remove("hidden");
  $("detail").scrollIntoView({ behavior: "smooth", block: "nearest" });
}
$("detailClose").onclick = () => $("detail").classList.add("hidden");

/* ---------------------------------------------------------------- 실행 */
async function run(stages) {
  const all = !stages;
  if (all && !confirm("빠진 것만 순서대로 전부 돌립니다 — 투입 → 위임 → 용어 → 프레임(LLM) → 벡터 → 점검.\n"
                      + "LLM·임베딩은 시간이 걸립니다(분~시간). 진행은 이 화면에서 보입니다. 시작할까요?")) return;
  try {
    const r = await api("/v1/pipeline/run", { stages: stages || null });
    S.runId = r.run_id;
    $("log").textContent = "";
    startPolling();
  } catch (e) {
    alert("실행 실패: " + e.message);
  }
}
$("runBtn").onclick = () => run(null);
$("stopBtn").onclick = async () => { try { await api("/v1/pipeline/stop", {}); } catch (e) { alert(e.message); } };
$("refreshBtn").onclick = loadLineup;

function fmtDur(a, b) {
  if (!a) return "";
  const ms = (b ? new Date(b) : new Date()) - new Date(a);
  const s = Math.floor(ms / 1000);
  return s < 60 ? `${s}s` : s < 3600 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}

async function poll() {
  let st;
  try { st = await api("/v1/pipeline/status"); } catch { return; }
  S.status = st;
  const running = !!st.running;
  $("stopBtn").classList.toggle("hidden", !running);
  $("runBtn").disabled = running;
  if (st.run_id) {
    S.runId = st.run_id;
    $("runPane").classList.remove("hidden");
    $("runTitle").textContent = `실행 ${st.run_id}` + (st.owner === "other-process" ? " (CLI 프로세스)" : "");
    $("runState").textContent = running ? "실행 중" : st.stale ? "끊김(프로세스 죽음)"
      : ({ done: "완료", failed: "실패", stopped: "중지" }[st.status] || st.status);
    $("runState").className = "state " + (running ? "running" : st.stale ? "failed" : st.status);
    $("runTime").textContent = `${st.started ? st.started.replace("T", " ").slice(0, 19) : ""} · ${fmtDur(st.started, st.finished)}`;
    const doneStages = Object.values(st.stages || {}).filter((s) => s.status === "done").length;
    $("runNote").textContent = `요청 단계 ${(st.requested || []).join(" → ")} · 완료 ${doneStages}`;
  }
  renderStages();
  renderDocs();
  if (S.runId) {
    try {
      const lg = await api(`/v1/pipeline/runs/${S.runId}/log?n=1500`);
      S.events = lg.events || [];
      renderLog();
    } catch {}
  }
  if (!running && S.timer) {
    clearInterval(S.timer); S.timer = null;
    loadLineup();                          // 끝나면 라인업을 다시 센다 — 빠진 것이 줄었는지 보인다
    loadRuns();
  }
}

function startPolling() {
  if (S.timer) clearInterval(S.timer);
  poll();
  S.timer = setInterval(poll, 2000);
}

async function loadRuns() {
  try {
    const r = await api("/v1/pipeline/runs?limit=12");
    $("runs").innerHTML = (r.runs || []).map((x) => {
      const st = Object.entries(x.stages || {}).filter(([, s]) => s.status && s.status !== "skipped" || false)
        .map(([k, s]) => `<span class="mini ${s.status}" title="${esc(s.note || "")}">${esc(k)}</span>`).join("");
      return `<div class="rrow"><span class="rid">${esc(x.run_id)}</span>
        <span class="state ${x.status}">${esc(x.status)}</span>
        <span class="sub">${fmtDur(x.started, x.finished)}</span><span class="minis">${st}</span></div>`;
    }).join("") || "<div class='sub'>아직 실행한 적 없음</div>";
  } catch {}
}

/* ---------------------------------------------------------------- 로그·문서 표 */
function renderLog() {
  const stage = $("logStage").value, q = ($("logFilter").value || "").trim();
  const rows = S.events.filter((e) => (!stage || (e.stage === stage || (e.kind || "").startsWith(stage + "_")))
    && (!q || JSON.stringify(e).includes(q)));
  $("log").textContent = rows.map((e) => {
    const { ts, kind, ...rest } = e;
    const head = rest.doc ? `${rest.doc}` : (rest.stage || "");
    delete rest.doc;
    return `${(ts || "").slice(11, 19)}  ${(kind || "").padEnd(15)} ${head.padEnd(28).slice(0, 28)} ${JSON.stringify(rest).slice(0, 200)}`;
  }).join("\n");
  $("logMeta").textContent = `${rows.length}/${S.events.length}줄`;
  if ($("logFollow").checked) $("log").scrollTop = $("log").scrollHeight;
  // 단계 목록 — 사건에서 뽑는다
  const stages = [...new Set(S.events.map((e) => e.stage || (e.kind || "").split("_")[0]).filter(Boolean))];
  const sel = $("logStage");
  if (sel.options.length - 1 !== stages.length) {
    const cur = sel.value;
    sel.innerHTML = `<option value="">전부</option>` + stages.map((s) => `<option value="${esc(s)}">${esc((S.lineup && S.lineup.labels[s]) || s)}</option>`).join("");
    sel.value = cur;
  }
}
$("logStage").onchange = renderLog;
$("logFilter").oninput = renderLog;

const DOC_COLS = {
  ingest: ["via", "folder", "kind", "score", "tier", "structured_by", "pages", "sec", "error"],
  structure: ["folder", "kind", "score", "tier", "structured_by", "quarantined"],
  terms: ["terms"],
  frames: ["jos", "frames", "errors", "sec"],
  embed: ["fresh", "sections"],
};
function renderDocs() {
  const st = S.status || {};
  const stages = Object.entries(st.stages || {}).filter(([, s]) => (s.docs || []).length);
  const sel = $("docsStage");
  if (sel.options.length !== stages.length) {
    const cur = sel.value;
    sel.innerHTML = stages.map(([k, s]) => `<option value="${k}">${esc((S.lineup && S.lineup.labels[k]) || k)} (${s.docs.length})</option>`).join("");
    if ([...sel.options].some((o) => o.value === cur)) sel.value = cur;
  }
  const key = sel.value;
  const rows = key && st.stages && st.stages[key] ? st.stages[key].docs : [];
  const q = ($("docsFilter").value || "").trim();
  const cols = DOC_COLS[key] || [];
  const shown = rows.filter((r) => !q || (r.doc || "").includes(q)).slice(-400).reverse();
  $("docsMeta").textContent = rows.length ? `${shown.length}/${rows.length}` : "아직 기록 없음";
  $("docsTable").innerHTML = rows.length ? `<table><thead><tr><th>시각</th><th>문서</th>${cols.map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>` +
    shown.map((r) => `<tr class="${r.ok === false || r.quarantined ? "bad" : ""}"><td class="sub">${esc((r.ts || "").slice(11, 19))}</td>
      <td><a href="/structure/?doc=${esc(r.doc_id || "")}" target="_blank">${esc(r.doc || "")}</a></td>` +
      cols.map((c) => `<td>${esc(r[c] == null ? "" : (typeof r[c] === "number" && c === "score" ? r[c].toFixed(2) : r[c]))}</td>`).join("") + "</tr>").join("") +
    "</tbody></table>" : "";
}
$("docsStage").onchange = renderDocs;
$("docsFilter").oninput = renderDocs;

/* ---------------------------------------------------------------- 시작 */
(async () => {
  await loadLineup();
  await loadRuns();
  const st = await api("/v1/pipeline/status").catch(() => null);
  if (st && st.running) startPolling(); else if (st && st.run_id) { S.status = st; S.runId = st.run_id; poll(); }
})();
