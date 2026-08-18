/* 계보 원장 — 수집→변환→구조화→연결을 문서 단위로 감독하는 화면.
 *
 * 데이터는 GET /v1/lineage 한 번이다. 원장은 각 단계의 자기 기록(수집
 * manifest · 변환 사이드카 · 구조화 meta.json · 연결 links.json)에서
 * 요청 때마다 파생되므로(docs/LINEAGE.md), 이 화면에 쓰기 조작은 없다 —
 * 고치는 손은 각 단계의 화면·CLI 이고, 여기는 멈춘 자리를 보는 곳이다.
 *
 * 깔때기의 단계 상자가 필터다 — 감독은 완료 목록이 아니라 멈춘 자리를
 * 보는 일이라, 상자를 누르면 그 단계에서 멈춘 문서만 남는다. */
const S = { led: null, src: "", next: "", q: "" };
const $ = (id) => document.getElementById(id);
const esc = (s) => (s || "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmtAt = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d) ? "—" : d.toLocaleString("ko-KR", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
};

/* 다음 걸음의 표시 순서 — 파이프라인 순서 그대로. "" 는 전체, null 은 완료. */
const NEXTS = ["수집", "변환", "구조화"];

async function load() {
  try {
    const r = await fetch("/v1/lineage");
    if (!r.ok) throw new Error(`${r.status}`);
    S.led = await r.json();
  } catch (e) {
    $("banner").textContent = `원장을 못 읽었습니다 — ${e.message}`;
    $("banner").classList.remove("hidden");
    return;
  }
  $("banner").classList.add("hidden");
  render();
}

/* ---------------------------------------------------------------- 깔때기 */
function funnelCard(src, items) {
  const n = { items: items.length, col: 0, needCv: 0, cv: 0, st: 0 };
  for (const it of items) {
    n.col += it.collected.done ? 1 : 0;
    if (it.converted.required) { n.needCv += 1; n.cv += it.converted.done ? 1 : 0; }
    n.st += it.structured.done ? 1 : 0;
  }
  // 단계 상자: 분모는 "그 단계에 올 자격이 있는 수"다 — 변환은 요구분만.
  const stage = (label, got, of, filter) => {
    const full = of > 0 && got === of;
    return `<button class="stg ${full ? "ok" : got === 0 && of > 0 ? "zero" : "part"}"
      data-src="${esc(src)}" data-next="${filter}"
      title="${esc(label)} — ${got}/${of}. 누르면 이 단계에서 멈춘 문서만 봅니다">
      <span class="sl">${esc(label)}</span><span class="sv">${got}<i>/${of}</i></span></button>`;
  };
  let h = `<div class="fcard"><div class="fsrc">${esc(src)}
             <span class="sub">${n.items}건</span></div><div class="flow">`;
  h += stage("수집", n.col, n.items, "수집");
  if (n.needCv) h += `<span class="arr">→</span>` + stage("변환", n.cv, n.needCv, "변환");
  h += `<span class="arr">→</span>` + stage("구조화", n.st, n.col, "구조화");
  return h + `</div></div>`;
}

function renderFunnel() {
  const bySrc = new Map();
  for (const it of S.led.items) {
    if (!bySrc.has(it.source)) bySrc.set(it.source, []);
    bySrc.get(it.source).push(it);
  }
  let h = "";
  for (const [src, items] of [...bySrc.entries()].sort()) h += funnelCard(src, items);

  // 연결은 문서가 아니라 말뭉치의 국면이다 — 출처 카드와 나란히, 따로 선다.
  const L = S.led.links;
  h += `<div class="fcard phase"><div class="fsrc">연결 <span class="sub">말뭉치 국면</span></div>
    <div class="flow"><a class="stg ${L.present ? (L.edges ? "ok" : "part") : "zero"}" href="/links/"
      title="확정 간선과 settle 이력 — 참조 화면으로 갑니다">
      <span class="sl">${L.present ? "확정 간선" : "미실행"}</span>
      <span class="sv">${L.edges}</span></a>
    <span class="runmeta">${L.last_run
      ? `마지막 settle ${fmtAt(L.last_run.at)} · ${esc(String(L.last_run.saved))}건 확정`
      : "settle 이력 없음"}</span></div></div>`;

  const X = S.led.extras;
  if (X.length) {
    const stale = X.filter((e) => e.stale).length;
    h += `<div class="fcard phase"><div class="fsrc">원장 밖 <span class="sub">수집분과 조인 안 됨</span></div>
      <div class="flow"><button class="stg ${stale ? "zero" : "part"}" data-extras="1"
        title="스토어에 있는데 현재 수집분 어느 본문과도 sha 가 안 맞는 문서">
        <span class="sl">${stale ? `낡음 ${stale} 포함` : "수집 밖 유입"}</span>
        <span class="sv">${X.length}</span></button></div></div>`;
  }
  $("funnel").innerHTML = h;

  for (const b of $("funnel").querySelectorAll("button.stg")) {
    b.addEventListener("click", () => {
      if (b.dataset.extras) {
        $("extras").scrollIntoView({ behavior: "smooth" });
        return;
      }
      S.src = b.dataset.src; S.next = b.dataset.next;
      renderTabs(); renderRows();
    });
  }
}

/* ------------------------------------------------------------------ 필터 */
function tab(label, on, val, host) {
  const b = document.createElement("button");
  b.textContent = label;
  b.className = on ? "on" : "";
  b.addEventListener("click", () => { Object.assign(S, val); renderTabs(); renderRows(); });
  host.appendChild(b);
}

function renderTabs() {
  const srcs = [...new Set(S.led.items.map((i) => i.source))].sort();
  const st = $("srcTabs"); st.innerHTML = "";
  tab("전체 출처", S.src === "", { src: "" }, st);
  for (const s of srcs) tab(s, S.src === s, { src: s }, st);

  const counts = {};
  for (const it of S.led.items)
    if (!S.src || it.source === S.src)
      counts[it.next ?? "완료"] = (counts[it.next ?? "완료"] || 0) + 1;
  const nt = $("nextTabs"); nt.innerHTML = "";
  tab("다음 할 일 전체", S.next === "", { next: "" }, nt);
  for (const n of NEXTS)
    if (counts[n]) tab(`${n} ${counts[n]}`, S.next === n, { next: n }, nt);
  if (counts["완료"]) tab(`완료 ${counts["완료"]}`, S.next === "완료", { next: "완료" }, nt);
}

/* -------------------------------------------------------------------- 표 */
function cellCollected(it) {
  if (it.collected.done) return `<td class="ok">✓</td>`;
  return `<td class="warn" title="수집이 끝나지 않았습니다 — collect.py 재실행 대상">
    ${esc(it.collected.status || "미확보")}</td>`;
}

function cellConverted(it) {
  const c = it.converted;
  const annex = c.annex_hwp
    ? `<span class="sub" title="별표서식 hwp 사이드카 — 본문 관문이 아니라 손실 기록">별표 ${c.annex_md}/${c.annex_hwp}</span>` : "";
  if (!c.required) return `<td class="na">—${annex ? " " + annex : ""}</td>`;
  return c.done ? `<td class="ok">✓ ${annex}</td>`
                : `<td class="wait">대기 ${annex}</td>`;
}

function cellStructured(it) {
  const s = it.structured;
  if (!s.done) return `<td class="wait">대기</td>`;
  const gate = s.passed === false
    ? ` <span class="warn" title="적합 게이트 불합격 — 검수 필요">불합격</span>` : "";
  return `<td class="ok"><a href="/structure/?doc=${esc(it.doc_id)}"
    title="구조 검수로 — ${esc(fmtAt(s.at))}">✓ 열기</a>${gate}</td>`;
}

function row(it) {
  const links = (it.linked.out || it.linked.in)
    ? `${it.linked.out}→ · →${it.linked.in}` : "—";
  const nxt = it.next
    ? `<span class="next n-${esc(it.next)}">${esc(it.next)}</span>`
    : `<span class="next done">완료</span>`;
  return `<tr>
    <td class="dim">${esc(it.source)}</td>
    <td class="name" title="${esc(it.body_file || "")}">${esc(it.name)}</td>
    <td class="dim" title="${esc(it.route.via)}">${esc(it.route.family || it.body_format || "?")}</td>
    ${cellCollected(it)}${cellConverted(it)}${cellStructured(it)}
    <td class="dim" title="확정 간선 — 나감·들어옴">${links}</td>
    <td>${nxt}</td></tr>`;
}

function renderRows() {
  const q = S.q.trim();
  const rows = S.led.items.filter((it) =>
    (!S.src || it.source === S.src)
    && (!S.next || (S.next === "완료" ? it.next === null : it.next === S.next))
    && (!q || (it.name || "").includes(q)));
  $("rows").innerHTML = rows.map(row).join("")
    || `<tr><td colspan="8" class="dim empty">해당 없음</td></tr>`;
}

/* ---------------------------------------------------------------- 원장 밖 */
function renderExtras() {
  const X = S.led.extras;
  const host = $("extras");
  host.classList.toggle("hidden", !X.length);
  if (!X.length) return;
  host.innerHTML = `<h2>원장 밖 ${X.length}건 — 스토어에 있는데 수집분과 조인되지 않음</h2>`
    + `<div class="gridwrap"><table class="grid"><thead><tr>
        <th>문서</th><th>doc_id</th><th>판정</th><th>구조화 시각</th></tr></thead><tbody>`
    + X.map((e) => `<tr>
        <td class="name"><a href="/structure/?doc=${esc(e.doc_id)}">${esc(e.name || "(이름 없음)")}</a></td>
        <td class="dim mono">${esc(e.doc_id)}</td>
        <td class="${e.stale ? "warn" : "dim"}">${esc(e.reason)}</td>
        <td class="dim">${fmtAt(e.at)}</td></tr>`).join("")
    + `</tbody></table></div>`;
}

/* ------------------------------------------------------------------ 조립 */
function render() {
  const items = S.led.items;
  const st = items.filter((i) => i.structured.done).length;
  $("meta").textContent = `수집 ${items.length} · 구조화 ${st + S.led.extras.length}`
    + ` (조인 ${st} · 밖 ${S.led.extras.length}) · 확정 간선 ${S.led.links.edges}`;
  renderFunnel();
  renderTabs();
  renderRows();
  renderExtras();
}

$("q").addEventListener("input", (e) => { S.q = e.target.value; renderRows(); });
$("reload").addEventListener("click", load);
load();
