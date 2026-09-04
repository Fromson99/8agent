(function () {
  "use strict";

  const state = { threshold: 2, evolution: null, rows: [], currentOnly: true, selected: "" };
  const $ = (s) => document.querySelector(s);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const clean = (v) => String(v || "—").replaceAll("_", " ");
  const fmtTime = (v) => { if (!v) return "—"; const d = new Date(v); return Number.isNaN(d.getTime()) ? v : new Intl.DateTimeFormat("ko-KR", {month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit"}).format(d); };
  // data-* 속성으로 왕복해야 하므로 NUL 같은 제어문자는 식별자에 쓰지 않는다.
  const keyOf = (c) => `${c.failure}\u241f${c.effect}`;
  const subjectText = (v) => {
    if (!v || typeof v !== "object") return String(v || "—");
    const preferred = ["label", "term", "qid", "doc_id", "src_doc", "dst_doc", "path", "rule_id"];
    const pairs = preferred.filter((k) => v[k] != null).map((k) => `${k}: ${v[k]}`);
    return pairs.length ? pairs.join(" · ") : JSON.stringify(v);
  };

  async function json(url) {
    const r = await fetch(url, {headers:{Accept:"application/json"}});
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  }

  async function load() {
    const btn = $("#refreshBtn"); btn.disabled = true;
    $("#syncState").textContent = "승인 원장 동기화 중";
    try {
      const [evolution, receipts] = await Promise.all([
        json(`/v1/rag/approvals/evolution?min_evidence=${state.threshold}`),
        json(`/v1/rag/approvals?current_only=${state.currentOnly}&limit=2000`),
      ]);
      state.evolution = evolution;
      state.rows = receipts.rows || [];
      if (state.selected && !(evolution.candidates || []).some((c) => keyOf(c) === state.selected)) state.selected = "";
      render();
      $("#syncState").textContent = `원장 연결 · ${fmtTime(new Date().toISOString())}`;
    } catch (error) {
      $("#syncState").textContent = `연결 실패 · ${error.message}`;
      renderError(error);
    } finally { btn.disabled = false; }
  }

  function render() {
    const e = state.evolution || {};
    const candidates = e.candidates || [];
    const ready = candidates.filter((c) => c.status === "탐색후보");
    $("#mReceipts").textContent = Number(e.receipts || 0).toLocaleString("ko-KR");
    $("#mSubjects").textContent = Number(e.current_subjects || 0).toLocaleString("ko-KR");
    $("#mCandidates").textContent = ready.length.toLocaleString("ko-KR");
    $("#mWatching").textContent = (candidates.length - ready.length).toLocaleString("ko-KR");
    $("#clusterCount").textContent = candidates.length ? `${candidates.length}개 실패 군집` : "실제 판정 대기";
    $("#candidateCount").textContent = candidates.length;
    $("#flowMap").classList.toggle("has-selection", Boolean(state.selected));
    renderCandidates(candidates);
    renderInspector(candidates.find((c) => keyOf(c) === state.selected));
    renderFilters();
    renderLedger();
  }

  function renderCandidates(candidates) {
    const box = $("#candidateList");
    if (!candidates.length) {
      box.innerHTML = `<div class="empty-block"><b>아직 변이 후보가 없습니다</b><p>실제 승인·기각·교정이 쌓이면 실패 유형과 효과가 여기서 군집화됩니다. 기준 미만의 군집도 관측 중으로 함께 표시됩니다.</p></div>`;
      return;
    }
    box.innerHTML = candidates.map((c) => {
      const selected = keyOf(c) === state.selected;
      return `<button class="candidate${selected ? " selected" : ""}" type="button" data-key="${esc(keyOf(c))}">
        <h3>${esc(clean(c.failure))}<span>→</span>${esc(clean(c.effect))}</h3>
        <span class="status${c.status === "탐색후보" ? "" : " watching"}">${esc(c.status)}</span>
        <div class="candidate-meta"><span>증거 <b>${c.evidence || 0}</b></span><span>질문 <b>${c.unique_qids || 0}</b></span><span>문서 <b>${c.documents || 0}</b></span><span>변경축 <b>${(c.mutation_targets || []).length}</b></span><span>최근 ${esc(fmtTime(c.last))}</span></div>
      </button>`;
    }).join("");
    box.querySelectorAll(".candidate").forEach((button) => button.addEventListener("click", () => {
      state.selected = button.dataset.key;
      renderCandidates(candidates);
      renderInspector(candidates.find((c) => keyOf(c) === state.selected));
      $("#flowMap").classList.add("has-selection");
    }));
  }

  function targetGroup(label, hint, type, targets) {
    return `<section class="target-group ${type}"><header><b>${label}</b><span>${hint}</span></header>${targets.length
      ? targets.map((t) => `<code class="target-chip">${esc(t)}</code>`).join("")
      : '<span class="none">해당 변경축 없음</span>'}</section>`;
  }

  function renderInspector(c) {
    const box = $("#inspector");
    if (!c) {
      box.innerHTML = `<div class="inspector-empty"><span class="section-code">CANDIDATE INSPECTOR</span><h2>${(state.evolution?.candidates || []).length ? "후보를 선택하세요" : "관측 신호 대기 중"}</h2><p>실패 유형과 효과가 어느 control·operator 변경축으로 연결되는지 확인할 수 있습니다.</p></div>`;
      return;
    }
    const targets = c.mutation_targets || [];
    const controls = targets.filter((t) => t.startsWith("control:"));
    const operators = targets.filter((t) => t.startsWith("operator:"));
    const enough = (c.evidence || 0) >= state.threshold;
    box.innerHTML = `<div class="inspect-title"><span class="section-code">${esc(c.status)} · EVIDENCE ${c.evidence || 0}</span><h2>${esc(clean(c.failure))} → ${esc(clean(c.effect))}</h2><p>독립 질문 ${c.unique_qids || 0}개 · 문서 ${c.documents || 0}개 · 최근 ${esc(fmtTime(c.last))}</p></div>
      <div class="target-grid">
        ${targetGroup("CONTROL", "등록된 수치 손잡이", "control", controls)}
        ${targetGroup("OPERATOR", "닫힌 DSL 설계 필요", "operator", operators)}
      </div>
      <div class="gate-list"><h3>운영 반영까지의 안전 게이트</h3>
        <div class="gate-row ${enough ? "ready" : ""}"><i>${enough ? "✓" : ""}</i><b>증거 기준</b><span>${c.evidence || 0} / ${state.threshold}건 ${enough ? "충족" : "미달"}</span></div>
        <div class="gate-row"><i></i><b>REPLAY</b><span>실행기 미구현</span></div>
        <div class="gate-row"><i></i><b>HOLDOUT</b><span>일반화 검증 미구현</span></div>
        <div class="gate-row"><i></i><b>SHADOW</b><span>운영 그림자 관측 미구현</span></div>
        <div class="gate-row"><i></i><b>사람 승인</b><span>운영 설정 변경 전 필수</span></div>
      </div>`;
  }

  function renderFilters() {
    const select = $("#kindFilter");
    const old = select.value;
    const kinds = [...new Set(state.rows.map((r) => r.kind).filter(Boolean))].sort();
    select.innerHTML = '<option value="">모든 유형</option>' + kinds.map((k) => `<option value="${esc(k)}">${esc(clean(k))}</option>`).join("");
    if (kinds.includes(old)) select.value = old;
  }

  function renderLedger() {
    const kind = $("#kindFilter").value;
    const query = $("#ledgerSearch").value.trim().toLowerCase();
    const rows = state.rows.filter((r) => {
      if (kind && r.kind !== kind) return false;
      return !query || `${r.failure} ${r.effect} ${subjectText(r.subject)} ${r.note || ""}`.toLowerCase().includes(query);
    }).slice().reverse();
    $("#ledgerRows").innerHTML = rows.map((r) => `<tr>
      <td><time datetime="${esc(r.ts)}">${esc(fmtTime(r.ts))}</time></td>
      <td>${esc(clean(r.kind))}</td>
      <td><span class="decision">${esc(clean(r.decision))}</span></td>
      <td>${esc(clean(r.failure))} <span class="mv">→</span> ${esc(clean(r.effect))}</td>
      <td><span class="subject" title="${esc(subjectText(r.subject))}">${esc(subjectText(r.subject))}</span></td>
      <td>${(r.qids || []).length}Q · ${(r.mutation_targets || []).length}축</td>
    </tr>`).join("");
    $("#ledgerEmpty").classList.toggle("hidden", rows.length > 0);
  }

  function renderError(error) {
    $("#candidateList").innerHTML = `<div class="empty-block"><b>승인 원장을 불러오지 못했습니다</b><p>${esc(error.message)} · 서버 재기동 후 다시 시도하세요.</p></div>`;
    $("#inspector").innerHTML = '<div class="inspector-empty"><span class="section-code">CONNECTION ERROR</span><h2>API 연결이 필요합니다</h2></div>';
  }

  $("#refreshBtn").addEventListener("click", load);
  $("#threshold").addEventListener("change", (e) => { state.threshold = Number(e.target.value) || 2; load(); });
  $("#currentOnly").addEventListener("change", (e) => { state.currentOnly = e.target.checked; load(); });
  $("#kindFilter").addEventListener("change", renderLedger);
  $("#ledgerSearch").addEventListener("input", renderLedger);
  load();
})();
