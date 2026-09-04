/* 질의응답 화면 — /v1/rag/ask 를 부르고, 경로(사다리·탐험)를 그대로 보여 주고,
 * 피드백을 진단 튜플로 돌려보낸다. 근거는 전부 구조 뷰어 딥링크다. */
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

const S = { qid: null, question: "" };
const clip2 = (s, n) => (String(s).length > n ? String(s).slice(0, n) + "…" : String(s));

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return r.json();
}

/* ---------------------------------------------------------------- 스코프 */
// 스코프 목록 — yml 정의(해석 결과·못 찾은 이름) + 내장. 비어 있는 스코프는
// 고를 수 있되 표시해 둔다(질의가 400 으로 바로 알려 준다).
(async () => {
  try {
    const r = await api("/v1/rag/scopes");
    const sel = $("optScope");
    for (const s of r.scopes || []) {
      const o = document.createElement("option");
      o.value = s.name;
      o.textContent = `${s.name} (${s.count})` + (s.missing && s.missing.length ? " ⚠" : "");
      o.title = (s.description || "") + (s.missing && s.missing.length
        ? `\n못 찾은 이름: ${s.missing.join(", ")}` : "")
        + (s.documents && s.documents.length ? `\n${s.documents.slice(0, 12).join("\n")}` : "");
      sel.appendChild(o);
    }
    const saved = localStorage.getItem("rag.scope") || "";
    if (saved && [...sel.options].some((o) => o.value === saved)) sel.value = saved;
    sel.addEventListener("change", () => localStorage.setItem("rag.scope", sel.value));
  } catch (_) { /* 스코프 목록이 없어도 질의는 된다 */ }
})();

/* ---------------------------------------------------------------- 묻기 */
$("askForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("q").value.trim();
  if (!q) return;
  $("askBtn").disabled = true;
  $("askBtn").textContent = "찾는 중…";
  $("result").classList.remove("hidden");
  $("answer").className = "answer";
  $("answer").textContent = "…";
  $("refs").innerHTML = "";
  $("fb").classList.add("hidden");
  $("fbPick").classList.add("hidden");
  $("fbDone").classList.add("hidden");
  $("nudge").classList.add("hidden");
  try {
    const out = await api("/v1/rag/ask", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ question: q, filter: $("optFilter").checked,
                             recover: $("optRecover").checked,
                             mode: $("optRetriever").value || "legalclosure",
                             scope: $("optScope").value || "" }),
    });
    render(out);
  } catch (err) {
    $("answer").className = "answer err";
    $("answer").textContent = "실패: " + err.message;
    $("trailPane").classList.add("hidden");
  } finally {
    $("askBtn").disabled = false;
    $("askBtn").textContent = "묻기";
  }
});

function render(out) {
  S.qid = out.qid || null;
  S.question = out.question;

  $("answer").className = "answer" + (out.answerable === false ? " err" : "");
  $("answer").textContent = out.answer || out.ask_user || "(답 없음)";

  // 벡터 모드의 출처는 정적(회수 집합 전체) — kind(벡터/참조)와 모델이
  // 실제로 인용한 번호(cited)를 함께 보여 준다. 행을 누르면 오른쪽 PDF
  // 패널에 그 자리(앵커 상자)가 뜬다 — 새 탭 없이 바로 확인한다.
  const cited = new Set(out.cited || []);
  $("refs").innerHTML = (out.refs || []).map((r) => `
    <div class="ref"><span class="n">[${r.n ?? ""}]</span>
      ${r.kind ? `<span class="badge ${r.kind === "벡터" ? "warn" : ""}"
                   title="${esc(r.matched || "")}">${esc(r.kind)}</span>` : ""}
      ${r.scope_out ? `<span class="badge warn" title="질의 범위 밖 문서 — 간선(배제·위임·준용…)으로 동반됨">범위 밖</span>` : ""}
      ${r.node != null ? `<a class="pplink" data-pp data-doc="${esc(r.doc_id)}"
           data-node="${r.node}" data-label="${esc(pathTail(r.path || ""))}"
           title="누르면 오른쪽에 원문 PDF 가 뜹니다">${esc(r.doc || r.doc_id)} ▸ ${esc(r.path || `구역 ${r.node}`)}</a>`
        : `<a href="${esc(r.link)}" target="_blank">${esc(r.doc || r.doc_id)} ▸ ${esc(r.path || "")}</a>`}
      <a class="go" href="${esc(r.link)}" target="_blank" title="구조 뷰어에서 열기">↗</a>
      <span class="sub">p.${r.page ?? "?"}${cited.has(r.n) ? " · 인용됨" : ""}</span></div>`).join("");

  // 경로 — 사다리 단마다 몇 건이 잡혔나. 탐험이 돌았으면 발화 단이 표시된다.
  const rungs = (out.recovery && out.recovery.rungs_fired) || [];
  $("trailPane").classList.remove("hidden");
  $("trailMode").textContent = (out.mode ? `검색 모드: ${out.mode}` : "")
    + (out.scope ? ` · 범위: ${out.scope.name} (${out.scope.count}문서`
        + (out.scope.out_of_scope ? `, 밖 동반 ${out.scope.out_of_scope}` : "")
        + (out.scope.dropped && out.scope.dropped.length ? `, 밖 진입 ${out.scope.dropped.length} 버림` : "")
        + ")" : "");
  $("trail").innerHTML = (out.ladder || []).map((step) => {
    const stage = step.stage || step.단 || step.mode || JSON.stringify(step);
    const cnt = step.count ?? step.hits ?? "";
    const hit = rungs.includes(step.stage) || (typeof cnt === "number" && cnt > 0);
    return `<li><span class="stage ${hit ? "hit" : ""}">${esc(stage)}</span>
            <span class="cnt">${cnt !== "" ? cnt + "건" : ""} ${esc(step.note || "")}</span></li>`;
  }).join("");
  if (rungs.length)
    $("trail").innerHTML += `<li><span class="stage hit">탐험 발화</span>
      <span class="cnt">${esc(rungs.join(" → "))}</span></li>`;

  // 판정 지문 — 이번 답변에서 "잘못 끌려왔다"고 찍힌 구역. 기록일 뿐이며
  // 반영(간선 억제)은 아래 백로그에서 사람이 승인해야 일어난다.
  if (out.discards && out.discards.length) {
    $("refs").innerHTML += `<div class="sub" style="margin-top:6px">
      판정 지문 ${out.discards.length}건 — ${out.discards.map((d) =>
        `<span class="badge ${d.kind === "오참조" ? "bad" : ""}"
          title="${esc(d.reason)}">${esc(d.kind)} [${d.n}]</span>`).join(" ")}
      → 아래 백로그에 기록됨</div>`;
  }

  // 빈약한 답의 다음 걸음 — 답이 못 섰거나, 근거가 없거나, 정상 회수가 실패해
  // 탐험이 돈 경우. 그 순간에만 디버깅 통로를 연다 (평소엔 조용하다).
  const weak = out.answerable === false || !(out.refs || []).length || rungs.length;
  $("nudge").classList.toggle("hidden", !weak);
  if (weak) {
    const why = out.answerable === false ? "답을 세우지 못했습니다"
      : !(out.refs || []).length ? "근거 구역이 하나도 실리지 않았습니다"
      : "정상 회수가 빈손이라 회복 사다리(탐험)가 돌았습니다";
    $("nudge").innerHTML = `⚠ ${why} — 아래 <b>어떻게 찾았나</b>에서 어느 단이
      비었는지 보이고, ${S.qid ? `<a class="qlink"
        href="/rag/debug.html?qid=${encodeURIComponent(S.qid)}">디버깅 화면</a>에서
      프롬프트·토큰까지 전모가 보입니다.` : "디버깅 화면에서 전모가 보입니다."}
      용어가 없어 못 찾은 것이면 <a class="qlink" href="/glossary/">용어집</a>에
      더해 주세요.`;
  }

  if (S.qid) $("fb").classList.remove("hidden");
  loadTuples();
  loadVerdicts();
}

/* ------------------------------------------------- 판정 백로그
 * 공용 카드(backlog.js) — 머리를 누르면 토글로 펼쳐지고, 경로를 누르면 PDF
 * 패널, 질의 칩을 누르면 카드 안에서 Q/A(질문·프롬프트·답·회수)가 스위칭된다. */
let BKV = null;
function loadVerdicts() {
  if (!BKV) BKV = bkMount({ edges: $("verdicts"), stats: $("vdStats") });
  BKV.refresh().catch(() => {
    $("verdicts").innerHTML = `<span class="sub">백로그를 불러오지 못했습니다</span>`;
  });
}

/* ---------------------------------------------------------------- 피드백 */
$("fbOk").addEventListener("click", () => sendFeedback("정답", null, ""));
$("fbNo").addEventListener("click", async () => {
  $("fbPick").classList.remove("hidden");
  if ($("fbDoc").options.length <= 1) {
    try {
      const d = await api("/v1/rag/links");     // 문서 목록이 실려 온다
      for (const doc of d.docs || [])
        $("fbDoc").add(new Option(doc.doc, doc.doc_id));
    } catch {}
  }
});
$("fbCancel").addEventListener("click", () => $("fbPick").classList.add("hidden"));

$("fbDoc").addEventListener("change", async () => {
  const docId = $("fbDoc").value;
  $("fbNode").innerHTML = "<option value=''>구역 선택…</option>";
  $("fbNode").disabled = !docId;
  $("fbPeek").classList.toggle("hidden", !docId);
  if (!docId) return;
  $("fbPeek").href = `/structure/?doc=${docId}`;
  try {
    const d = await api(`/v1/rag/nodes?doc_id=${encodeURIComponent(docId)}`);
    for (const n of d.nodes || [])
      $("fbNode").add(new Option(
        `${"　".repeat(Math.max(0, (n.level || 1) - 1))}${n.path || "구역 " + n.node} (p.${n.page ?? "?"})`,
        n.node));
  } catch {}
});

async function sendFeedback(verdict, expected, note) {
  if (!S.qid) return;
  try {
    const result = await api("/v1/rag/feedback", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ qid: S.qid, verdict, expected, note }),
    });
    $("fbPick").classList.add("hidden");
    const recovered = result.recovery || {};
    const suggestions = recovered.selected || [];
    const recoveryHtml = suggestions.length ? `
      <div class="muted" style="margin-top:.55rem">검증된 복구 후보 ${suggestions.length}개</div>
      ${suggestions.map((r) => `<div>
        <a class="qlink" href="/structure/?doc=${encodeURIComponent(r.doc_id || "")}&node=${encodeURIComponent(r.node ?? "")}">
          ${esc(r.doc || "법령")} · ${esc(r.path || "조항")}
        </a>
      </div>`).join("")}` : "";
    // 오답이면 다음 걸음까지 말해 준다 — 기록은 후보일 뿐, 백로그 승인이
    // 간선을 억제해야 검색이 실제로 바뀐다 (루프 2의 나머지 절반).
    $("fbDone").innerHTML = verdict === "정답"
      ? "기록했습니다 — 이 질의는 golden 후보입니다"
      : `기록했습니다 — 아래 <a href="#backlog" class="qlink">판정 백로그</a>에
         후보로 쌓입니다. 거기서 승인해야 잘못된 참조 간선이 억제됩니다.${recoveryHtml}`;
    $("fbDone").classList.remove("hidden");
    sessionStorage.removeItem("ui-queue-counts");   // 상단바 배지 즉시 갱신
    loadTuples();
  } catch (err) { alert("피드백 실패: " + err.message); }
}

$("fbSend").addEventListener("click", () => {
  const docId = $("fbDoc").value;
  const node = $("fbNode").value;
  const expected = docId
    ? { doc_id: docId, node: node ? Number(node) : null } : null;
  sendFeedback("오답", expected, $("fbNote").value.trim());
});

/* ---------------------------------------------------------------- 최근 질의
 * 한 줄이 요약이고, 누르면 그 자리에서 전모가 펼쳐진다 — 그때의 질문, 답
 * 전문, 어느 단이 무엇을 데려왔는지(회수 구역·사다리), 근거·교정·지문·피드백.
 * /v1/rag/debug 하나로 다 온다(지문·교정이 qid 로 이미 합쳐져 있다). */
let TUP = [];

async function loadTuples() {
  try {
    const d = await api("/v1/rag/debug?limit=15");
    TUP = d.tuples || [];
    const s = d.stats || {};
    $("tupStats").textContent =
      `${s.질의 ?? TUP.length}건 · 피드백 ${s.피드백 ?? 0}건`
      + ` · 승격 후보 ${s.승격_후보 ?? 0}건 — 줄을 누르면 전체가 보입니다`;
    $("tuples").innerHTML = TUP.map((t, i) => {
      const fb = t.피드백;
      const badge = !fb ? `<span class="badge">미평가</span>`
        : fb.판정 === "정답" ? `<span class="badge ok">정답</span>`
        : `<span class="badge bad">오답</span>`;
      const rec = t.recovery
        ? `<span class="badge warn">탐험 ${esc((t.recovery.rungs_fired || []).join("→") || "빈손")}</span>` : "";
      const marks = ((t.지문 || []).length ? `<span class="badge bad">지문 ${t.지문.length}</span>` : "")
        + ((t.교정 || []).length ? `<span class="badge">교정 ${t.교정.length}</span>` : "");
      return `<div class="tupwrap" data-i="${i}">
        <div class="tup click">${badge}${rec}${marks}
          <span class="q" title="${esc(t.질의)}">${esc(t.질의)}</span>
          <span class="ts">${esc((t.ts || "").slice(5, 16).replace("T", " "))}</span>
        </div>
        <div class="tupdetail hidden"></div>
      </div>`;
    }).join("") || `<span class="sub">아직 질의가 없습니다</span>`;
    $("tuples").querySelectorAll(".tupwrap").forEach((w) => {
      w.querySelector(".tup").onclick = () => {
        const box = w.querySelector(".tupdetail");
        if (!box.classList.contains("hidden")) { box.classList.add("hidden"); return; }
        $("tuples").querySelectorAll(".tupdetail").forEach((b) => b.classList.add("hidden"));
        box.innerHTML = tupDetail(TUP[+w.dataset.i]);
        box.classList.remove("hidden");
      };
    });
  } catch {
    $("tuples").innerHTML = `<span class="sub">튜플을 불러오지 못했습니다</span>`;
  }
}

const pathTail = (p) => String(p || "").split(" ▸ ").filter(Boolean).slice(-2).join(" ▸ ");

/* 질의 하나의 전모 — 질문 → 답 전문 → 어떻게 찾았나 → 회수 구역(어느 단이
 * 데려왔나) → 근거 → LLM 교정·지문 → 피드백. 좌표는 전부 구조 뷰어 딥링크다. */
function tupDetail(t) {
  if (!t) return "";
  const cited = new Set(t.cited || []);
  const ctx = (t.context || []).map((c) => `
    <div class="ctxrow">
      <span class="n">[${c.n}]</span>
      <span class="badge ${c.kind === "벡터" ? "warn" : String(c.kind || "").startsWith("참조") ? "" : "ok"}">${esc(c.kind || "?")}</span>
      ${c.node != null ? `<a class="pplink q" data-pp data-doc="${esc(c.doc_id)}"
           data-node="${c.node}" data-label="${esc(pathTail(c.path || ""))}"
           title="${esc(c.doc || "")} ▸ ${esc(c.path || "")}">${esc(c.doc || "")} ▸ ${esc(c.path || "")}</a>`
        : `<span class="q" title="${esc(c.doc || "")} ▸ ${esc(c.path || "")}">${esc(c.doc || "")} ▸ ${esc(c.path || "")}</span>`}
      <span class="sub" title="${esc(c.matched || "")}">${esc(c.matched || "")}${cited.has(c.n) ? " · 인용됨" : ""}</span>
    </div>`).join("");
  const fb = t.피드백;
  return `
    <h4>질문</h4>
    <div>${esc(t.질의)}</div>

    <h4>주입 프롬프트 — 지식이 어떻게 들어갔나</h4>
    ${t.프롬프트 ? `<details class="bkprompt">
        <summary>system + user([질문]+[컨텍스트]) 펼치기 — 답 합성에 실제로 들어간 원문</summary>
        <div class="plabel">system</div>
        <pre>${esc(t.프롬프트.system || "")}</pre>
        <div class="plabel">user — [질문] + [컨텍스트]</div>
        <pre>${esc(t.프롬프트.user || "")}</pre>
      </details>` : `<span class="sub">기록 없음 — 프롬프트 저장 이전의 질의</span>`}

    <h4>답 전문 ${t.answerable === false ? '<span class="badge warn">답없음</span>' : ""}</h4>
    <div class="ans">${esc(t.답 || "(기록 없음 — 답 전문 저장 이전의 질의)")}</div>

    <h4>어떻게 찾았나 ${t.mode ? `<span class="badge">${esc(t.mode)}</span>` : ""}</h4>
    <ol class="trail">${(t.ladder || []).map((s) => `
      <li><span class="stage ${(s.count ?? 0) > 0 ? "hit" : ""}">${esc(s.stage || "")}</span>
          <span class="cnt">${s.count ?? ""}건 ${esc(s.note || "")}</span></li>`).join("")}
    </ol>
    ${t.recovery ? `<div class="sub">탐험 발화: ${esc((t.recovery.rungs_fired || []).join(" → ") || "빈손")}</div>` : ""}
    ${t.filter && t.filter.applied ? `<div class="sub">필터: ${t.filter.in} → ${t.filter.out} (${esc(t.filter.reason || "")})</div>` : ""}

    <h4>회수 구역 — 어느 단이 무엇을 데려왔나 (${(t.context || []).length})</h4>
    ${ctx || `<span class="sub">회수 기록 없음 (이 항목 저장 이전의 질의)</span>`}

    <h4>근거 (${(t.refs || []).length})</h4>
    ${(t.refs || []).map((r) => `
      <div class="ref">${r.n != null ? `<span class="n">[${r.n}]</span>` : ""}
        ${r.node != null ? `<a class="pplink" data-pp data-doc="${esc(r.doc_id)}"
             data-node="${r.node}" data-label="${esc(pathTail(r.path || ""))}">${esc(r.doc || r.doc_id)} ▸ ${esc(r.path || `구역 ${r.node}`)}</a>`
          : `<span>${esc(r.doc || r.doc_id)}</span>`}
        <a class="go" href="/structure/?doc=${encodeURIComponent(r.doc_id || "")}${r.node != null ? `&node=${r.node}` : ""}"
           target="_blank" title="구조 뷰어">↗</a>
        <span class="sub">p.${r.page ?? "?"}</span></div>`).join("")
      || `<span class="sub">근거 없음</span>`}

    ${(t.교정 || []).length ? `<h4>LLM 착지 교정 (${t.교정.length})</h4>` + t.교정.map((f) => `
      <div class="ctxrow"><span class="badge">${esc((f.간선 || {}).surface || "")}</span>
        ${esc(pathTail((f.간선 || {}).dst_path))} ⤷ <b>${esc(pathTail(f.새_dst_path))}</b>
        <span class="sub">${esc(f.사유 || "")}</span></div>`).join("") : ""}

    ${(t.지문 || []).length ? `<h4>LLM 판정 지문 (${t.지문.length})</h4>` + t.지문.map((d) => `
      <div class="ctxrow"><span class="badge ${d.판정 === "오참조" ? "bad" : "warn"}">${esc(d.판정)}</span>
        ${d.간선 ? `${esc(pathTail(d.간선.src_path))} → ${esc(pathTail(d.간선.dst_path))}` : ""}
        <span class="sub">${esc(d.사유 || "")}</span></div>`).join("") : ""}

    ${fb ? `<h4>피드백</h4>
      <div class="ctxrow"><span class="badge ${fb.판정 === "정답" ? "ok" : "bad"}">${esc(fb.판정)}</span>
        ${fb.기대 ? `기대: ${esc(fb.기대.doc || "")} ▸ ${esc(fb.기대.path || `구역 ${fb.기대.node}`)}` : ""}
        <span class="sub">${esc(fb.메모 || "")}</span></div>` : ""}

    <div style="margin-top:8px">
      <a class="navlink" href="/rag/debug.html?qid=${encodeURIComponent(t.qid)}">디버깅 화면에서 보기 →</a>
    </div>`;
}

/* 판정 백로그 ↔ 최근 질의 — 탭 스위칭. 백로그(검수할 것)가 기본이다. */
function setBkTab(bk) {
  $("tabBk").classList.toggle("on", bk);
  $("tabTup").classList.toggle("on", !bk);
  $("verdicts").classList.toggle("hidden", !bk);
  $("vdStats").classList.toggle("hidden", !bk);
  $("tuples").classList.toggle("hidden", bk);
  $("tupStats").classList.toggle("hidden", bk);
}
$("tabBk").onclick = () => setBkTab(true);
$("tabTup").onclick = () => setBkTab(false);

(async function init() {
  // 딥링크 ①: ?q=<질문> — 용어집 "이 용어로 질의 →" 등 다른 화면이 질문을
  // 실어 보낸다. 채워만 두지 않고 바로 묻는다 — 오는 목적이 그것이다.
  const q0 = new URLSearchParams(location.search).get("q");
  if (q0) {
    $("q").value = q0;
    $("askForm").requestSubmit();
  }
  // 딥링크 ②: #backlog — 홈 할 일·상단바 배지가 검수할 것으로 바로 보낸다
  if (location.hash === "#backlog")
    $("backlog")?.scrollIntoView({ block: "start" });
  try {
    const d = await api("/v1/rag/search?q=__ping__");
    $("summary").textContent = `문서 ${d.documents}건 · 색인 ${d.entries}줄`;
  } catch { $("summary").textContent = "색인 상태를 읽지 못했습니다"; }
  loadTuples();
  loadVerdicts();
})();
