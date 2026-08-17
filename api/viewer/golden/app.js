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

/* ── 시작 ─────────────────────────────────────────────────── */
(async function init() {
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
})();
