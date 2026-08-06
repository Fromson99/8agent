/* AGENT6 근거 연결 편집 화면.
 *
 * 세 칸이다: 구조화된 코퍼스(좌) → 그 문서의 구역 트리(중) → 체크리스트(우).
 * 가운데와 오른쪽 사이에 선을 그린다. 선 하나가 항목 YAML 의 basis 한 줄이다.
 *
 * ## 선을 화면에서만 그리지 않는 이유
 * 연결을 별도 상태로 두면 체크리스트 파일과 어긋난다. 잇기/끊기는 즉시 서버로 가고
 * 서버는 `checklist/items/*.yaml` 을 고친다 — 그 파일이 판정 파이프라인의 정본이다.
 *
 * ## 좌표는 사람이 타이핑하지 않는다
 * 구역을 클릭해 잇는다. `section_id` 는 구조화 산출에서 그대로 온다 — 없는 좌표나
 * 여러 곳에 걸리는 좌표를 적을 자리가 없다(실측: 30개 중 6개가 그렇게 차단됐다). */

const API = "/v1/agent6";
const S = { corpora: [], items: [], links: [], blocked: {}, tree: [], doc: null,
            item: null, sec: null, filterLinked: false, filterBlocked: false };

const $ = (id) => document.getElementById(id);
const esc = (s) => (s || "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ------------------------------------------------------------------ 불러오기 */
async function load() {
  const r = await fetch(`${API}/graph${S.doc ? `?doc=${encodeURIComponent(S.doc)}` : ""}`);
  if (!r.ok) return banner(`그래프를 읽지 못했습니다 (${r.status})`);
  const d = await r.json();
  S.corpora = d.corpora; S.items = d.items; S.links = d.links; S.blocked = d.blocked || {};
  if (d.tree && S.doc) S.tree = d.tree[S.doc] || [];
  renderAll();
}

async function loadTree(docId) {
  S.doc = docId; S.sec = null;
  const r = await fetch(`${API}/doc/${encodeURIComponent(docId)}`);
  S.tree = r.ok ? (await r.json()).sections : [];
  if (!r.ok) banner(`${docId}: 구조화 산출이 없습니다 — corpus_build 를 먼저 돌리세요`);
  renderAll();
}

function banner(msg) {
  const b = $("banner");
  b.textContent = msg;
  b.classList.toggle("hidden", !msg);
}

/* ------------------------------------------------------------------- 렌더 */
function renderAll() { renderCorpora(); renderTree(); renderItems(); renderSummary(); wires(); }

function renderSummary() {
  const amb = S.links.filter((l) => l.status === "AMBIGUOUS").length;
  const miss = S.links.filter((l) => l.status === "MISSING").length;
  const nb = Object.keys(S.blocked).length;
  $("summary").innerHTML =
    `항목 ${S.items.length} · 연결 ${S.links.length}` +
    (amb ? ` · <span class="pill warn">모호 ${amb}</span>` : "") +
    (miss ? ` · <span class="pill bad">미해소 ${miss}</span>` : "") +
    (nb ? ` · <span class="pill bad">차단 항목 ${nb}</span>` : "");
}

function renderCorpora() {
  $("corpora").innerHTML = S.corpora.map((c) => {
    const st = c.structured
      ? `<span class="pill ok">구조화됨</span>`
      : `<span class="pill bad">${esc(c.status || "미구조화")}</span>`;
    const ver = c.verification && c.verification !== "VERIFIED"
      ? ` <span class="pill warn">${esc(c.verification)}</span>` : "";
    return `<div class="corpus ${c.id === S.doc ? "on" : ""}" data-id="${esc(c.id)}">
      <b>${esc(c.title)}</b>
      <div class="meta">${esc(c.id)} · ${st}${ver}
        ${c.edition ? `<br>${esc(c.edition)}` : ""}
        ${c.sections ? `<br>구역 ${c.sections}개` : ""}</div></div>`;
  }).join("") || "<p class='hint'>코퍼스가 없습니다.</p>";
  document.querySelectorAll(".corpus").forEach((el) => {
    el.onclick = () => loadTree(el.dataset.id);
  });
}

/* 이 구역에 걸린 연결들 — 해소된 section_id 또는 스펙이 적은 section 으로 맞춘다. */
function linksOfSection(sid) {
  return S.links.filter((l) => l.doc === S.doc &&
    (l.section_id === sid || l.section === sid));
}

function renderTree() {
  $("mid-title").textContent = S.doc ? `구역 — ${S.doc}` : "구역";
  if (!S.doc) { $("tree").innerHTML = "<p class='hint'>왼쪽에서 문서를 고르세요.</p>"; return; }
  const rows = S.tree.filter((s) => {
    if (s.kind === "default") return false;      // 기본 구역은 인용 대상이 아니다
    if (S.filterLinked && !linksOfSection(s.section_id).length) return false;
    return true;
  });
  $("tree").innerHTML = rows.map((s) => {
    const ls = linksOfSection(s.section_id);
    const tag = ls.length ? ` <span class="pill ok">${ls.map((l) => l.item).join(" ")}</span>` : "";
    return `<div class="sec ${ls.length ? "linked" : ""} ${S.sec === s.section_id ? "sel" : ""}"
                 data-sid="${esc(s.section_id)}" style="padding-left:${6 + s.level * 12}px">
      <span class="lab">${esc(s.label)}</span>
      <span class="ttl">${esc(s.title || s.preview.slice(0, 70))}</span>${tag}
      <span class="act"><button class="mini link">잇기</button></span></div>`;
  }).join("") || "<p class='hint'>표시할 구역이 없습니다.</p>";

  document.querySelectorAll(".sec").forEach((el) => {
    const sid = el.dataset.sid;
    el.onclick = (e) => {
      if (e.target.classList.contains("link")) return;
      S.sec = sid; showSection(sid); renderTree(); wires();
    };
    const b = el.querySelector(".link");
    if (b) b.onclick = (e) => { e.stopPropagation(); addLink(sid); };
  });
}

function renderItems() {
  const rows = S.items.filter((i) => !S.filterBlocked || S.blocked[i.id]);
  $("items").innerHTML = rows.map((it) => {
    const mine = S.links.filter((l) => l.item === it.id);
    const basis = mine.map((l) => {
      const cls = l.status === "AMBIGUOUS" ? "amb" : l.status === "RESOLVED" ? "" : "miss";
      const where = l.citation || l.resolved || l.coord;
      // 끊기는 좌표 **왼쪽**에 둔다. 오른쪽에 두면 긴 조문 이름이 버튼을 패널
      // 밖으로 밀어내 눌 수 없게 된다(실측).
      return `<div class="row ${cls}" title="${esc(l.reason || where)}">
        <button class="cut" title="이 연결 끊기" data-item="${esc(it.id)}"
          data-doc="${esc(l.doc)}" data-section="${esc(l.section || "")}"
          data-term="${esc(l.term || "")}">✕</button>
        <span class="coord">${esc(where)}</span>
      </div>`;
    }).join("") || `<div class="row miss"><span class="coord">근거 없음</span></div>`;
    return `<div class="item ${S.item === it.id ? "sel" : ""} ${S.blocked[it.id] ? "blocked" : ""}"
                 data-id="${esc(it.id)}">
      <div class="head"><span class="id">${esc(it.id)}</span>
        <span class="nm">${esc(it.name)}</span>
        <span class="pill">${esc(it.type)}</span></div>
      <div class="basis">${basis}</div></div>`;
  }).join("");

  document.querySelectorAll(".item").forEach((el) => {
    el.onclick = (e) => {
      if (e.target.classList.contains("cut")) return;
      S.item = el.dataset.id; showItem(S.item); renderItems(); wires();
    };
  });
  document.querySelectorAll(".cut").forEach((b) => {
    b.onclick = (e) => { e.stopPropagation(); cutLink(b.dataset); };
  });
}

/* ------------------------------------------------------------------ 연결선 */
/* 스크롤 밖으로 나간 마디의 y 를 패널 가장자리로 **접는다**.
 *
 * 접지 않으면 스크롤된 구역들의 좌표가 전부 패널 밖 같은 지점으로 몰려, 화면에는
 * "굵은 초록 띠" 하나로만 보인다(실측). 어디로 가는지 알 수 없으니 선이 아니라
 * 잡음이다. 가장자리에 붙이고 **화살촉으로 "이 방향에 더 있다"** 를 말한다. */
function anchor(el, pane, box, side) {
  const r = el.getBoundingClientRect();
  const p = pane.getBoundingClientRect();
  const mid = r.top + r.height / 2;
  const y = Math.min(Math.max(mid, p.top + 6), p.bottom - 6);
  return { x: (side === "right" ? r.right : r.left) - box.left,
           y: y - box.top, off: mid < p.top || mid > p.bottom };
}

function wires() {
  const svg = $("wires");
  const box = svg.getBoundingClientRect();
  const treePane = $("tree"), itemPane = $("items");
  const secEl = {}, itemEl = {};
  document.querySelectorAll(".sec").forEach((e) => (secEl[e.dataset.sid] = e));
  document.querySelectorAll(".item").forEach((e) => (itemEl[e.dataset.id] = e));

  // 고른 것이 있으면 그것만 진하게, 나머지는 배경으로 물린다. 30여 개를 같은 굵기로
  // 그리면 어느 것이 어느 것인지 읽히지 않는다.
  const focused = S.item || S.sec;
  const paths = [];
  for (const l of S.links) {
    if (l.doc !== S.doc) continue;
    const a = secEl[l.section_id] || secEl[l.section];
    const b = itemEl[l.item];
    if (!a || !b) continue;
    const hot = S.item === l.item || S.sec === (l.section_id || l.section);
    if (focused && !hot) continue;              // 초점이 있으면 그것만 그린다
    const p1 = anchor(a, treePane, box, "right");
    const p2 = anchor(b, itemPane, box, "left");
    const dx = Math.max(24, (p2.x - p1.x) / 2);
    const cls = [l.status === "AMBIGUOUS" ? "amb" : l.status === "RESOLVED" ? "" : "miss",
                 hot ? "hot" : "", (p1.off || p2.off) ? "off" : ""].join(" ").trim();
    paths.push(`<path class="${cls}" d="M${p1.x},${p1.y} `
      + `C${p1.x + dx},${p1.y} ${p2.x - dx},${p2.y} ${p2.x},${p2.y}"/>`);
    if (p1.off || p2.off) {                     // 화면 밖으로 이어진다는 표시
      const e = p1.off ? p1 : p2;
      paths.push(`<circle class="stub ${cls}" cx="${e.x}" cy="${e.y}" r="2.6"/>`);
    }
  }
  svg.setAttribute("viewBox", `0 0 ${box.width} ${box.height}`);
  svg.innerHTML = paths.join("");
  $("wirehint").textContent = focused
    ? `${paths.length ? "" : "연결 없음 — "}고른 것만 표시 중 (빈 곳을 누르면 전체)`
    : `연결 ${S.links.filter((l) => l.doc === S.doc).length}개 — 항목이나 구역을 고르면 그것만 보입니다`;
}

/* 빈 곳을 누르면 초점을 푼다 — 초점이 걸려 있으면 나머지 선이 안 보이므로
 * 빠져나올 길이 있어야 한다. */
document.addEventListener("click", (e) => {
  // 캔버스가 켜져 있으면 목록의 초점을 건드리지 않는다 — 숨어 있는 DOM 의 좌표는
  // 전부 0 이라 선을 다시 그려 봐야 잡음만 만든다.
  if (typeof CV !== "undefined" && CV.on) return;
  if (e.target.closest(".sec, .item, .top, .detail")) return;
  S.item = null; S.sec = null;
  renderTree(); renderItems(); wires();
});

/* ------------------------------------------------------------------ 편집 */
async function addLink(sid) {
  if (!S.item) return banner("먼저 오른쪽에서 체크리스트 항목을 고르세요.");
  const body = { item: S.item, doc: S.doc, section: sid, note: "" };
  const r = await fetch(`${API}/links`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) return banner(`잇지 못했습니다: ${d.detail || r.status}`);
  banner(`${S.item} ← ${S.doc}/${sid} 를 이었습니다. 발췌를 만들려면 corpus_build 를 다시 돌리세요.`);
  await load();
}

async function cutLink(ds) {
  const body = { item: ds.item, doc: ds.doc,
                 section: ds.section || null, term: ds.term || null };
  const r = await fetch(`${API}/links`, {
    method: "DELETE", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) return banner(`끊지 못했습니다: ${d.detail || r.status}`);
  banner(`${ds.item} 의 연결을 끊었습니다.`);
  await load();
}

/* ------------------------------------------------------------------ 상세 */
function detail(html) {
  const d = $("detail");
  d.innerHTML = `<span class="x" onclick="document.getElementById('detail').classList.add('hidden')">✕</span>${html}`;
  d.classList.remove("hidden");
}

function showSection(sid) {
  const s = S.tree.find((x) => x.section_id === sid);
  if (!s) return;
  detail(`<h3>${esc(s.label)} ${esc(s.title)}</h3>
    <div class="sub">${esc(S.doc)}/${esc(s.section_id)} · ${s.chars}자
      ${s.pages && s.pages.length ? ` · p${s.pages.join("–")}` : ""}</div>
    <pre>${esc(s.preview)}</pre>`);
}

function showItem(id) {
  const it = S.items.find((x) => x.id === id);
  if (!it) return;
  const blocked = S.blocked[id]
    ? `<div class="sub" style="color:var(--bad)">차단: ${esc(S.blocked[id])}</div>` : "";
  detail(`<h3>${esc(it.id)} ${esc(it.name)}</h3>
    <div class="sub">${esc(it.type)} · when: ${esc(it.when)} · ${esc(it.file)}</div>
    ${blocked}<pre>${esc(it.definition)}</pre>`);
}

/* ------------------------------------------------------------------ 검색 */
let qTimer = null;
$("q").oninput = (e) => {
  clearTimeout(qTimer);
  const q = e.target.value.trim();
  qTimer = setTimeout(async () => {
    if (q.length < 2) return renderTree();
    const r = await fetch(`${API}/search?q=${encodeURIComponent(q)}&doc=${encodeURIComponent(S.doc || "")}`);
    if (!r.ok) return;
    const hits = (await r.json()).hits;
    const ids = new Set(hits.map((h) => h.section_id));
    const keep = S.tree.filter((s) => ids.has(s.section_id));
    $("tree").innerHTML = keep.map((s) => `<div class="sec" data-sid="${esc(s.section_id)}">
      <span class="lab">${esc(s.label)}</span>
      <span class="ttl">${esc(s.title || s.preview.slice(0, 70))}</span>
      <span class="act"><button class="mini link">잇기</button></span></div>`).join("")
      || "<p class='hint'>일치하는 구역이 없습니다.</p>";
    document.querySelectorAll(".sec").forEach((el) => {
      el.onclick = (ev) => { if (!ev.target.classList.contains("link")) showSection(el.dataset.sid); };
      const b = el.querySelector(".link");
      if (b) b.onclick = (ev) => { ev.stopPropagation(); addLink(el.dataset.sid); };
    });
    wires();
  }, 220);
};

$("only-linked").onchange = (e) => { S.filterLinked = e.target.checked; renderTree(); wires(); };
$("only-blocked").onchange = (e) => { S.filterBlocked = e.target.checked; renderItems(); wires(); };
$("reload").onclick = () => load();
document.querySelectorAll(".scroll").forEach((el) => el.addEventListener("scroll", wires));
window.addEventListener("resize", wires);

load();
