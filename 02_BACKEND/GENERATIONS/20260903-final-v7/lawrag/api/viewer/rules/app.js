/* 공리 루프 화면 — 규칙의 생애(잠정 → 규칙 → 정착 AXIOM)를 공간으로 그린다.
 *
 * 사다리의 각 단은 상태이고, 단 사이 화살표가 곧 규율이다: 잠정→규칙은
 * 자동(replay 녹색), 규칙→정착은 사람만(의심의 방향을 뒤집는 결정).
 * 카드의 4기준 게이지가 "규칙이 공리로 변해가는 과정"의 그림이다 —
 * 서버 보고서(promotable)가 정본이고 게이지는 그 시각 표현일 뿐이다.
 */
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const S = { data: null, sel: null };

async function api(path, opts) {
  const r = await fetch(path, opts ? { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(opts) } : undefined);
  if (!r.ok) throw new Error((await r.text()).slice(0, 300));
  return r.json();
}

async function load() {
  S.data = await api("/v1/rag/rules");
  render();
  loadSwitches();
}

/* 귀납 버튼은 상단바에 늘 있다 — 규칙이 생긴 뒤에야 "한 바퀴 더"가 필요하다 */
$("induceBtn").onclick = induce;

/* ── 엔진 규칙 스위치 — 해소(선언·본문우선·추정)와 회수(동반·항해)의 자동
 * 규칙 등록부. 규칙은 코드가 갖고 있지만 켜짐/꺼짐은 사용자 소유다.
 * 끄면 다음 질의부터: 확정 규칙의 간선은 보류로, 동반 규칙은 회수에서 빠진다. */
async function loadSwitches() {
  let sw;
  try { sw = (await api("/v1/rag/switches")).switches; } catch { return; }
  const box = $("engineSwitches");
  const by = {};
  sw.forEach((s) => (by[s["자리"]] = by[s["자리"]] || []).push(s));
  box.innerHTML = Object.entries(by).map(([grp, rows]) =>
    `<span class="grp">${esc(grp)}</span>` + rows.map((s) =>
      `<label class="sw ${s.on ? "on" : ""}" title="${esc(s["설명"])}">
         <input type="checkbox" data-k="${esc(s.key)}" ${s.on ? "checked" : ""}>
         ${esc(s["이름"])}</label>`).join("")).join("");
  box.classList.remove("hidden");
  box.querySelectorAll("input").forEach((el) => {
    el.onchange = async () => {
      await api("/v1/rag/switches", { key: el.dataset.k, on: el.checked });
      loadSwitches();
    };
  });
}

/* ── 게이지 값 — 서버 4기준 보고서의 시각화(정본은 권고 문구다) ── */
function gauges(rep) {
  const 성 = rep["성숙"] || {}, 안 = rep["안정"] || {},
        하 = rep["하중"] || {}, 부 = rep["부검"] || {};
  const g = [];
  g.push(["성숙", Math.min(1, (성["발동"] || 0) / 6) * ((성["스코프"] || 0) >= 2 ? 1 : 0.5)]);
  g.push(["안정", Math.max(0.15, 1 - (안["예외술어"] || 0) * 0.3)]);
  g.push(["하중", Math.min(1, ((하["근거사례"] || 0) + (하["확정"] || 0)) / 6)]);
  const j = (부["확정"] || 0) + (부["뒤집힘"] || 0);
  g.push(["부검", j ? (부["확정"] || 0) / j : 0.25]);
  return g;
}

function card(r) {
  const rep = r["보고서"] || {}, st = r["실적"] || {};
  const reco = rep["권고"] || "";
  const go = reco === "정착 후보";
  const when = Object.entries(r.when || {})
    .map(([k, v]) => `<span>${esc(k)}=${esc(v)}</span>`).join("");
  const bars = gauges(rep).map(([k, v]) => `
      <label>${k}</label>
      <div class="bar ${v >= 1 ? "full" : ""}"><i style="width:${Math.round(v * 100)}%"></i></div>`).join("");
  return `
  <div class="card ${S.sel === r.id ? "sel" : ""}" data-id="${esc(r.id)}">
    <div class="top"><span class="rid">${esc(r.id)}</span>
      <span class="reco ${go ? "go" : ""}" title="promotable 4기준 판정">${esc(reco)}</span></div>
    <div class="rat">${esc(r.rationale || "")}</div>
    <div class="whenchips">${when}</div>
    <div class="nums">
      <span>발동 <b>${st["발동"] || 0}</b></span>
      <span>그림자 <b>${st["그림자"] || 0}</b></span>
      <span>스코프 <b>${st["발동스코프"] ?? st["scopes"] ?? 0}</b></span>
      <span class="bad">뒤집힘 <b>${st["뒤집힘"] || 0}</b></span>
    </div>
    <div class="gauges">${bars}</div>
  </div>`;
}

function render() {
  const d = S.data, rules = d.rules || [];
  /* 상단 — 유효 모드는 색이 곧 상태다 */
  const m = d.mode;
  const pill = $("modePill");
  pill.textContent = m === "on" ? "발동 on" : m === "shadow" ? "그림자 shadow" : "꺼짐 off";
  pill.className = "mode " + (m === "on" ? "on" : m === "shadow" ? "shadow" : "off");
  pill.title = `env=${d.env} · 차단기=${(d.breaker || {}).state || "정상"}`;
  $("summary").textContent =
    `규칙 ${rules.length} · 발동 ${rules.filter((r) => ["규칙", "정착"].includes(r.status)).length}`;

  /* 차단기 — 강하는 사고다. 배너로 올리고 해제(사람)만 남긴다 */
  const br = d.breaker || {};
  const bn = $("breaker");
  if (br.state === "강하") {
    bn.classList.remove("hidden");
    bn.innerHTML = `⚡ 차단기 강하 — ${esc(br.reason || "")}
      <button id="brReset">해제 (사람 결정 — shadow→on 복귀)</button>`;
    $("brReset").onclick = async () => {
      if (!confirm("차단기를 해제합니까? 강하의 원인이 해소됐다는 판단은 사람 몫입니다."))
        return;
      await api("/v1/rag/rules/breaker", { action: "해제", note: "화면에서 해제" });
      load();
    };
  } else bn.classList.add("hidden");

  const ov = d["중첩"] || [];
  const on = $("overlapNote");
  if (ov.length) {
    on.classList.remove("hidden");
    on.textContent = "규칙 중첩 — " + ov.map(([a, b]) => `${a} ⊂ ${b}`).join(" · ")
      + " (좁은 쪽이 먼저 평가됩니다)";
  } else on.classList.add("hidden");

  /* 사다리 배치 — 상태가 곧 자리다 */
  const cols = { "잠정": [], "규칙": [], "정착": [] };
  const parked = [];
  for (const r of rules)
    (cols[r.status] ? cols[r.status] : parked).push(r);
  for (const [k, arr] of Object.entries(cols)) {
    const col = document.querySelector(`.stage[data-col="${k}"]`);
    col.querySelector(".n").textContent = arr.length || "";
    col.querySelector(".cards").innerHTML =
      arr.map(card).join("") || `<p class="hint">—</p>`;
  }
  $("nParked").textContent = parked.length || "";
  $("parkedCards").innerHTML = parked.map(card).join("") || `<p class="hint">—</p>`;

  document.querySelectorAll(".card").forEach((el) => {
    el.onclick = () => { S.sel = el.dataset.id; render(); detail(); };
  });

  $("empty").classList.toggle("hidden", rules.length > 0);
  if (S.sel && !rules.some((r) => r.id === S.sel)) S.sel = null;
  if (!S.sel) $("detail").classList.add("hidden");
}

async function induce() {
  $("induceBtn").disabled = true;
  try {
    const out = await api("/v1/rag/rules/induce", {});
    $("induceOut").classList.remove("hidden");
    $("induceOut").textContent = JSON.stringify(out, null, 2);
    await load();
  } catch (e) { alert("귀납 실패: " + e.message); }
  $("induceBtn").disabled = false;
}

/* ── 상세 — 여정 타임라인 + 적중 원장(부검) ───────────────── */
async function detail() {
  const r = (S.data.rules || []).find((x) => x.id === S.sel);
  if (!r) return;
  const box = $("detail");
  box.classList.remove("hidden");
  box.innerHTML = `<h2>${esc(r.id)} — ${esc(r.rationale || "")}</h2><p class="hint">불러오는 중…</p>`;
  const led = await api(`/v1/rag/rules/hits?rule=${encodeURIComponent(r.id)}&limit=200`);

  /* 여정 — 등재부터 지금까지. 정착 도달점은 금빛으로 빛난다 */
  const evs = (led.events || []).map((e) => {
    const kind = e.kind === "상태변경" ? `${e["이전"]}→${e["이후"]}` : e.kind;
    const cls = e.kind === "상태변경" && e["이후"] === "정착" ? "정착"
      : e.kind === "뒤집힘" ? "뒤집힘" : e.kind === "확정" ? "확정" : "";
    const by = e.by ? ` · ${e.by}` : "";
    return `<span class="tl ${cls}"><span class="dot"></span>
      <span class="lbl">${esc(kind)}${esc(by)}<br>${esc((e.ts || "").slice(5, 16))}</span>
      <span class="line"></span></span>`;
  }).join("");

  const ev = r.evidence || {};
  const rows = (led.hits || []).slice().reverse().slice(0, 60).map((h) => {
    const t = h["표지"] || {}, tg = h["대상"] || {};
    const act = h.status === "미검" && h["시점"] !== "그림자" ? `
      <button data-a="확정" title="규칙이 옳았다">확정</button>
      <button data-a="뒤집힘" class="demote" title="데이터가 옳았다 — 이 규칙의 반례가 된다">뒤집힘</button>`
      : h.status === "미검" ? `
      <button data-a="확정" title="발동했다면 옳았을 것 — 그림자 부검(원문 독해로 심판)">확정</button>
      <button data-a="뒤집힘" class="demote">뒤집힘</button>` : "";
    return `<tr data-t='${esc(JSON.stringify(tg))}'>
      <td>${esc(h["시점"])}</td>
      <td class="mini"><span class="path"><b>${esc(t.src)}</b> ${esc(t.src_path)}</span><br>
        <span class="path">${esc(t.dst_path)}</span> <span class="mv">→ ${esc(t.new_path || "")}</span></td>
      <td class="st-${esc(h.status)}">${esc(h.status)}</td><td>${act}</td></tr>`;
  }).join("");

  const acts = [];
  if (r.status === "잠정")
    acts.push(`<button data-s="규칙">잠정 → 규칙 (발동 시작)</button>`);
  if (r.status === "규칙")
    acts.push(`<button data-s="정착" class="settle">규칙 → 정착 AXIOM — 의심의 방향을 뒤집는다</button>`);
  if (["잠정", "규칙"].includes(r.status))
    acts.push(`<button data-s="보류" class="demote">보류</button>`);
  if (r.status === "정착")
    acts.push(`<button data-s="강등" class="demote">정착 강등 — 영향 분석(적중 ${led.count}건) 재심 전제</button>`);
  if (["보류", "강등"].includes(r.status))
    acts.push(`<button data-s="규칙">복권 — 다시 규칙으로</button>`);

  box.innerHTML = `
    <h2>${esc(r.id)} — ${esc(r.rationale || "")}</h2>
    <h3>여정</h3><div class="timeline">${evs || '<span class="hint">기록 없음</span>'}
      <span class="tl"><span class="lbl"><b>지금: ${esc(r.status)}</b></span></span></div>
    <h3>근거 — 사례 ${((ev.instances) || []).length}건 · 홀드아웃 ${((ev.holdout) || []).length}건 ·
        반증 조건: ${esc(r.falsify_when || "")}</h3>
    <h3>적중 원장 ${led.count}건 — 뒤집힘이 곧 반례이고, 이 목록이 강등의 영향 분석이다</h3>
    <div class="hits"><table><tr><th>시점</th><th>간선 (지금 → 규칙의 착지)</th><th>부검</th><th></th></tr>
      ${rows || "<tr><td colspan=4 class='hint'>적중 없음</td></tr>"}</table></div>
    <div class="acts">${acts.join("")}</div>`;

  box.querySelectorAll(".acts button").forEach((b) => {
    b.onclick = async () => {
      const s = b.dataset.s;
      const warn = s === "정착"
        ? "정착 승격 — 이후 반례는 규칙이 아니라 데이터를 심판하게 됩니다. 4기준 보고서를 확인했습니까?"
        : s === "강등" ? "정착 강등 — 이 규칙이 심판한 적중 전부가 재심 대상이 됩니다."
        : `${r.id} 를 '${s}' 로 바꿉니다.`;
      if (!confirm(warn)) return;
      try { await api("/v1/rag/rules/resolve", { id: r.id, status: s, note: "화면에서 처리" }); }
      catch (e) { alert(e.message); }
      await load(); detail();
    };
  });
  box.querySelectorAll(".hits button").forEach((b) => {
    b.onclick = async () => {
      const tg = JSON.parse(b.closest("tr").dataset.t);
      try {
        await api("/v1/rag/rules/hits/resolve",
                  { rule: r.id, "대상": tg, action: b.dataset.a, note: "화면 부검" });
      } catch (e) { alert(e.message); }
      await load(); detail();
    };
  });
}

load().catch((e) => { $("summary").textContent = "불러오기 실패: " + e.message; });
