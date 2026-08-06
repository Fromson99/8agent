// trust-parser 뷰어 — 빌드 없음. cli.py serve 가 만든 /out/viewer.json 하나만 읽는다.
const $ = (s, r = document) => r.querySelector(s);
const el = (t, cls, txt) => { const n = document.createElement(t); if (cls) n.className = cls; if (txt != null) n.textContent = txt; return n; };
const esc = s => (s == null ? "" : String(s));

let DATA = null;              // { generated_at, ontology, docs[], reports[] }
let doc = null;               // 선택된 chunks 문서
let sel = { role: null, level: null, topic: null, text: "" };
let picked = null;

// ---------------------------------------------------------------- 부팅
fetch("../out/viewer.json?" + Date.now())
  .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
  .then(d => { DATA = d; boot(); })
  .catch(e => { $("main").innerHTML =
    `<p class="hint">데이터를 읽지 못했습니다 (${e.message}).<br>
     <code>.venv/bin/python src/cli.py serve</code> 로 띄웠는지 확인하세요.</p>`; });

function boot() {
  $("#meta").textContent = `${DATA.docs.length}개 문서 · ${DATA.reports.length}개 대사 · ${DATA.generated_at}`;
  const pick = $("#doc-pick"), qpick = $("#q-doc");
  DATA.docs.forEach((d, i) => {
    pick.appendChild(new Option(`${d.document} (${d.chunks.length})`, i));
    qpick.appendChild(new Option(d.document, i));
  });
  pick.onchange = () => selectDoc(+pick.value);
  selectDoc(0);
  renderOntology();
  renderReconcile();

  document.querySelectorAll("#tabs button").forEach(b => b.onclick = () => {
    document.querySelectorAll("#tabs button").forEach(x => x.classList.toggle("on", x === b));
    ["chunks", "onto", "reconcile", "query"].forEach(t =>
      $("#tab-" + t).hidden = t !== b.dataset.tab);
  });
  $("#q-text").oninput = e => { sel.text = e.target.value.trim(); renderList(); };
  $("#q-form").onsubmit = runQuery;
}

// ---------------------------------------------------------------- 파싱 결과
function selectDoc(i) {
  doc = DATA.docs[i];
  sel = { role: null, level: null, topic: null, text: sel.text };
  picked = null;
  renderFacets(); renderList();
}

function counts(key, base) {
  const m = new Map();
  base.forEach(c => m.set(c[key], (m.get(c[key]) || 0) + 1));
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
}

// facet 은 2축(role × topic)이 직교라는 스키마를 그대로 보여준다 — 트리가 아니다
function renderFacets() {
  const box = $("#facets"); box.innerHTML = "";
  [["role", "role (어디에 있나)"], ["level", "level (무슨 단위)"], ["topic", "topic (무엇에 대해)"]]
    .forEach(([key, title]) => {
      const g = el("div", "facet"); g.appendChild(el("h4", null, title));
      const base = doc.chunks.filter(c => Object.entries(sel).every(([k, v]) =>
        k === "text" || k === key || !v || c[k] === v));
      counts(key, base).slice(0, key === "topic" ? 40 : 12).forEach(([v, n]) => {
        const chip = el("span", "chip" + (sel[key] === v ? " on" : ""), v || "—");
        chip.appendChild(el("span", "n", n));
        chip.onclick = () => { sel[key] = sel[key] === v ? null : v; renderFacets(); renderList(); };
        g.appendChild(chip);
      });
      box.appendChild(g);
    });
}

function filtered() {
  return doc.chunks.filter(c =>
    (!sel.role || c.role === sel.role) &&
    (!sel.level || c.level === sel.level) &&
    (!sel.topic || c.topic === sel.topic) &&
    (!sel.text || (c.text || "").includes(sel.text) || c.chunk_id.includes(sel.text)));
}

function renderList() {
  const list = $("#chunk-list"); list.innerHTML = "";
  const rows = filtered();
  $("#chunk-count").textContent = `${rows.length} / ${doc.chunks.length} 청크`;
  rows.forEach(c => {
    const r = el("div", "row" + (picked === c.chunk_id ? " on" : ""));
    r.appendChild(el("span", "id", c.chunk_id));
    r.appendChild(el("span", "t", "  " + (c.topic || "")));
    r.appendChild(el("span", "x", (c.text || "").slice(0, 90)));
    r.onclick = () => { picked = c.chunk_id; renderList(); renderDetail(c); };
    list.appendChild(r);
  });
}

function renderDetail(c) {
  const d = $("#chunk-detail"); d.innerHTML = "";
  d.appendChild(el("h3", null, c.topic || c.chunk_id));
  const tags = el("div");
  [c.role, c.level, c.article, c.clause].filter(Boolean)
    .forEach(t => tags.appendChild(el("span", "tag", t)));
  d.appendChild(tags);

  const kv = el("dl", "kv");
  const add = (k, v) => { if (v == null || v === "" ) return;
    kv.appendChild(el("dt", null, k)); kv.appendChild(el("dd", "mono", v)); };
  add("chunk_id", c.chunk_id);
  add("페이지", c.provenance ? "p." + c.provenance.page : null);
  add("heading", (c.heading_path || []).join(" › "));
  add("refs", (c.refs || []).join(", "));
  add("cross_ref", c.cross_ref_explicit);
  add("structure", c.structure);
  add("template", c.value_template);
  d.appendChild(kv);

  d.appendChild(el("pre", null, c.text || ""));

  if (c.items) {
    d.appendChild(el("h2", null, `호 ${c.items.length}개`));
    const t = table(["번호", "내용"]);
    c.items.forEach(i => t.tBodies[0].appendChild(tr([i.no, i.text])));
    d.appendChild(t);
  }
  if (c.options) {
    d.appendChild(el("h2", null, `선택지 ${c.options.length}개`));
    const t = table(["", "번호", "라벨"]);
    c.options.forEach(o => t.tBodies[0].appendChild(tr([o.checked ? "✓" : "", o.no, o.label])));
    d.appendChild(t);
  }
  // 이 청크를 근거로 삼은 대사 행 — 파싱과 판정을 한 화면에서 잇는다
  const rel = DATA.reports.flatMap(r => r.rows.filter(x => x.topic && x.topic === c.topic)
    .map(x => ({ ...x, _r: r.name })));
  if (rel.length) {
    d.appendChild(el("h2", null, "이 topic 의 대사 결과"));
    const t = table(["필드", "계약서", "요약서", "판정"]);
    rel.forEach(x => t.tBodies[0].appendChild(tr(
      [x.field_name, x.contract_value, x.summary_value, verdict(x.verdict)])));
    d.appendChild(t);
  }
}

function table(head) {
  const t = el("table"), h = el("thead"), r = el("tr");
  head.forEach(x => r.appendChild(el("th", null, x)));
  h.appendChild(r); t.appendChild(h); t.appendChild(el("tbody")); return t;
}
function tr(cells) {
  const r = el("tr");
  cells.forEach(c => { const td = el("td");
    if (c instanceof Node) td.appendChild(c); else td.textContent = esc(c);
    r.appendChild(td); });
  return r;
}
function verdict(v) { return el("span", "v v-" + v, v); }

// ---------------------------------------------------------------- 온톨로지
function renderOntology() {
  const o = DATA.ontology, s = $("#tab-onto"); s.innerHTML = "";
  s.appendChild(el("h2", null, `competency questions — 여기 쓰이지 않는 제약은 만들지 않는다 (§C12.2)`));
  const cq = table(["CQ", "질문", "이 CQ 를 근거로 하는 필드"]);
  Object.entries(o.competency_questions || {}).forEach(([k, v]) => {
    const users = Object.entries(o.fields).filter(([, f]) => (f.cq || []).includes(k)).map(([n]) => n);
    cq.tBodies[0].appendChild(tr([k, v, users.join(", ") || "— (미구현)"]));
  });
  s.appendChild(cq);

  s.appendChild(el("h2", null, "구조 — 청킹 단위는 이 선언에서 나온다 (토큰 예산 없음, §D1)"));
  const st = table(["노드", "포함", "recognizer", "chunk", "경계"]);
  Object.entries(o.structure).forEach(([k, v]) =>
    st.tBodies[0].appendChild(tr([k, v.contains || "", v.recognizer || "", v.chunk || "", v.chunk_boundary || ""])));
  s.appendChild(st);

  s.appendChild(el("h2", null, `필드 ${Object.keys(o.fields).length}개 — Part B 검증 대상`));
  const f = table(["필드", "value_type", "조", "CQ", "aliases", "출처"]);
  Object.entries(o.fields).forEach(([n, v]) => {
    const p = v.provenance || {};
    f.tBodies[0].appendChild(tr([n, v.value_type, v.article || (v.derived ? "계산: " + v.derived : ""),
      (v.cq || []).join(","), (v.aliases || []).join(", ") || "— (의도적 공백)",
      [p.origin, p.approved_by, p.date].filter(Boolean).join(" / ")]));
  });
  s.appendChild(f);

  s.appendChild(el("h2", null, "shapes — 이름은 선언, 검사 로직은 validate.py"));
  const sh = el("div"); (o.shapes || []).forEach(x => sh.appendChild(el("span", "tag", x)));
  s.appendChild(sh);

  if ((o.axioms_from_text || []).length) {
    s.appendChild(el("h2", null, "본문에서 뽑은 공리 (사람 승인 필요)"));
    const a = table(["id", "출처", "규칙", "승인"]);
    o.axioms_from_text.forEach(x =>
      a.tBodies[0].appendChild(tr([x.id, x.source, x.rule, x.approved ? "✓" : "대기"])));
    s.appendChild(a);
  }
}

// ---------------------------------------------------------------- 대사 결과
function renderReconcile() {
  const s = $("#tab-reconcile"); s.innerHTML = "";
  if (!DATA.reports.length) { s.appendChild(el("p", "hint", "대사 리포트가 없습니다 — cli.py reconcile 을 먼저 돌리세요.")); return; }
  DATA.reports.forEach(rep => {
    s.appendChild(el("h2", null, `${rep.name} — ${rep.contract} vs ${rep.summary}`));
    const cards = el("div", "cards");
    const label = { total: "전체", match: "일치", value_mismatch: "불일치", missing: "누락", unmapped: "미매핑", needs_review: "보류" };
    Object.entries(rep.stats || {}).forEach(([k, v]) => {
      const c = el("div", "card"); c.appendChild(el("b", null, v));
      c.appendChild(el("span", null, label[k] || k)); cards.appendChild(c);
    });
    s.appendChild(cards);

    const t = table(["필드", "타입", "계약서 (정답)", "요약서", "판정", "근거"]);
    rep.rows.forEach(r => t.tBodies[0].appendChild(tr([
      r.field_name, r.value_type, r.contract_value, r.summary_value,
      verdict(r.verdict), r.note])));
    s.appendChild(t);

    const f = rep.firings || {};
    if (f.per_cq) {
      s.appendChild(el("h2", null, "제약 발화 (§C12.4) — 오래 침묵한 제약은 폐기 후보다"));
      const c = table(["CQ", "검사", "발화"]);
      Object.entries(f.per_cq).forEach(([k, v]) => c.tBodies[0].appendChild(tr([k, v.checked, v.fired])));
      s.appendChild(c);
      if ((f.never_fired || []).length)
        s.appendChild(el("p", "hint", "이번 대사에서 미발화: " + f.never_fired.join(", ")));
    }
    if ((rep.violations || []).length) {
      s.appendChild(el("h2", null, "shape 위반"));
      const v = table(["shape", "심각도", "내용", "청크"]);
      rep.violations.forEach(x => v.tBodies[0].appendChild(tr([x.shape, x.severity, x.message, x.chunk_id])));
      s.appendChild(v);
    }
  });
}

// ---------------------------------------------------------------- 질의 (Part D)
async function runQuery(e) {
  e.preventDefault();
  const out = $("#q-result"); out.innerHTML = '<p class="hint">조회 중…</p>';
  const url = `/api/query?doc=${$("#q-doc").value}&q=${encodeURIComponent($("#q-input").value)}`;
  let r;
  try { r = await (await fetch(url)).json(); }
  catch (err) { out.innerHTML = `<p class="hint">질의 실패: ${err.message}</p>`; return; }
  out.innerHTML = "";
  if (r.error || !r.route) {                      // 서버가 예외를 삼켰을 때
    out.appendChild(el("p", "hint", "질의 처리 중 오류: " + (r.error || "route 없음")));
    return;
  }

  const rt = r.route;
  out.appendChild(el("div", "trace",
    `intent=${rt.intent}  field=${rt.field || "—"}  role=${rt.role || "—"}  conf=${rt.confidence.toFixed(2)}\n` +
    `경로: ${rt.path.join("  →  ") || "(규칙 미적중)"}`));

  if (r.answer && r.answer.found) {
    const a = el("div", "answer");
    a.appendChild(el("b", null, `${r.answer.field_name} = ${r.answer.value}`));
    a.appendChild(el("div", "mono", "원문: " + r.answer.raw));
    if (r.answer.derived_from) a.appendChild(el("div", "hint", "계산: " + r.answer.derived_from));
    if (r.answer.source) a.appendChild(el("div", "hint",
      `근거: ${r.answer.source.doc} p.${r.answer.source.page}`));
    out.appendChild(a);
  } else if (r.answer) {
    out.appendChild(el("p", "hint", "fact 미스: " + r.answer.note + " → 청크 검색으로 넘어감"));
  }

  if (r.hits && r.hits.length) {
    out.appendChild(el("h2", null, `청크 검색 ${r.hits.length}건 (facet 후보 ${r.candidates})`));
    const t = table(["점수", "청크", "topic", "왜 걸렸나", "본문"]);
    r.hits.forEach(h => t.tBodies[0].appendChild(tr(
      [h.score, h.chunk_id, h.topic, h.why.join(" · "), h.text.slice(0, 120)])));
    out.appendChild(t);
    if (r.expanded.length) out.appendChild(el("p", "hint", "refs 확장: " + r.expanded.join(", ")));
    if (r.context.length) out.appendChild(el("p", "hint",
      `small-to-big 컨텍스트: ${r.context.join(", ")}`));
  } else if (!r.answer || !r.answer.found) {
    out.appendChild(el("p", "hint", "일치하는 청크가 없습니다."));
  }
}
