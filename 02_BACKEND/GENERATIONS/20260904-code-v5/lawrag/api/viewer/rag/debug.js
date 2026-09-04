/* RAG 디버깅 화면 — /v1/rag/debug 한 번으로 다 그린다.
 *
 * 왼쪽은 질의 로그(무엇을 물었나), 오른쪽은 고른 질의의 전모(사다리·근거·
 * LLM 판정/교정·피드백·답 첫머리), 아래는 두 백로그다:
 *   착지 교정   "제2조가 아니라 제2조 제3항" — 승인하면 간선이 그 좌표로 옮겨 앉는다
 *   오참조·무관 "이 간선은 틀렸다" — 승인하면 참조 닫힘에서 빠진다
 * 반영은 전부 사람 승인이다 — LLM 기록은 후보일 뿐이라는 규율을 화면이 지킨다. */
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const tail = (p) => {
  const parts = String(p || "").split(" ▸ ").filter(Boolean);
  return parts.slice(-2).join(" ▸ ") || p || "";
};

const S = { data: null, sel: null, limit: 100 };
const clip = (s, n) => (String(s).length > n ? String(s).slice(0, n) + "…" : String(s));

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return r.json();
}

async function load() {
  try {
    S.data = await api(`/v1/rag/debug?limit=${S.limit}`);
  } catch (err) {
    $("qlist").innerHTML = `<span class="sub">불러오기 실패: ${esc(err.message)}</span>`;
    return;
  }
  // 딥링크·백로그가 가리킨 질의가 목록 한도 밖이면 — 한도를 넓혀 한 번 더
  if (S.sel && S.limit < 500
      && !(S.data.tuples || []).some((t) => t.qid === S.sel)) {
    S.limit = 500;
    return load();
  }
  renderStats();
  renderList();
  renderBacklog();
  if (S.sel) renderDetail(S.sel);
}

/* ------------------------------------------------------------- 품질 통계 */
function renderStats() {
  const s = S.data.stats;
  const rate = s.피드백 ? Math.round(s.정답 / s.피드백 * 100) : null;
  $("stats").innerHTML = `
    <span class="stat"><b>${s.질의}</b> 질의</span>
    <span class="stat ok"><b>${s.answerable}</b> 답변됨</span>
    <span class="stat ${rate == null ? "" : rate >= 70 ? "ok" : "bad"}">
      <b>${rate == null ? "—" : rate + "%"}</b> 정답률
      <span class="sub">(피드백 ${s.피드백}건: 정답 ${s.정답} · 오답 ${s.오답})</span></span>
    <span class="stat warn"><b>${s.지문}</b> 판정 지문</span>
    <span class="stat"><b>${s.교정}</b> 착지 교정</span>
    <span class="stat"><b>${s.억제_규칙}</b> 억제 규칙</span>
    <span class="stat"><b>${s.재지정_규칙}</b> 재지정 규칙</span>`;
}

/* ------------------------------------------------------------- 질의 목록 */
function fbBadge(t) {
  const fb = t.피드백;
  if (!fb) return `<span class="badge">미평가</span>`;
  return fb.판정 === "정답" ? `<span class="badge ok">정답</span>`
                            : `<span class="badge bad">오답</span>`;
}

function renderList() {
  const rows = S.data.tuples || [];
  $("qStats").textContent = `${rows.length}건`;
  $("qlist").innerHTML = rows.map((t) => `
    <div class="qrow ${S.sel === t.qid ? "on" : ""}" data-qid="${esc(t.qid)}">
      ${fbBadge(t)}
      ${t.answerable === false ? `<span class="badge warn">답없음</span>` : ""}
      ${(t.지문 || []).length ? `<span class="badge bad">지문 ${t.지문.length}</span>` : ""}
      ${(t.교정 || []).length ? `<span class="badge">교정 ${t.교정.length}</span>` : ""}
      <span class="q" title="${esc(t.질의)}">${esc(t.질의)}</span>
      <span class="ts">${esc((t.ts || "").slice(5, 16).replace("T", " "))}</span>
    </div>`).join("") || `<span class="sub">아직 질의가 없습니다 — /rag/ 에서 물어보세요</span>`;
  $("qlist").querySelectorAll(".qrow").forEach((el) => {
    el.onclick = () => { S.sel = el.dataset.qid; renderList(); renderDetail(S.sel); };
  });
}

/* ------------------------------------------------------------- 상세 */
function renderDetail(qid) {
  const t = (S.data.tuples || []).find((x) => x.qid === qid);
  if (!t) { $("detail").innerHTML = ""; return; }
  $("dHint").textContent = `${t.qid} · ${t.mode || ""}`;
  const fb = t.피드백;
  const usage = t.usage
    ? Object.entries(t.usage).map(([k, v]) =>
        `${k} ${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ") : "";
  $("detail").innerHTML = `
    <h3>질문</h3>
    <div>${esc(t.질의)}</div>

    <h3>주입 프롬프트 — 지식이 어떻게 들어갔나</h3>
    ${t.프롬프트 ? `<details class="bkprompt">
        <summary>system + user([질문]+[컨텍스트]) 펼치기 — 답 합성에 실제로 들어간 원문</summary>
        <div class="plabel">system</div>
        <pre>${esc(t.프롬프트.system || "")}</pre>
        <div class="plabel">user — [질문] + [컨텍스트]</div>
        <pre>${esc(t.프롬프트.user || "")}</pre>
      </details>` : `<span class="sub">기록 없음 — 프롬프트 저장 이전의 질의</span>`}

    <h3>답 전문 ${t.answerable === false ? '<span class="badge warn">답없음</span>' : ""}</h3>
    <div class="ans">${esc(t.답 || "(기록 없음 — 답 저장 이전의 질의)")}</div>

    <h3>어떻게 찾았나</h3>
    <ol class="ldr">${(t.ladder || []).map((s) => `
      <li><b>${esc(s.stage || "")}</b> ${s.count ?? ""}건 ${esc(s.note || "")}</li>`).join("")}
    </ol>
    ${t.recovery ? `<div class="kv"><span class="badge warn">탐험
      ${esc((t.recovery.rungs_fired || []).join(" → ") || "빈손")}</span></div>` : ""}
    ${t.filter && t.filter.applied ? `<div class="kv sub">필터: ${t.filter.in} → ${t.filter.out}
      (${esc(t.filter.reason || "")})</div>` : ""}

    <h3>회수 구역 — 어느 단이 무엇을 데려왔나 (${(t.context || []).length})</h3>
    ${(t.context || []).map((c) => `
      <div class="ref">
        <span class="n">[${c.n}]</span>
        <span class="badge ${c.kind === "벡터" ? "warn" : ""}">${esc(c.kind || "?")}</span>
        <span title="${esc(c.matched || "")}">${esc(c.doc || "")} ▸ ${esc(c.path || "")}</span>
        <span class="sub">${(t.cited || []).includes(c.n) ? "인용됨" : ""}</span>
      </div>`).join("") || `<span class="sub">회수 기록 없음 (이 항목 저장 이전의 질의)</span>`}

    <h3>근거 (${(t.refs || []).length})</h3>
    ${(t.refs || []).map((r) => `
      <div class="ref">
        ${r.n != null ? `<span class="n">[${r.n}]</span>` : ""}
        <a href="/structure/?doc=${encodeURIComponent(r.doc_id || "")}${r.node != null ? `&node=${r.node}` : ""}"
           target="_blank">${esc(r.doc || r.doc_id)} ▸ ${esc(r.path || `구역 ${r.node ?? "?"}`)}</a>
        <span class="sub">p.${r.page ?? "?"}</span>
      </div>`).join("") || `<span class="sub">근거 없음</span>`}

    <h3>LLM 착지 교정 (${(t.교정 || []).length})</h3>
    ${(t.교정 || []).map((f, i) => `
      <div class="mark fix" data-mk="교정" data-i="${i}">
        <span class="badge">${esc((f.간선 || {}).surface || "")}</span>
        ${esc(tail((f.간선 || {}).dst_path))}
        <span class="arrow">⤷</span> <b>${esc(tail(f.새_dst_path))}</b>
        ${editBits(f, "교정", i)}
        <div class="why">${esc(f.사유 || "")}</div>
        ${histBits(f)}
      </div>`).join("") || `<span class="sub">이 질의에서 교정 없음</span>`}

    <h3>LLM 판정 지문 (${(t.지문 || []).length})</h3>
    ${(t.지문 || []).map((d, i) => `
      <div class="mark ${d.판정 === "무관" || d.판정 === "오참조" ? "bad" : ""}"
           data-mk="지문" data-i="${i}">
        <span class="badge ${d.판정 === "오참조" ? "bad" : d.판정 === "무관" ? "warn" : "ok"}">${esc(d.판정)}</span>
        ${d.간선 ? `${esc(tail(d.간선.src_path))} <span class="arrow">→</span>
                    ${esc(tail(d.간선.dst_path))}
                    <span class="badge">${esc(d.간선.surface || "")}</span>` : ""}
        ${editBits(d, "지문", i)}
        <div class="why">${esc(d.사유 || "")}</div>
        ${histBits(d)}
      </div>`).join("") || `<span class="sub">이 질의에서 지문 없음</span>`}

    <h3>사용자 피드백</h3>
    ${fb ? `<div class="mark ${fb.판정 === "정답" ? "" : "bad"}">
        <span class="badge ${fb.판정 === "정답" ? "ok" : "bad"}">${esc(fb.판정)}</span>
        ${fb.기대 ? `기대: ${esc(fb.기대.doc || "")} ▸ ${esc(fb.기대.path || `구역 ${fb.기대.node}`)}` : ""}
        ${fb.메모 ? `<div class="why">${esc(fb.메모)}</div>` : ""}
      </div>` : `<span class="sub">아직 없음 — /rag/ 화면의 "맞아요/이게 아니에요"가 여기 쌓입니다</span>`}

    ${t.timing ? `<h3>시간 — 스트리밍 실측</h3>
      <div class="sub">답 첫 글자 <b>${t.timing.answer_ttft_ms ?? "?"}ms</b>
        · 합성 전체 ${t.timing.answer_ms ?? "?"}ms</div>
      <div class="sub">${(t.timing.calls || []).map((c) =>
        `${esc(c.kind)} ${c.dur_ms}ms(첫 ${c.ttft_ms}ms)`).join(" · ")}</div>` : ""}
    ${usage ? `<h3>토큰</h3><div class="sub">${esc(usage)}</div>` : ""}`;
  wireEdits(qid, t);
}

/* --------------------------------------------------- LLM 판단 수정
 * "오참조라 했는데 실제로는 맞는 연결이다" — 판단 JSON 을 사람이 고친다.
 * 원본은 남고 수정 레코드가 겹쳐 읽히며(서버 _effective), 이력이 붙는다.
 * 지문의 판정을 "정상"으로 고치면 백로그에서도 빠진다. */
function editBits(row, kind, i) {
  return `<button class="mkedit" data-kind="${kind}" data-i="${i}"
            title="판단 JSON 을 수정한다 — 이력이 남는다">✎ 수정</button>`
    + (row.수정이력 ? `<span class="badge ok">수정됨 ${row.수정이력.length}</span>` : "");
}

function histBits(row) {
  if (!row.수정이력) return "";
  return `<details class="hist"><summary>수정 이력 ${row.수정이력.length}건</summary>
    ${row.수정이력.map((h) => `
      <div class="histrow">
        <span class="sub">${esc((h.ts || "").slice(5, 16).replace("T", " "))}</span>
        ${esc(JSON.stringify(h.before))} → <b>${esc(JSON.stringify(h.after))}</b>
        ${h.메모 ? `<span class="sub">— ${esc(h.메모)}</span>` : ""}
      </div>`).join("")}</details>`;
}

function wireEdits(qid, t) {
  $("detail").querySelectorAll(".mkedit").forEach((b) => {
    b.onclick = () => {
      const kind = b.dataset.kind, i = +b.dataset.i;
      const row = (kind === "지문" ? t.지문 : t.교정)[i];
      const seed = kind === "지문"
        ? { 판정: row.판정, 사유: row.사유 }
        : { 새_dst: row.새_dst, 새_dst_path: row.새_dst_path, 사유: row.사유 };
      const box = b.closest(".mark");
      box.innerHTML = `
        <div class="sub" style="margin-bottom:4px">${kind} 수정 — 허용 필드:
          판정(무관·오참조·정상)·사유·간선·새_dst·새_dst_path.
          지문을 "정상"으로 고치면 백로그에서 빠집니다.</div>
        <textarea class="mkjson" rows="4">${esc(JSON.stringify(seed, null, 1))}</textarea>
        <input class="mknote" placeholder="메모 (선택) — 왜 고치나">
        <div class="acts" style="margin-top:5px">
          <button class="yes mksave">저장</button>
          <button class="no mkcancel">취소</button>
        </div>`;
      box.querySelector(".mkcancel").onclick = () => renderDetail(qid);
      box.querySelector(".mksave").onclick = async () => {
        let after;
        try { after = JSON.parse(box.querySelector(".mkjson").value); }
        catch { alert("JSON 이 올바르지 않습니다"); return; }
        try {
          await api("/v1/rag/verdicts/edit", {
            method: "POST", headers: { "content-type": "application/json" },
            body: JSON.stringify({ qid, target: kind, idx: i, after,
                                   note: box.querySelector(".mknote").value.trim() }),
          });
        } catch (err) { alert("수정 실패: " + err.message); return; }
        await load();                        // 수정본이 겹쳐 읽힌 채로 다시 그린다
      };
    };
  });
}

/* ------------------------------------------------------------- 백로그
 * 공용 카드(backlog.js) — 토글 펼침, 경로→PDF 패널, 질의 칩→카드 안 Q/A 스위칭. */
let BKD = null;
function renderBacklog() {
  if (!BKD) BKD = bkMount({ edges: $("verdicts"), fixes: $("fixes"),
                            stats: $("vdStats"), fixStats: $("fxStats") });
  BKD.refresh(S.data);
}

$("reload").onclick = load;
// 딥링크 — /rag/ 의 최근 질의에서 "디버깅 화면에서 보기"로 넘어오면 그 질의를 편다
const qid0 = new URLSearchParams(location.search).get("qid");
if (qid0) S.sel = qid0;
load();
