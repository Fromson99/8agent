/* 골든 태깅 — 회답이 답을 가른 조문을 항·호까지 짚는다.
 *
 * 흐름: 왼쪽에서 사례를 고르고 → 가운데서 이유를 읽고 → 오른쪽에서 법령을 펴
 * 마디를 눌러 담는다. 담은 것이 곧 "결정 마디"이고, 전제는 담지 않는다.
 * 정규식 자가 그 둘을 못 가르는 것이 이 화면이 생긴 이유다(docs/RETRIEVAL.md 1-3).
 */
const $ = (s) => document.querySelector(s);
const el = (t, c, x) => { const n = document.createElement(t); if (c) n.className = c;
                          if (x != null) n.textContent = x; return n; };

let CASES = [], CUR = null, TAG = null, LAWNAME = "";
let CM = null, CM_CUR = null, TAGGING_LOADED = false;

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}
function fail(msg) {
  const b = $("#banner"); b.textContent = msg; b.classList.remove("hidden");
  setTimeout(() => b.classList.add("hidden"), 6000);
}

/* ── 후보 목록 ─────────────────────────────────────────────── */
function clean(c) {
  return !c.store_missing.length && !c.jo_gone.length && !c.needs_precedent && !c.multi_part;
}
function renderList() {
  const only = $("#onlyClean").checked;
  const rows = only ? CASES.filter(clean) : CASES;
  const box = $("#list"); box.innerHTML = "";
  rows.forEach((c) => {
    const it = el("div", "item" + (CUR === c.case_no ? " sel" : ""));
    const no = el("div", "no");
    const dot = el("span", "dot" + (c.tagged ? (c.tagged_by === "사람" ? " on" : " agent") : ""));
    no.append(dot, el("span", null, c.case_no), el("span", "hint", String(c.score)));
    it.append(no, el("div", "ti", c.title));
    it.onclick = () => open(c.case_no);
    box.append(it);
  });
  const done = CASES.filter((c) => c.tagged).length;
  $("#progress").textContent = `${done}/${CASES.length} 태그됨`;
  $("#summary").textContent = `후보 ${CASES.length}건 · 결함 없는 것 ${CASES.filter(clean).length}건`;
}

/* ── 사례 열기 ─────────────────────────────────────────────── */
async function open(no) {
  CUR = no;
  const d = await api(`/v1/golden/case/${no}`);
  TAG = d.tag || { decisive_full: [], direction: null, colloquial: "", note: "" };
  if (!TAG.decisive_full) TAG.decisive_full = [];

  $("#empty").classList.add("hidden");
  $("#editor").classList.remove("hidden");
  $("#caseNo").textContent = no;
  $("#issue").textContent = d.issue;
  $("#answer").textContent = d.answer;
  $("#reason").textContent = d.reason || "(이유 없음)";
  $("#colloq").value = TAG.colloquial || "";
  $("#note").value = TAG.note || "";
  $("#saveBtn").disabled = false;

  const meta = CASES.find((c) => c.case_no === no) || {};
  const f = $("#flags"); f.innerHTML = "";
  const add = (t, ok) => f.append(Object.assign(el("span", "flag" + (ok ? " ok" : ""), t), {}));
  if (meta.store_missing?.length) add(`창고결손 ${meta.store_missing.length}`);
  if (meta.jo_gone?.length) add(`조부재 ${meta.jo_gone.length}`);
  if (meta.needs_precedent) add("판례필요");
  if (meta.multi_part) add("다부");
  if (!f.children.length) add("결함 신호 없음", true);

  renderDirs(); renderPicked(); renderList();
  if (d.laws?.length) { $("#lawq").value = d.laws[0]; loadLaw(d.laws[0]); }
}

function renderDirs() {
  document.querySelectorAll("#dirs button").forEach((b) =>
    b.classList.toggle("on", b.dataset.d === TAG.direction));
}
function renderPicked() {
  const box = $("#picked"); box.innerHTML = "";
  if (!TAG.decisive_full.length) { box.append(el("div", "hint", "아직 없음")); return; }
  TAG.decisive_full.forEach((p, i) => {
    const c = el("div", "chip");
    c.append(el("span", "co", `${p.law} ${p.jo}${p.hang_ho ? " " + p.hang_ho : ""}`),
             el("span", "tx", p.text || ""));
    const x = el("button", "x", "×");
    x.onclick = () => { TAG.decisive_full.splice(i, 1); renderPicked(); markTree(); };
    c.append(x); box.append(c);
  });
}

/* ── 법령 열람 ─────────────────────────────────────────────── */
async function loadLaw(name) {
  try {
    const d = await api(`/v1/golden/law?name=${encodeURIComponent(name)}`);
    LAWNAME = d.law;
    const box = $("#jos"); box.innerHTML = "";
    d.jos.forEach((j) => {
      const b = el("button", j.addendum ? "add" : "", j.surface);
      b.title = j.title || "";
      b.onclick = () => loadJo(j.surface);
      box.append(b);
    });
    $("#tree").innerHTML = "";
  } catch (e) { fail(String(e.message)); }
}
async function loadJo(jo) {
  try {
    const d = await api(`/v1/golden/law?name=${encodeURIComponent(LAWNAME)}&jo=${encodeURIComponent(jo)}`);
    const tree = $("#tree"); tree.innerHTML = "";
    d.nodes.forEach((n) => tree.append(nodeEl(n, d.jo)));
    markTree();
  } catch (e) { fail(String(e.message)); }
}
function nodeEl(n, jo) {
  const wrap = el("div");
  const row = el("div", "node");
  row.style.marginLeft = `${n.depth * 12}px`;
  row.dataset.nodeId = n.node_id;
  row.append(el("span", "sf", n.surface || jo), el("span", null, n.text.slice(0, 300)));
  row.onclick = () => pick(n, jo);
  wrap.append(row);
  n.children.forEach((k) => wrap.append(nodeEl(k, jo)));
  return wrap;
}
function pick(n, jo) {
  const i = TAG.decisive_full.findIndex((p) => p.node_id === n.node_id && p.law === LAWNAME);
  if (i >= 0) TAG.decisive_full.splice(i, 1);
  else TAG.decisive_full.push({ law: LAWNAME, jo, hang_ho: n.surface === jo ? "" : n.surface,
                                node_id: n.node_id, text: n.text.slice(0, 120), why: "" });
  renderPicked(); markTree();
}
function markTree() {
  const ids = new Set(TAG.decisive_full.filter((p) => p.law === LAWNAME).map((p) => p.node_id));
  document.querySelectorAll("#tree .node").forEach((r) =>
    r.classList.toggle("picked", ids.has(r.dataset.nodeId)));
}

/* ── 저장 ─────────────────────────────────────────────────── */
async function save() {
  if (!CUR) return;
  try {
    await api(`/v1/golden/tag/${CUR}`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({
        decisive: TAG.decisive_full, direction: TAG.direction,
        colloquial: $("#colloq").value.trim(), note: $("#note").value.trim(), by: "사람",
      }),
    });
    const c = CASES.find((x) => x.case_no === CUR);
    if (c) { c.tagged = TAG.decisive_full.length > 0; c.tagged_by = "사람"; }
    renderList();
    $("#saveBtn").textContent = "저장됨";
    setTimeout(() => ($("#saveBtn").textContent = "저장"), 1200);
  } catch (e) { fail(`저장 실패 — ${e.message}`); }
}

/* ── CM 현업 핵심 골든 ────────────────────────────────────── */
function cmFiltered() {
  if (!CM) return [];
  const q = $("#cmQuery").value.trim().toLowerCase();
  const domain = $("#cmDomain").value;
  return CM.cases.filter((row) => {
    if (domain && row.business_domain !== domain) return false;
    const laws = (row.expected_articles || []).map((x) => `${x.law} ${x.article}`).join(" ");
    return !q || `${row.id} ${row.topic} ${row.question} ${laws}`.toLowerCase().includes(q);
  });
}

function renderCMList() {
  const rows = cmFiltered();
  $("#cmCount").textContent = `${rows.length}건`;
  const box = $("#cmList"); box.innerHTML = "";
  rows.forEach((row) => {
    const button = el("button", "cm-case" + (CM_CUR === row.id ? " on" : ""));
    const top = el("span", "cm-case-top");
    top.append(el("b", null, row.id), el("i", null, row.business_domain || "미분류"));
    button.append(top, el("strong", null, row.source_question || row.question),
      el("small", null, `${row.question_kind === "additional" ? "추가질문" : "본질문"} · 정답조문 ${(row.expected_articles || []).length}개`));
    button.onclick = () => openCM(row.id);
    box.append(button);
  });
  if (!rows.length) box.append(el("div", "cm-empty small", "조건에 맞는 문항이 없습니다."));
}

function cmBlock(title, text, cls = "") {
  const section = el("section", `cm-block ${cls}`.trim());
  section.append(el("h3", null, title), el("div", "cm-text", text || "—"));
  return section;
}

async function openCM(id) {
  try {
    CM_CUR = id; renderCMList();
    const data = await api(`/v1/golden/cm/case/${encodeURIComponent(id)}`);
    const row = data.case, axes = row.axes || {}, box = $("#cmDetail");
    box.innerHTML = "";
    const head = el("header", "cm-detail-head");
    const meta = el("div", "cm-detail-meta");
    meta.append(el("span", "cm-id", row.id), el("span", "cm-domain", axes.business_domain || "미분류"),
      el("span", "cm-kind", row.question_kind === "additional" ? "추가질문" : "본질문"));
    head.append(meta, el("h2", null, row.source_question || row.question), el("p", null, row.topic || ""));
    box.append(head, cmBlock("단일턴 입력", row.question, "question"),
      cmBlock("현업 기준답변", row.reference_answer, "answer"));

    const evidence = el("section", "cm-block");
    evidence.append(el("h3", null, `정답 조문 ${(row.expected_articles || []).length}개`));
    const coords = el("div", "cm-coords");
    (row.expected_articles || []).forEach((coord) => {
      const card = el("div", "cm-coord");
      card.append(el("b", null, `${coord.law} ${coord.article}`),
        el("span", null, `doc ${coord.doc_id || "—"} · node ${coord.node || "—"}`),
        el("small", null, `${coord.document_revision || "개정일 없음"} · 동결 ${coord.corpus_status || "—"}`));
      coords.append(card);
    });
    evidence.append(coords); box.append(evidence);

    const axis = el("section", "cm-block"); axis.append(el("h3", null, "평가 축"));
    const chips = el("div", "cm-axis");
    Object.entries(axes).forEach(([key, value]) => chips.append(el("span", null, `${key} · ${value}`)));
    axis.append(chips); box.append(axis);
  } catch (e) { fail(`CM 문항을 못 불러왔습니다 — ${e.message}`); }
}

async function loadCM() {
  if (CM) { renderCMList(); return; }
  try {
    CM = await api("/v1/golden/cm");
    const s = CM.summary, validation = CM.validation || {}, current = validation.current_material || {};
    $("#cmCases").textContent = s.cases;
    $("#cmArticles").textContent = s.expected_articles;
    $("#cmDomains").textContent = s.business_domains;
    $("#cmComplete").textContent = `${current.complete || 0}/${s.cases}`;
    $("#cmDrift").textContent = `좌표 변화 ${(validation.corpus_drift || []).length}건`;
    $("#cmValid").textContent = validation.valid ? "원문 검증 PASS" : "원문 검증 FAIL";
    $("#cmValid").classList.toggle("bad", !validation.valid);
    $("#cmFrozen").textContent = CM.frozen ? "FROZEN" : "DRAFT";
    $("#cmSource").textContent = `${CM.source.organization_unit || "CM본부"} · ${CM.source.title || CM.name} · ${CM.source.date_from_filename || ""}`;
    $("#summary").textContent = `CM 현업 ${s.cases}건 · 정답 조문 ${s.expected_articles}개 · 현재 재료 ${current.complete || 0}건`;
    const domains = Object.keys(s.by_domain || {}).sort();
    $("#cmDomain").innerHTML = '<option value="">모든 도메인</option>';
    domains.forEach((domain) => { const option = el("option", null, domain); option.value = domain; $("#cmDomain").append(option); });
    renderCMList();
    if (CM.cases.length) openCM(CM.cases[0].id);
  } catch (e) { fail(`CM 골든을 못 불러왔습니다 — ${e.message}`); }
}

/* ── 법령해석 태깅 지연 적재 ─────────────────────────────── */
async function loadTagging() {
  if (TAGGING_LOADED) { renderList(); return; }
  TAGGING_LOADED = true;
  try {
    const d = await api("/v1/golden/cases?limit=60");
    CASES = d.cases; renderList();
    const laws = await api("/v1/golden/laws");
    $("#lawlist").innerHTML = laws.laws.map((l) => `<option value="${l}">`).join("");
  } catch (e) { fail(`목록을 못 불러왔습니다 — ${e.message}`); }

  $("#onlyClean").onchange = renderList;
  $("#saveBtn").onclick = save;
  document.querySelectorAll("#dirs button").forEach((b) =>
    (b.onclick = () => { TAG.direction = TAG.direction === b.dataset.d ? null : b.dataset.d;
                         renderDirs(); }));
  $("#lawq").onchange = () => loadLaw($("#lawq").value.trim());
}

function setMode(mode) {
  const cm = mode === "cm";
  $("#cmView").classList.toggle("hidden", !cm);
  $("#tagView").classList.toggle("hidden", cm);
  $("#saveBtn").classList.toggle("hidden", cm);
  $("#cmMode").classList.toggle("on", cm);
  $("#tagMode").classList.toggle("on", !cm);
  history.replaceState(null, "", cm ? "#cm" : "#tagging");
  if (cm) loadCM(); else loadTagging();
}

/* ── 시작 ─────────────────────────────────────────────────── */
$("#cmMode").onclick = () => setMode("cm");
$("#tagMode").onclick = () => setMode("tagging");
$("#cmQuery").oninput = renderCMList;
$("#cmDomain").onchange = renderCMList;
setMode(location.hash === "#tagging" ? "tagging" : "cm");
