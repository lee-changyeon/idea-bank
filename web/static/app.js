// 아이디어뱅크 온라인 — 사용자 앱 (창안자·사업자). 해시 라우팅 SPA, 빌드 없음.
"use strict";
const { api, html, raw, esc, kst, kstFull, won, stampBadge, toast, sha256Hex, b64, download, busy } = IB;
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const main = $("#main");
let ME = null;
let LIMITS = { max_file: 20 * 1048576, max_total: 200 * 1048576, direct: false }; // 서버가 /api/me 로 알려 준다
const mb = (n) => `${Math.round(n / 1048576)}MB`;

const LEVELS = {
  private: ["비공개", "나만 봅니다. 목록에도 나오지 않습니다."],
  summary: ["요약 공개", "제목·요약·태그만 사업자에게 보입니다."],
  nda: ["NDA 후 전문 공개", "요약을 보고 NDA에 서명한 사업자만 전문을 봅니다."],
};
const PAY = { upfront: "계약금", royalty: "매출 로열티", profit: "이익 배당", equity: "지분" };

// ───────── 공통 ─────────
function render(content) { main.innerHTML = String(content); main.focus({ preventScroll: true }); window.scrollTo(0, 0); }
function go(hash) { if (location.hash === hash) route(); else location.hash = hash; }
function navLinks() {
  const links = !ME ? [["#/", "소개"], ["#/verify", "검증"]]
    : ME.role === "creator"
      ? [["#/new", "등록"], ["#/vault", "보관함"], ["#/views", "열람 기록"], ["#/loans", "대출 신청함"], ["#/verify", "검증"]]
      : [["#/market", "아이디어 둘러보기"], ["#/activity", "내 NDA·신청"], ["#/verify", "검증"]];
  const cur = location.hash.split("?")[0] || "#/";
  $("#nav").innerHTML = links.map(([h, t]) => {
    const on = cur === h || (h !== "#/" && cur.startsWith(h + "/")) || (h === "#/vault" && cur.startsWith("#/idea/")) || (h === "#/market" && cur.startsWith("#/market/"));
    return `<a href="${h}" class="${on ? "on" : ""}">${esc(t)}</a>`;
  }).join("");
  $("#who").innerHTML = ME
    ? String(html`<span class="role">${ME.role_label}</span><span class="nm">${ME.name}${ME.org ? ` · ${ME.org}` : ""}</span><button class="linkbtn" id="logout">로그아웃</button>`)
    : String(html`<a class="btn sm" href="#/login">로그인</a><a class="btn sm primary" href="#/signup">회원가입</a>`);
  const lo = $("#logout");
  if (lo) lo.onclick = async () => { await api("POST", "/api/logout"); ME = null; IB.setCsrf(null); go("#/"); };
}
function needRole(role) {
  if (!ME) { go("#/login?next=" + encodeURIComponent(location.hash)); return false; }
  if (role && ME.role !== role) { render(html`<div class="card empty">이 화면은 ${role === "creator" ? "창안자" : "사업자"} 계정으로 볼 수 있습니다.</div>`); return false; }
  return true;
}
const loading = () => render('<div class="empty"><span class="spin"></span> 불러오는 중</div>');
const errorView = (e) => render(html`<div class="card empty"><p class="err">${e.message}</p><a class="btn" href="#/">처음으로</a></div>`);
const tags = (ts) => (ts || []).map((t) => `#${esc(t)}`).join(" ");
const lvlBadge = (d) => html`<span class="badge ${d === "private" ? "" : d === "nda" ? "ink" : "info"}">${LEVELS[d][0]}</span>`;
const fmtSize = (n) => (n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`);

function termsList(t) {
  const pay = Object.entries(t.pay || {}).map(([k, v]) => {
    if (k === "upfront") return `계약금 ${won(v.amount)}`;
    if (k === "equity") return `지분 ${v.pct}%`;
    if (k === "royalty") return `매출 로열티 ${v.pct}%` + (v.annual_cap ? ` (연 상한 ${won(v.annual_cap)})` : "") + ` · ${v.years}년`;
    if (k === "profit") return `이익 배당 연동 ${v.pct}%`;
    return k;
  });
  return html`<dl class="facts">
    <div><dt>사용 분야 (제3조)</dt><dd>${t.field}</dd></div>
    <div><dt>독점 여부 · 지역 · 기간</dt><dd>${t.exclusive ? "독점" : "비독점"} · ${t.territory} · ${t.term_years}년</dd></div>
    <div><dt>대가 (제5조)</dt><dd>${pay.join(" / ")}</dd></div>
    <div><dt>첫 서비스 출시 목표 (제7조)</dt><dd>약정일부터 ${t.mvp_months}개월</dd></div>
    ${t.message ? html`<div><dt>메시지</dt><dd class="body-text">${t.message}</dd></div>` : ""}
  </dl>`;
}
const loanBadge = (l) => html`<span class="badge ${l.status === "approved" ? "ok" : l.status === "rejected" ? "bad" : "wait"}">${l.status_label}</span>`;

// ───────── 소개·로그인 ─────────
function viewHome() {
  if (ME) return go(ME.role === "creator" ? "#/vault" : "#/market");
  render(html`
  <section class="hero">
    <div>
      <h1>생각한 날을 증명하고,<br>아이디어를 안전하게 빌려 주세요</h1>
      <p>특허로 지키기 어려운 아이디어를 적립하면 <b>고유 지문</b>과 외부 기관의 <b>공인 시각</b>이 찍힙니다.
      사업자는 NDA에 서명해야 전문을 볼 수 있고, 모든 열람은 기록되어 창안자에게 보입니다.</p>
      <div class="btns"><a class="btn primary" href="#/signup">무료로 시작하기</a><a class="btn" href="#/login">로그인</a><a class="btn" href="#/verify">증명 파일 검증</a></div>
    </div>
    <ol class="flow">
      <li><i>1</i><div><b>창안자: 적립</b><br><span class="muted small">아이디어를 적고 등록하면 고유 지문과 공인 시각을 받습니다.</span></div></li>
      <li><i>2</i><div><b>공개 단계 선택</b><br><span class="muted small">비공개 / 요약 공개 / NDA 후 전문 공개</span></div></li>
      <li><i>3</i><div><b>사업자: NDA 서명 후 열람</b><br><span class="muted small">서명과 열람이 모두 원장에 남고 공인 시각을 받습니다.</span></div></li>
      <li><i>4</i><div><b>아이디어 대출 신청</b><br><span class="muted small">사용 범위와 대가(계약금·로열티·이익 배당·지분)를 정해 신청합니다.</span></div></li>
    </ol>
  </section>`);
}

function viewLogin(q) {
  render(html`<div class="auth card stack">
    <div><h1>로그인</h1><p class="lead">창안자·사업자 공용 로그인입니다.</p></div>
    <form class="form" id="f">
      <div class="field"><label for="em">이메일</label><input id="em" name="email" type="email" autocomplete="username" required></div>
      <div class="field"><label for="pw">비밀번호</label><input id="pw" name="password" type="password" autocomplete="current-password" required></div>
      <p class="err" id="msg" hidden></p>
      <button class="btn primary">로그인</button>
      <p class="small muted">계정이 없나요? <a href="#/signup">회원가입</a></p>
    </form></div>`);
  $("#f").onsubmit = async (ev) => {
    ev.preventDefault();
    try {
      const r = await busy(ev.submitter, () => api("POST", "/api/login", IB.formData(ev.target)));
      ME = r.user;
      go(q.get("next") || (ME.role === "creator" ? "#/vault" : "#/market"));
    } catch (e) { $("#msg").hidden = false; $("#msg").textContent = e.message; }
  };
}

function viewSignup() {
  render(html`<div class="auth card stack">
    <div><h1>회원가입</h1><p class="lead">어떤 분으로 쓰실지 골라 주세요.</p></div>
    <form class="form" id="f">
      <div class="seg two" role="radiogroup" aria-label="회원 유형">
        <label><input type="radio" name="role" value="creator" checked><b>창안자</b><span>아이디어를 적립하고 빌려 줍니다</span></label>
        <label><input type="radio" name="role" value="business"><b>사업자</b><span>아이디어를 찾아 빌려 사업화합니다</span></label>
      </div>
      <div class="field"><label for="nm">이름<span class="req">*</span></label><input id="nm" name="name" type="text" autocomplete="name" required><span class="hint">NDA 서명에 이 이름을 씁니다.</span></div>
      <div class="field" id="orgf" hidden><label for="org">회사(기관) 이름<span class="req">*</span></label><input id="org" name="org" type="text" autocomplete="organization"></div>
      <div class="field"><label for="em">이메일<span class="req">*</span></label><input id="em" name="email" type="email" autocomplete="email" required></div>
      <div class="field"><label for="pw">비밀번호<span class="req">*</span></label><input id="pw" name="password" type="password" autocomplete="new-password" minlength="8" required><span class="hint">8자 이상</span></div>
      <p class="err" id="msg" hidden></p>
      <button class="btn primary">가입하기</button>
    </form></div>`);
  const sync = () => { $("#orgf").hidden = $("input[name=role]:checked").value !== "business"; };
  $$("input[name=role]").forEach((r) => (r.onchange = sync));
  $("#f").onsubmit = async (ev) => {
    ev.preventDefault();
    try {
      const r = await busy(ev.submitter, () => api("POST", "/api/signup", IB.formData(ev.target)));
      ME = r.user; toast("가입했습니다. 환영합니다!");
      go(ME.role === "creator" ? "#/new" : "#/market");
    } catch (e) { $("#msg").hidden = false; $("#msg").textContent = e.message; }
  };
}

// ───────── 창안자: 등록 ─────────
async function viewNew(q) {
  if (!needRole("creator")) return;
  let parent = null;
  if (q.get("parent")) { try { parent = await api("GET", `/api/my/ideas/${encodeURIComponent(q.get("parent"))}`); } catch (e) { return errorView(e); } }
  const files = [];
  render(html`<div class="head-row"><div><h1>${parent ? `개정판 등록 (v${parent.version + 1})` : "아이디어 등록"}</h1>
    <p class="lead">${parent ? `원본 ${parent.idea_no} 은 그대로 남고, 새 판이 이어서 기록됩니다.` : "적고 등록하면 고유 지문과 공인 시각이 찍힙니다."}</p></div></div>
  <form class="grid2" id="f">
    <div class="card form">
      <div class="field"><label for="ti">제목<span class="req">*</span></label><input id="ti" name="title" type="text" maxlength="200" required value="${parent ? parent.title : ""}" placeholder="예) 자전거 거치대 겸용 우산꽂이"></div>
      <div class="field"><label for="bo">내용<span class="req">*</span></label>
        <textarea id="bo" name="body" required placeholder="[무엇] …&#10;[왜] …&#10;[어떻게] …&#10;[특징] …">${parent ? parent.body : ""}</textarea>
        <span class="hint">"무엇을, 왜, 어떻게"가 드러나게 적으면 나중에 증거로 쓰기 좋습니다.</span></div>
      <div class="field"><label for="tg">태그</label><input id="tg" name="tags" type="text" value="${parent ? parent.tags.join(", ") : ""}" placeholder="쉼표로 구분: 생활용품, 자전거"></div>
      <div class="field"><span class="lbl">첨부파일</span>
        <label class="drop" id="drop" for="fi">파일을 끌어다 놓거나 눌러서 고르세요 (파일당 ${mb(LIMITS.max_file)}${LIMITS.max_total < 50 * 1048576 ? `, 합계 ${mb(LIMITS.max_total)}` : ""})</label>
        <input id="fi" type="file" multiple hidden>
        <ul class="files" id="fl"></ul></div>
    </div>
    <div class="stack">
      <div class="card form">
        <h2>공개 단계</h2>
        <div class="seg col" id="lv">${Object.entries(LEVELS).map(([k, [t, d]]) => html`<label><input type="radio" name="disclosure" value="${k}" ${k === "private" ? raw("checked") : ""}><b>${t}</b><span>${d}</span></label>`)}</div>
        <div class="field" id="sumf" hidden><label for="sm">공개 요약<span class="req">*</span></label>
          <textarea id="sm" name="summary" class="short" maxlength="2000" placeholder="사업자가 먼저 보는 짧은 소개. 핵심 비법은 적지 마세요."></textarea>
          <span class="hint">전문은 공개되지 않습니다. 공개 단계는 나중에 바꿀 수 있습니다.</span></div>
      </div>
      <div class="card form">
        <label class="check"><input type="checkbox" name="timestamp" checked><span><b>공인 시각 받기</b><br><span class="hint">외부 기관(DigiCert 등)에 고유 지문만 보내 시각 서명을 받습니다. 내용은 보내지 않습니다.</span></span></label>
        <label class="check"><input type="checkbox" id="ok" required><span>등록한 내용은 <b>고칠 수도 지울 수도 없다</b>는 것을 확인했습니다. (바꾸려면 개정판을 등록합니다)</span></label>
        <p class="err" id="msg" hidden></p>
        <button class="btn primary">등록하기</button>
      </div>
    </div>
  </form>`);
  const drawFiles = () => {
    $("#fl").innerHTML = files.map((f, i) => `<li><span>${esc(f.name)}</span><small class="muted">${fmtSize(f.size)}</small><button type="button" class="x" data-i="${i}" aria-label="빼기">✕</button></li>`).join("");
    $$("#fl .x").forEach((b) => (b.onclick = () => { files.splice(+b.dataset.i, 1); drawFiles(); }));
  };
  const add = (list) => {
    for (const f of list) {
      const total = files.reduce((n, x) => n + x.size, 0);
      if (f.size > LIMITS.max_file) toast(`${f.name}: ${mb(LIMITS.max_file)}를 넘습니다`, true);
      else if (total + f.size > LIMITS.max_total) toast(`첨부 합계가 ${mb(LIMITS.max_total)}를 넘습니다`, true);
      else files.push(f);
    }
    drawFiles();
  };
  $("#fi").onchange = (e) => { add(e.target.files); e.target.value = ""; };
  const drop = $("#drop");
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); add(e.dataTransfer.files); };
  const syncLv = () => { const v = $("input[name=disclosure]:checked").value; $("#sumf").hidden = v === "private"; $("#sm").required = v !== "private"; };
  $$("input[name=disclosure]").forEach((r) => (r.onchange = syncLv));
  $("#f").onsubmit = async (ev) => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    try {
      const d = await busy(ev.submitter, async () => api("POST", "/api/my/ideas", {
        title: fd.get("title"), body: fd.get("body"), tags: String(fd.get("tags") || "").split(/[,\n]/).map((s) => s.trim()).filter(Boolean),
        disclosure: fd.get("disclosure"), summary: fd.get("summary") || "", timestamp: !!fd.get("timestamp"),
        parent_seq: parent ? parent.seq : null,
        attachments: await prepareFiles(files, ev.submitter),
      }));
      sessionStorage.setItem("ib_new", d.seq);
      go(`#/idea/${d.seq}`);
    } catch (e) { $("#msg").hidden = false; $("#msg").textContent = e.message; }
  };
}

// 첨부 준비: 온라인은 Storage 로 직접 올리고(파일당 20MB) 경로만 보낸다. 로컬은 내용을 그대로 보낸다.
async function prepareFiles(files, btn) {
  const out = [];
  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    const mime = f.type || "application/octet-stream";
    if (!LIMITS.direct) { out.push({ name: f.name, mime, data_b64: b64(await f.arrayBuffer()) }); continue; }
    if (btn) btn.innerHTML = `<span class="spin"></span> 첨부 올리는 중 (${i + 1}/${files.length})`;
    const up = await api("POST", "/api/my/uploads", { name: f.name, size: f.size, mime });
    const r = await fetch(up.url, { method: "PUT", headers: { "Content-Type": mime, "x-upsert": "false" }, body: f });
    if (!r.ok) throw new Error(`첨부 '${f.name}' 를 올리지 못했습니다 (${r.status}). 다시 시도해 주세요.`);
    out.push({ name: f.name, mime, upload_path: up.path });
  }
  if (btn && files.length) btn.innerHTML = '<span class="spin"></span> 등록 중';
  return out;
}

// ───────── 창안자: 보관함 ─────────
async function viewVault(q) {
  if (!needRole("creator")) return;
  const term = q.get("q") || "";
  let r;
  try { r = await api("GET", "/api/my/ideas?q=" + encodeURIComponent(term)); } catch (e) { return errorView(e); }
  render(html`<div class="head-row"><div><h1>내 보관함</h1><p class="lead">등록한 아이디어 ${r.ideas.length}건</p></div><a class="btn primary" href="#/new">＋ 새 아이디어</a></div>
  <form class="search" id="s"><input type="search" name="q" value="${term}" placeholder="제목·내용·태그·등록번호 검색" aria-label="검색"><button class="btn">찾기</button></form>
  <div class="list">${r.ideas.length ? r.ideas.map((d) => html`<a class="item" href="#/idea/${d.seq}">
      <span class="no">${d.idea_no} · v${d.version}</span>
      <h3>${d.title}</h3>
      <span class="meta">${tags(d.tags) ? raw(tags(d.tags) + " · ") : ""}등록 ${kst(d.created_at, false)} · 열람 ${d.view_count} · NDA ${d.nda_count} · 대출 신청 ${d.loan_count}</span>
      <span class="side">${stampBadge(d.tsa_time)}${lvlBadge(d.disclosure)}${d.hidden ? html`<span class="badge bad">운영자 숨김</span>` : ""}</span>
    </a>`) : html`<div class="card empty">${term ? "찾는 아이디어가 없습니다." : raw('아직 등록한 아이디어가 없습니다. <a href="#/new">첫 아이디어 등록하기</a>')}</div>`}</div>`);
  $("#s").onsubmit = (e) => { e.preventDefault(); go("#/vault?q=" + encodeURIComponent(new FormData(e.target).get("q"))); };
}

function viewsTable(views, withIdea) {
  if (!views.length) return html`<p class="muted small">아직 열람 기록이 없습니다.</p>`;
  return html`<div class="tbl"><table class="t stack-sm"><thead><tr>${withIdea ? html`<th>아이디어</th>` : ""}<th>열람자</th><th>범위</th><th>열람 시각</th><th>공인 시각</th><th>기록 지문</th></tr></thead><tbody>
    ${views.map((v) => html`<tr>
      ${withIdea ? html`<td data-l="아이디어"><a href="#/idea/${v.idea_seq}">${v.title}</a><br><span class="mono muted">${v.idea_no}</span></td>` : ""}
      <td data-l="열람자"><b>${v.viewer}</b><br><span class="muted small">${v.org}</span></td>
      <td data-l="범위"><span class="badge ${v.level === "summary" ? "" : "ink"}">${v.level_label}</span>${v.detail ? html` <span class="small">${v.detail}</span>` : ""}</td>
      <td data-l="열람 시각">${kst(v.at)}</td>
      <td data-l="공인 시각">${v.tsa_time ? kst(v.tsa_time) : html`<span class="badge wait">대기</span>`}</td>
      <td data-l="기록 지문"><span class="mono muted" title="${v.event_hash}">${v.event_hash.slice(0, 16)}…</span></td>
    </tr>`)}</tbody></table></div>`;
}

function loanCard(l, opts = {}) {
  return html`<div class="card stack" id="loan-${l.id}">
    <div class="head-row"><div><span class="mono muted">${l.loan_no}</span><h3>${opts.showIdea ? l.title : `${l.org} · ${l.business}`}</h3>
      <span class="small muted">${opts.showIdea ? `${l.idea_no} · ${l.org} · ` : ""}신청 ${kst(l.created_at)} ${l.tsa_time ? `· 공인 시각 ${kst(l.tsa_time)}` : ""}</span></div>
      <div class="btns">${loanBadge(l)}<span class="badge">창안자 ${l.creator_response_label}</span></div></div>
    ${termsList(l.terms)}
    ${l.review_note ? html`<div class="note ${l.status === "rejected" ? "bad" : "ok"}"><b>심사 의견</b><p>${l.review_note}</p></div>` : ""}
    ${l.creator_note ? html`<div class="note"><b>창안자 의견</b><p>${l.creator_note}</p></div>` : ""}
    ${l.contract ? html`<div class="note ok"><b>계약 기록 ${l.contract.contract_no}</b><p>약정일 ${l.contract.signed_on}</p></div>` : ""}
    ${opts.respond && l.status === "submitted" ? html`<form class="form respond" data-id="${l.id}">
      <div class="field"><label>창안자 의견 (선택)</label><textarea name="note" class="short" placeholder="조건에 대한 의견을 남기면 운영팀 심사에 참고됩니다."></textarea></div>
      <div class="btns"><button class="btn primary" name="accept" value="1">조건에 동의</button><button class="btn danger" name="accept" value="0">거절</button></div></form>` : ""}
  </div>`;
}
function bindRespond(after) {
  $$("form.respond").forEach((f) => (f.onsubmit = async (ev) => {
    ev.preventDefault();
    const accept = ev.submitter.value === "1";
    await busy(ev.submitter, () => api("POST", `/api/my/loans/${f.dataset.id}/respond`, { accept, note: new FormData(f).get("note") }));
    toast(accept ? "조건에 동의했습니다. 운영팀 심사 뒤 계약이 진행됩니다." : "신청을 거절했습니다.");
    after();
  }));
}

// ───────── 창안자: 아이디어 상세 ─────────
async function viewIdea(seq) {
  if (!needRole("creator")) return;
  let d;
  try { d = await api("GET", `/api/my/ideas/${seq}`); } catch (e) { return errorView(e); }
  const fresh = sessionStorage.getItem("ib_new") === String(d.seq);
  sessionStorage.removeItem("ib_new");
  render(html`
  ${fresh ? html`<div class="note ${d.tsa_time ? "ok" : "amber"}"><b>${d.tsa_time ? "등록되었습니다. 공인 시각을 받았습니다." : "등록되었습니다. 공인 시각은 아직 대기 중입니다."}</b>
    <p>등록번호 <b class="mono">${d.idea_no}</b>${d.tsa_time ? ` · 공인 시각 ${kstFull(d.tsa_time)}` : " · 오른쪽 [공인 시각 다시 받기]를 눌러 주세요."}</p></div><br>` : ""}
  <div class="grid2">
    <div class="stack">
      <article class="card stack">
        <div><span class="mono muted">${d.idea_no} · v${d.version}</span><h1>${d.title}</h1>
          <div class="btns">${lvlBadge(d.disclosure)}${d.hidden ? html`<span class="badge bad">운영자가 공개 목록에서 숨김</span>` : ""}<span class="tag">${raw(tags(d.tags))}</span></div></div>
        <p class="body-text">${d.body}</p>
        ${d.attachments.length ? html`<div><span class="lbl">첨부파일</span><ul class="files">${d.attachments.map((a) => html`<li><span>${a.name}</span><small class="muted">${fmtSize(a.size)}</small><button class="btn sm dl" data-path="/api/my/ideas/${d.seq}/files/${a.sha256}">받기</button></li>`)}</ul></div>` : ""}
      </article>

      <section class="card stack" id="disc">
        <div><h2>공개 단계</h2><p class="small muted">바꿀 때마다 원장에 기록됩니다. 아이디어 원문(고유 지문)은 바뀌지 않습니다.</p></div>
        <form class="form" id="df">
          <div class="seg">${Object.entries(LEVELS).map(([k, [t, ds]]) => html`<label><input type="radio" name="level" value="${k}" ${k === d.disclosure ? raw("checked") : ""}><b>${t}</b><span>${ds}</span></label>`)}</div>
          <div class="field"><label for="sm">공개 요약</label><textarea id="sm" name="summary" class="short" maxlength="2000">${d.summary}</textarea><span class="hint">사업자는 요약만 먼저 봅니다. 핵심 비법은 적지 마세요.</span></div>
          <div><button class="btn primary">공개 단계 저장</button></div>
        </form>
      </section>

      <section class="card stack"><div><h2>열람 기록</h2><p class="small muted">누가 언제 무엇을 봤는지. 모든 열람은 원장에 기록되고 공인 시각을 받습니다.</p></div>${viewsTable(d.views, false)}</section>

      <section class="card stack"><h2>NDA 서명</h2>
        ${d.ndas.length ? html`<div class="tbl"><table class="t stack-sm"><thead><tr><th>서명자</th><th>서명 시각</th><th>공인 시각</th><th>NDA 문서 지문</th></tr></thead><tbody>
          ${d.ndas.map((n) => html`<tr><td data-l="서명자"><b>${n.signer_name}</b><br><span class="small muted">${n.org}</span></td><td data-l="서명 시각">${kst(n.signed_at)}</td><td data-l="공인 시각">${n.tsa_time ? kst(n.tsa_time) : "대기"}</td><td data-l="문서 지문"><span class="mono muted">${n.doc_hash.slice(0, 16)}…</span></td></tr>`)}
        </tbody></table></div>` : html`<p class="muted small">아직 NDA 서명이 없습니다.</p>`}
      </section>

      <section class="stack"><h2>대출 신청</h2>${d.loans.length ? d.loans.map((l) => loanCard(l, { respond: true })) : html`<div class="card"><p class="muted small">아직 대출 신청이 없습니다.</p></div>`}</section>
    </div>

    <aside class="stack">
      <div class="card">
        <dl class="facts">
          <div><dt>등록번호</dt><dd class="mono">${d.idea_no}</dd></div>
          <div><dt>등록 시각</dt><dd>${kstFull(d.created_at)}</dd></div>
          <div class="hl"><dt>공인 시각</dt><dd>${d.tsa_time ? html`${kstFull(d.tsa_time)}<br><span class="small muted">${d.tsa_url}</span>` : html`<span class="badge wait">대기 중</span>`}</dd></div>
          <div><dt>고유 지문 (SHA-256)</dt><dd class="mono">${d.content_hash}</dd></div>
          <div><dt>원장 위치</dt><dd class="small">${d.event_seq}번째 기록<br><span class="mono muted">고리값 ${d.entry_hash.slice(0, 24)}…</span></dd></div>
        </dl>
      </div>
      <div class="card stack">
        <div class="btns">
          <a class="btn primary" href="#/cert/${d.seq}">확인서 보기·인쇄</a>
          <button class="btn dl" data-path="/api/my/ideas/${d.seq}/bundle">증명 파일(zip)</button>
          <a class="btn" href="#/new?parent=${d.seq}">개정판 등록</a>
          ${d.tsa_time ? "" : html`<button class="btn amber" id="restamp">공인 시각 다시 받기</button>`}
        </div>
        <p class="small muted">증명 파일만 있으면 이 서비스 없이도 openssl 등으로 직접 검증할 수 있습니다.</p>
      </div>
      <div class="card"><h3>개정 이력</h3><ol class="timeline">${d.revisions.map((r) => html`<li class="${r.seq === d.seq ? "cur" : ""}"><span class="v">v${r.version}</span><a href="#/idea/${r.seq}">${kst(r.created_at, false).slice(0, 10)} ${r.title}</a></li>`)}</ol></div>
      <div class="card"><h3>원장 기록</h3><ul class="events">${d.history.map((e) => html`<li><b>${e.kind_label}</b><span class="small muted">${kst(e.created_at)} · ${e.tsa_time ? `공인 시각 ${kst(e.tsa_time)}` : "공인 시각 대기"}</span><span class="mono muted">#${e.seq} ${e.content_hash.slice(0, 20)}…</span></li>`)}</ul></div>
    </aside>
  </div>`);
  $$(".dl").forEach((b) => (b.onclick = () => busy(b, () => download(b.dataset.path))));
  const rs = $("#restamp");
  if (rs) rs.onclick = () => busy(rs, () => api("POST", `/api/my/ideas/${d.seq}/timestamp`)).then(() => { toast("공인 시각을 받았습니다."); route(); });
  $("#df").onsubmit = async (ev) => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    await busy(ev.submitter, () => api("POST", `/api/my/ideas/${d.seq}/disclosure`, { level: fd.get("level"), summary: fd.get("summary") }));
    toast("공개 단계를 저장했습니다."); route();
  };
  bindRespond(route);
}

// ───────── 확인서 ─────────
async function viewCert(seq) {
  if (!needRole("creator")) return;
  let d;
  try { d = await api("GET", `/api/my/ideas/${seq}`); } catch (e) { return errorView(e); }
  render(html`<div class="cert-tools"><a class="btn" href="#/idea/${d.seq}">← 돌아가기</a><button class="btn primary" id="pr">인쇄 / PDF로 저장</button></div>
  <div class="cert">
    <div class="head"><img src="/logo.svg" alt=""><div class="org">퍼스트프린트(FirstPrint)<br>아이디어뱅크 온라인</div></div>
    <h1>확 인 서</h1><p class="sub">아이디어 존재 시점 확인</p>
    <table>
      <tr><th>등록번호</th><td>${d.idea_no} (v${d.version})</td></tr>
      <tr><th>제목</th><td>${d.title}</td></tr>
      <tr><th>작성자</th><td>${d.author}</td></tr>
      <tr><th>등록 시각</th><td>${kstFull(d.created_at)}</td></tr>
      <tr><th>공인 시각</th><td class="stampv">${d.tsa_time ? `${kstFull(d.tsa_time)} · ${d.tsa_url}` : "아직 없음"}</td></tr>
      <tr><th>고유 지문</th><td class="mono">${d.content_hash}</td></tr>
      <tr><th>원장 고리값</th><td class="mono">${d.entry_hash}</td></tr>
      ${d.attachments.length ? html`<tr><th>첨부</th><td>${d.attachments.map((a) => html`${a.name} <span class="mono">${a.sha256}</span><br>`)}</td></tr>` : ""}
    </table>
    <p class="statement">위 고유 지문을 가진 아이디어가 ${d.tsa_time ? `공인 시각 ${kstFull(d.tsa_time)}` : `${kstFull(d.created_at)}`}에 존재하였고, 그 뒤 바뀌지 않았음을 확인합니다.
    고유 지문은 증명 파일의 canonical.json 으로 누구나 다시 계산할 수 있습니다.</p>
    <p class="right">발급일 ${kst(new Date().toISOString(), false).slice(0, 10)}</p>
    <div class="limits">이 확인서는 "위 시각에 이 내용이 존재했다"는 사실만 보여 주며, 독창성이나 최초 창안자임을 증명하지 않습니다.
    법적 증거력은 사안에 따라 다를 수 있으니 중요한 사안은 변리사·변호사와 상담하세요.</div>
  </div>`);
  $("#pr").onclick = () => window.print();
}

// ───────── 창안자: 열람 기록·대출 신청함 ─────────
async function viewViews() {
  if (!needRole("creator")) return;
  let r;
  try { r = await api("GET", "/api/my/views"); } catch (e) { return errorView(e); }
  render(html`<h1>열람 기록</h1><p class="lead">내 아이디어를 누가, 언제, 어디까지 봤는지 보여 줍니다. 모든 기록은 원장에 남고 공인 시각을 받습니다.</p>${viewsTable(r.views, true)}`);
}

async function viewLoans() {
  if (!needRole("creator")) return;
  let r;
  try { r = await api("GET", "/api/my/loans"); } catch (e) { return errorView(e); }
  render(html`<h1>대출 신청함</h1><p class="lead">사업자가 보낸 사용권(아이디어 대출) 신청입니다. 조건에 동의하면 운영팀 심사 뒤 계약을 진행합니다.</p>
  <div class="stack">${r.loans.length ? r.loans.map((l) => loanCard(l, { respond: true, showIdea: true })) : html`<div class="card empty">아직 받은 신청이 없습니다.</div>`}</div>
  ${contractsSection(r.contracts)}`);
  bindRespond(route);
}

function contractsSection(cs) {
  if (!cs || !cs.length) return "";
  return html`<h2 class="mt">계약·정산</h2><div class="stack">${cs.map((c) => html`<div class="card stack">
    <div class="head-row"><div><span class="mono muted">${c.contract_no}</span><h3>${c.loan.title}</h3><span class="small muted">${c.loan.org} · 약정일 ${c.signed_on}</span></div><span class="badge ok">계약 기록됨</span></div>
    ${c.settlements.length ? html`<div class="tbl"><table class="t stack-sm"><thead><tr><th>기간</th><th>종류</th><th class="right">금액</th><th>지급일</th><th>공인 시각</th></tr></thead><tbody>
      ${c.settlements.map((s) => html`<tr><td data-l="기간">${s.period}</td><td data-l="종류">${s.kind_label}</td><td data-l="금액" class="right">${won(s.amount)}</td><td data-l="지급일">${s.paid_on || "-"}</td><td data-l="공인 시각">${s.tsa_time ? kst(s.tsa_time) : "대기"}</td></tr>`)}
    </tbody></table></div>` : html`<p class="small muted">아직 정산 기록이 없습니다.</p>`}
  </div>`)}</div>`;
}

// ───────── 사업자 ─────────
async function viewMarket(q) {
  if (!needRole("business")) return;
  const term = q.get("q") || "", tag = q.get("tag") || "";
  let r;
  try { r = await api("GET", `/api/market?q=${encodeURIComponent(term)}&tag=${encodeURIComponent(tag)}`); } catch (e) { return errorView(e); }
  const allTags = [...new Set(r.ideas.flatMap((i) => i.tags))].sort();
  render(html`<h1>아이디어 둘러보기</h1><p class="lead">창안자가 공개한 요약입니다. 전문은 NDA 서명 뒤에 볼 수 있고, 열람은 창안자에게 기록으로 보입니다.</p>
  <form class="search" id="s"><input type="search" name="q" value="${term}" placeholder="제목·요약·태그 검색" aria-label="검색"><button class="btn">찾기</button></form>
  ${allTags.length ? html`<div class="chips">${tag ? html`<button class="chip" data-tag="">전체</button>` : ""}${allTags.map((t) => html`<button class="chip ${t === tag ? "on" : ""}" data-tag="${t}">#${t}</button>`)}</div>` : ""}
  <div class="list">${r.ideas.length ? r.ideas.map((d) => html`<a class="item" href="#/market/${d.seq}">
    <span class="no">${d.idea_no} · 창안자 ${d.owner_name}</span><h3>${d.title}</h3>
    <span class="sum">${d.summary}</span>
    <span class="meta">${raw(tags(d.tags))}</span>
    <span class="side">${stampBadge(d.tsa_time)}${lvlBadge(d.disclosure)}${d.nda_signed ? html`<span class="badge ok">NDA 서명함</span>` : ""}</span>
  </a>`) : html`<div class="card empty">조건에 맞는 공개 아이디어가 없습니다.</div>`}</div>`);
  $("#s").onsubmit = (e) => { e.preventDefault(); go("#/market?q=" + encodeURIComponent(new FormData(e.target).get("q"))); };
  $$(".chip").forEach((c) => (c.onclick = () => go("#/market?tag=" + encodeURIComponent(c.dataset.tag))));
}

async function viewMarketIdea(seq) {
  if (!needRole("business")) return;
  let d;
  try { d = await api("GET", `/api/market/${seq}`); } catch (e) { return errorView(e); }
  const canLoan = d.disclosure === "summary" || d.nda_signed;
  const pending = d.my_loans.some((l) => l.status === "submitted");
  render(html`<p><a href="#/market" class="small">← 목록으로</a></p>
  <div class="grid2">
    <div class="stack">
      <article class="card stack">
        <div><span class="mono muted">${d.idea_no} · v${d.version} · 창안자 ${d.owner_name}</span><h1>${d.title}</h1>
          <div class="btns">${lvlBadge(d.disclosure)}<span class="tag">${raw(tags(d.tags))}</span></div></div>
        <div class="note"><b>공개 요약</b><p class="body-text">${d.summary}</p></div>
        <div id="full"></div>
      </article>

      ${d.disclosure === "nda" && !d.nda_signed ? html`<section class="card stack" id="ndabox">
        <div><h2>NDA 서명 후 전문 보기</h2><p class="small muted">아래 약정을 읽고 서명하면 전문을 볼 수 있습니다. 서명 문서의 고유 지문은 원장에 기록되고 공인 시각을 받습니다.</p></div>
        <pre class="legal" tabindex="0">${d.nda_template.text}</pre>
        <p class="small muted">약정문 판: ${d.nda_template.version} · 약정문 지문 <span class="mono">${d.nda_template.sha256.slice(0, 24)}…</span><br>
        대상 아이디어: ${d.idea_no} · 고유 지문 <span class="mono">${d.content_hash.slice(0, 24)}…</span></p>
        <form class="form" id="nf">
          <div class="field"><label for="sn">서명 (가입한 이름을 그대로 적어 주세요)</label><input id="sn" name="signer_name" type="text" required placeholder="${ME.name}" autocomplete="off"></div>
          <label class="check"><input type="checkbox" name="agree" required><span>위 비밀유지 약정의 내용을 모두 읽었고, <b>${ME.org}</b>을(를) 대표하여 이에 동의합니다.</span></label>
          <p class="err" id="nmsg" hidden></p>
          <div><button class="btn primary">동의하고 서명하기</button></div>
        </form></section>` : ""}

      ${d.nda ? html`<section class="card stack"><div class="head-row"><h2>내 NDA 서명</h2><span class="badge ok">서명 완료</span></div>
        <dl class="facts"><div><dt>서명자</dt><dd>${d.nda.signer_name} · ${d.nda.org}</dd></div>
        <div><dt>서명 시각 / 공인 시각</dt><dd>${kstFull(d.nda.signed_at)}<br>${d.nda.tsa_time ? `공인 시각 ${kstFull(d.nda.tsa_time)}` : "공인 시각 대기"}</dd></div>
        <div><dt>NDA 문서 지문</dt><dd class="mono">${d.nda.doc_hash}</dd></div></dl>
        <div class="note amber small">전문을 열 때마다 열람 기록이 원장에 남고 창안자에게 보입니다.</div>
        <div><button class="btn primary" id="openfull">전문 보기</button></div></section>` : ""}

      ${d.disclosure === "summary" ? html`<div class="note info">창안자가 이 아이디어를 <b>요약 공개</b>로 두었습니다. 전문은 공개되지 않으며, 대출 신청을 보내면 창안자가 검토합니다.</div>` : ""}

      ${d.my_loans.length ? html`<section class="stack"><h2>내 대출 신청</h2>${d.my_loans.map((l) => loanCard(l))}</section>` : ""}

      ${canLoan && !pending ? html`<section class="card stack" id="loanbox">
        <div><h2>대출 신청 (사용권 허락 신청)</h2><p class="small muted">「아이디어 사용권 약정서」(LA-2026-001) 표준 조건을 따릅니다. "대출"은 아이디어 사용권 허락을 뜻하며, 금전 대여가 아닙니다.</p></div>
        <form class="form" id="lf">
          <div class="field"><label for="fd">사용 분야 (제3조)<span class="req">*</span></label><input id="fd" name="field" type="text" required placeholder="예) 아파트 현관용 생활용품 제조·판매"></div>
          <div class="row3">
            <div class="field"><label for="ex">독점 여부</label><select id="ex" name="exclusive"><option value="1">독점</option><option value="0">비독점</option></select></div>
            <div class="field"><label for="tr">지역</label><input id="tr" name="territory" type="text" value="대한민국"></div>
            <div class="field"><label for="ty">기간(년)</label><input id="ty" name="term_years" type="number" min="1" max="30" value="10"></div>
          </div>
          <div class="field"><span class="lbl">대가 방식 (제5조, 둘 이상 고를 수 있음)<span class="req">*</span></span>
            <div class="paybox">
              <label class="check"><input type="checkbox" name="p_upfront"><span><b>(가) 계약금</b> — 약정일부터 30일 안에 지급</span></label>
              <div class="sub" data-for="p_upfront" hidden><div class="field"><label for="ua">금액(원)</label><input id="ua" name="upfront_amount" type="number" min="1" step="1" placeholder="3000000"></div></div>
              <label class="check"><input type="checkbox" name="p_equity"><span><b>(나) 지분</b> — 발행주식 총수 대비 보통주</span></label>
              <div class="sub" data-for="p_equity" hidden><div class="field"><label for="eq">지분율(%)</label><input id="eq" name="equity_pct" type="number" min="0.01" max="100" step="0.01" placeholder="2"></div></div>
              <label class="check"><input type="checkbox" name="p_royalty"><span><b>(다) 매출 로열티</b> — 순매출 대비, 분기 정산</span></label>
              <div class="sub row3" data-for="p_royalty" hidden>
                <div class="field"><label for="rp">요율(%)</label><input id="rp" name="royalty_pct" type="number" min="0.01" max="100" step="0.01" placeholder="3"></div>
                <div class="field"><label for="rc">연간 상한(원)</label><input id="rc" name="royalty_cap" type="number" min="0" step="1" placeholder="0 = 없음"></div>
                <div class="field"><label for="ry">지급 기간(년)</label><input id="ry" name="royalty_years" type="number" min="1" max="30" value="5"></div>
              </div>
              <label class="check"><input type="checkbox" name="p_profit"><span><b>(라) 이익 배당 연동</b> — 배당 총액 대비 추가 지급</span></label>
              <div class="sub" data-for="p_profit" hidden><div class="field"><label for="pp">비율(%)</label><input id="pp" name="profit_pct" type="number" min="0.01" max="100" step="0.01" placeholder="5"></div></div>
            </div></div>
          <div class="field"><label for="mv">첫 서비스(MVP) 출시 목표 (제7조, 개월)</label><input id="mv" name="mvp_months" type="number" min="1" max="60" value="6"></div>
          <div class="field"><label for="ms">창안자에게 보낼 메시지</label><textarea id="ms" name="message" class="short" placeholder="사업화 계획을 간단히 적어 주세요."></textarea></div>
          <div class="note small">신청 내용은 원장에 기록되고 공인 시각을 받습니다. 창안자 응답과 운영팀 심사를 거쳐 정식 약정서를 작성합니다. 대금은 제휴 예탁기관을 통해 지급합니다(데모에서는 모의).</div>
          <p class="err" id="lmsg" hidden></p>
          <div><button class="btn primary">대출 신청 보내기</button></div>
        </form></section>` : ""}
    </div>
    <aside class="stack"><div class="card"><dl class="facts">
      <div><dt>등록번호</dt><dd class="mono">${d.idea_no}</dd></div>
      <div class="hl"><dt>공인 시각 (창안자 적립 시점)</dt><dd>${d.tsa_time ? kstFull(d.tsa_time) : "대기"}</dd></div>
      <div><dt>고유 지문</dt><dd class="mono">${d.content_hash}</dd></div>
      <div><dt>첨부</dt><dd>${d.attachment_count}개 ${d.attachment_count ? "(NDA 후 열람)" : ""}</dd></div>
    </dl></div>
    <div class="note small">이 아이디어는 위 공인 시각에 이미 창안자에게 있었습니다. 열람·서명·신청 기록도 모두 같은 원장에 남습니다.</div></aside>
  </div>`);

  const nf = $("#nf");
  if (nf) nf.onsubmit = async (ev) => {
    ev.preventDefault();
    const fd = new FormData(nf);
    try {
      await busy(ev.submitter, () => api("POST", `/api/market/${d.seq}/nda`, { signer_name: fd.get("signer_name"), agree: !!fd.get("agree"), template_hash: d.nda_template.sha256 }));
      toast("NDA에 서명했습니다. 이제 전문을 볼 수 있습니다."); route();
    } catch (e) { $("#nmsg").hidden = false; $("#nmsg").textContent = e.message; }
  };
  const of = $("#openfull");
  if (of) of.onclick = () => busy(of, async () => {
    const f = await api("GET", `/api/market/${d.seq}/full`);
    $("#full").innerHTML = String(html`<div class="stack"><h2>전문</h2><p class="body-text">${f.body}</p>
      ${f.attachments.length ? html`<div><span class="lbl">첨부파일</span><ul class="files">${f.attachments.map((a) => html`<li><span>${a.name}</span><small class="muted">${fmtSize(a.size)}</small><button class="btn sm dl" data-path="/api/market/${d.seq}/files/${a.sha256}">받기</button></li>`)}</ul></div>` : ""}
      <p class="small muted">작성자 ${f.author} · 등록 ${kstFull(f.created_at)} · 이 열람은 기록되었습니다.</p></div>`);
    $$("#full .dl").forEach((b) => (b.onclick = () => busy(b, () => download(b.dataset.path))));
    of.hidden = true;
    $("#full").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  const lf = $("#lf");
  if (lf) {
    $$(".paybox input[type=checkbox]", lf).forEach((c) => (c.onchange = () => { $(`.sub[data-for=${c.name}]`, lf).hidden = !c.checked; }));
    lf.onsubmit = async (ev) => {
      ev.preventDefault();
      const f = Object.fromEntries(new FormData(lf));
      const pay = {};
      if (f.p_upfront) pay.upfront = { amount: f.upfront_amount };
      if (f.p_equity) pay.equity = { pct: f.equity_pct };
      if (f.p_royalty) pay.royalty = { pct: f.royalty_pct, annual_cap: f.royalty_cap || 0, years: f.royalty_years };
      if (f.p_profit) pay.profit = { pct: f.profit_pct };
      try {
        const l = await busy(ev.submitter, () => api("POST", `/api/market/${d.seq}/loan`, {
          field: f.field, exclusive: f.exclusive === "1", territory: f.territory, term_years: f.term_years, mvp_months: f.mvp_months, message: f.message, pay }));
        toast(`대출 신청 ${l.loan_no} 을 보냈습니다.`); route();
      } catch (e) { $("#lmsg").hidden = false; $("#lmsg").textContent = e.message; }
    };
  }
}

async function viewActivity() {
  if (!needRole("business")) return;
  let r;
  try { r = await api("GET", "/api/biz/activity"); } catch (e) { return errorView(e); }
  render(html`<h1>내 NDA·신청</h1><p class="lead">서명한 NDA와 보낸 대출 신청, 계약 기록입니다.</p>
  <section class="stack"><h2>NDA 서명</h2>${r.ndas.length ? html`<div class="tbl"><table class="t stack-sm"><thead><tr><th>아이디어</th><th>서명 시각</th><th>공인 시각</th><th>NDA 문서 지문</th></tr></thead><tbody>
    ${r.ndas.map((n) => html`<tr><td data-l="아이디어"><a href="#/market/${n.idea_seq}">${n.title}</a><br><span class="mono muted">${n.idea_no}</span></td><td data-l="서명 시각">${kst(n.signed_at)}</td><td data-l="공인 시각">${n.tsa_time ? kst(n.tsa_time) : "대기"}</td><td data-l="문서 지문"><span class="mono muted">${n.doc_hash.slice(0, 16)}…</span></td></tr>`)}
  </tbody></table></div>` : html`<div class="card"><p class="muted small">아직 서명한 NDA가 없습니다.</p></div>`}</section>
  <br><section class="stack"><h2>대출 신청</h2>${r.loans.length ? r.loans.map((l) => loanCard(l, { showIdea: true })) : html`<div class="card"><p class="muted small">아직 보낸 신청이 없습니다.</p></div>`}</section>
  ${contractsSection(r.contracts)}`);
}

// ───────── 검증 (누구나) ─────────
async function viewVerify() {
  let led = null;
  try { led = await api("GET", "/api/ledger"); } catch (_) {}
  render(html`<h1>검증</h1><p class="lead">로그인 없이 누구나 쓸 수 있습니다. 파일은 서버로 보내지 않고 이 브라우저에서 고유 지문만 계산합니다(증명 파일 zip 검사는 예외).</p>
  <div class="cols">
    <section class="card stack"><h2>증명 파일(zip) 검사</h2><p class="small muted">아이디어뱅크에서 내려받은 증명 파일이 바뀌지 않았는지, 공인 시각 서명이 맞는지 확인합니다.</p>
      <label class="drop" for="zf">증명 파일(.zip) 고르기</label><input id="zf" type="file" accept=".zip,application/zip" hidden>
      <div id="zr"></div></section>
    <section class="card stack"><h2>파일·고유 지문으로 찾기</h2><p class="small muted">원본 파일(canonical.json 또는 첨부)을 고르거나 64자리 고유 지문을 붙여 넣으세요.</p>
      <label class="drop" for="hf">아무 파일 고르기 (내용은 보내지 않음)</label><input id="hf" type="file" hidden>
      <form class="search" id="hs"><input type="text" name="h" placeholder="고유 지문 64자리" aria-label="고유 지문" class="mono"><button class="btn">찾기</button></form>
      <div id="hr"></div></section>
  </div>
  ${led ? html`<br><div class="note small"><b>공개 원장 헤드</b> — 기록 ${led.count}건 · 마지막 고리값 <span class="mono">${led.head}</span><p>이 값을 정기적으로 공개해 두면, 운영자도 과거 기록을 몰래 바꿀 수 없습니다.</p>
    <p><button class="btn sm" id="chk">원장 무결성 검사</button></p><div id="chkr"></div></div>` : ""}`);
  const chk = $("#chk");
  if (chk) chk.onclick = async () => {
    $("#chkr").innerHTML = '<p class="small"><span class="spin"></span> 원장 전체를 다시 계산하는 중</p>';
    try {
      const r = await api("GET", "/api/ledger/verify");
      $("#chkr").innerHTML = String(html`<div class="note ${r.ok ? "ok" : "bad"}"><b>${r.ok ? `이상 없음 — 기록 ${r.count}건의 순번·고유 지문·고리값·공인 시각·첨부가 모두 맞습니다` : `문제 ${r.broken.length}건`}</b>
        ${r.pending ? html`<p>공인 시각 대기 ${r.pending}건</p>` : ""}
        ${r.broken.map((b) => html`<p>#${b.seq}: ${b.reason}</p>`)}<p class="mono">${r.head}</p></div>`);
    } catch (err) { $("#chkr").innerHTML = String(html`<p class="err">${err.message}</p>`); }
  };
  $("#zf").onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    if (LIMITS.direct && f.size > 3 * 1048576) {  // 온라인 서버는 요청 4.5MB 한도
      $("#zr").innerHTML = String(html`<div class="note amber"><b>3MB 를 넘는 증명 파일은 이 화면에서 검사할 수 없습니다.</b><p>증명 파일 안의 VERIFY.txt 안내대로 직접 검증하거나, 고유 지문(canonical.json 의 SHA-256)을 오른쪽 칸에서 찾아보세요. 원문 canonical.json 파일을 골라도 됩니다.</p></div>`);
      e.target.value = ""; return;
    }
    $("#zr").innerHTML = '<p class="small"><span class="spin"></span> 검사 중</p>';
    try {
      const r = await api("POST", "/api/verify/bundle", { zip_b64: b64(await f.arrayBuffer()) });
      $("#zr").innerHTML = String(html`<div class="note ${r.ok ? "ok" : "bad"}"><b>${r.ok ? "이상 없음 — 내용이 바뀌지 않았습니다" : "문제가 있습니다"}</b>
        <p>${r.title || ""}${r.author ? ` · ${r.author}` : ""}</p><p class="mono">${r.content_hash}</p></div>
        <ul class="results">${r.checks.map((c) => html`<li class="${c.ok ? "ok" : "bad"}"><span class="ic">${c.ok ? "✓" : "✕"}</span><span><b>${c.name}</b> — ${c.detail}</span></li>`)}</ul>`);
    } catch (err) { $("#zr").innerHTML = String(html`<p class="err">${err.message}</p>`); }
    e.target.value = "";
  };
  const look = async (h, label) => {
    $("#hr").innerHTML = '<p class="small"><span class="spin"></span> 찾는 중</p>';
    try {
      const r = await api("GET", "/api/lookup/" + h);
      const hit = r.ideas.length || r.event;
      $("#hr").innerHTML = String(html`${label ? html`<p class="small muted">${label}</p>` : ""}<p class="mono small">${r.hash}</p>
        <div class="note ${hit ? "ok" : ""}">${hit ? "" : html`<b>원장에서 찾지 못했습니다.</b><p>내용이 한 글자라도 다르면 고유 지문이 완전히 달라집니다.</p>`}
        ${r.ideas.map((i) => html`<p><b>${i.idea_no}</b> (v${i.version}) — ${i.hit === "content" ? "아이디어 원문" : "첨부파일"}과 일치<br>등록 ${kstFull(i.created_at)}<br>${i.tsa_time ? `공인 시각 ${kstFull(i.tsa_time)}` : "공인 시각 대기"}</p>`)}
        ${r.event ? html`<p><b>${r.event.kind_label}</b> 기록 #${r.event.seq}과 일치<br>${r.event.tsa_time ? `공인 시각 ${kstFull(r.event.tsa_time)}` : kstFull(r.event.created_at)}</p>` : ""}
        ${hit ? html`<p class="small muted">비공개 보호를 위해 제목·내용은 보여 주지 않습니다.</p>` : ""}</div>`);
    } catch (err) { $("#hr").innerHTML = String(html`<p class="err">${err.message}</p>`); }
  };
  $("#hf").onchange = async (e) => { const f = e.target.files[0]; if (!f) return; look(await sha256Hex(await f.arrayBuffer()), f.name); e.target.value = ""; };
  $("#hs").onsubmit = (e) => { e.preventDefault(); look(String(new FormData(e.target).get("h")).trim().toLowerCase()); };
}

// ───────── 라우터 ─────────
const ROUTES = [
  [/^#?\/?$/, viewHome], [/^#\/login$/, viewLogin], [/^#\/signup$/, viewSignup],
  [/^#\/new$/, viewNew], [/^#\/vault$/, viewVault], [/^#\/idea\/(\d+)$/, viewIdea], [/^#\/cert\/(\d+)$/, viewCert],
  [/^#\/views$/, viewViews], [/^#\/loans$/, viewLoans],
  [/^#\/market$/, viewMarket], [/^#\/market\/(\d+)$/, viewMarketIdea], [/^#\/activity$/, viewActivity],
  [/^#\/verify$/, viewVerify],
];
async function route() {
  const [path, qs] = (location.hash || "#/").split("?");
  const q = new URLSearchParams(qs || "");
  navLinks();
  for (const [rx, fn] of ROUTES) {
    const m = rx.exec(path);
    if (m) {
      if (m[1]) loading();
      try { await fn(m[1] ? m[1] : q, q); } catch (e) { if (!e.status) console.error(e); }
      return;
    }
  }
  render('<div class="card empty">없는 화면입니다. <a href="#/">처음으로</a></div>');
}
// m[1] 이 있으면 fn(id, q), 없으면 fn(q)
window.addEventListener("hashchange", route);
(async () => {
  try { const r = await api("GET", "/api/me"); ME = r.user; if (r.limits) LIMITS = r.limits; } catch (_) {}
  route();
})();
