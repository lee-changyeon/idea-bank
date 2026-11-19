// 아이디어뱅크 관리자 사이트. 사용자 로그인과 분리된 관리자 세션(ib_admin)으로만 동작한다.
"use strict";
const { api, html, raw, esc, kst, kstFull, won, toast, busy } = IB;
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const main = $("#main");
let ME = null;
let POLICY = { launched: false, min_len: 4, strong_rule: "12자 이상, 영문 소문자·대문자·숫자·특수문자 중 3가지 이상" };
let MUST = false; // 정식 서비스 중 약한 비밀번호 → 바꾸기 전에는 다른 화면을 못 씀
let MUST2FA = false; // 정식 서비스 중 2단계 인증 꺼짐 → 켜기 전에는 다른 화면을 못 씀
const setMe = (r) => { ME = r.admin; if (r.policy) POLICY = r.policy; MUST = !!r.must_change; MUST2FA = !!r.must_2fa; };
const pwHint = () => (POLICY.launched ? POLICY.strong_rule : `${POLICY.min_len}자 이상 (정식 서비스 전 임시 기준. 권장: ${POLICY.strong_rule})`);
const PAY = { upfront: "계약금", royalty: "매출 로열티", profit: "이익 배당", equity: "지분" };

function render(c) { main.innerHTML = String(c); main.focus({ preventScroll: true }); }
function go(h) { if (location.hash === h) route(); else location.hash = h; }
const errorView = (e) => render(html`<div class="card empty"><p class="err">${e.message}</p></div>`);
const short = (h, n = 14) => (h ? h.slice(0, n) + "…" : "");

// 간단한(약한) 비밀번호 안내 띠: 정식 서비스 전에는 권유, 정식 서비스 중에는 필수
function pwBanner() {
  let bn = $("#pwbanner");
  if (!bn) { bn = document.createElement("div"); bn.id = "pwbanner"; bn.className = "wrap"; main.before(bn); }
  if (!ME || (!ME.pw_weak && ME.totp)) { bn.innerHTML = ""; return; }
  const tfa = ME.totp ? "" : MUST2FA
    ? String(html`<div class="note bad" role="alert"><b>정식 서비스가 시작되어 2단계 인증을 켜야 합니다.</b><p>휴대폰 인증 앱(Google Authenticator 등)을 등록하기 전에는 다른 기능을 쓸 수 없습니다. <a href="#/security">보안 설정</a></p></div>`)
    : String(html`<div class="note amber" role="status"><b>2단계 인증이 꺼져 있습니다.</b><p>비밀번호가 새어도 안전하도록 휴대폰 인증 앱으로 2단계 인증을 켜 두세요. 정식 서비스 때는 필수입니다. <a href="#/security">지금 켜기</a></p></div>`);
  if (!ME.pw_weak) { bn.innerHTML = tfa; return; }
  bn.innerHTML = tfa + (MUST
    ? String(html`<div class="note bad" role="alert"><b>정식 서비스가 시작되어 비밀번호를 바꿔야 합니다.</b><p>지금 비밀번호는 보안 기준에 못 미칩니다. 새 비밀번호(${POLICY.strong_rule})로 바꾸기 전에는 다른 기능을 쓸 수 없습니다.</p></div>`)
    : String(html`<div class="note amber" role="status"><b>임시(간단한) 비밀번호를 쓰고 있습니다.</b><p>정식 서비스 전까지는 괜찮지만, 정식 서비스를 시작하면 강한 비밀번호(${POLICY.strong_rule})로 바꿔야 합니다. 미리 바꿔 두면 편합니다. <a href="#/password">지금 바꾸기</a></p></div>`));
}

function nav() {
  pwBanner();
  const links = ME && !MUST && !MUST2FA ? [["#/", "대시보드"], ["#/users", "회원"], ["#/ideas", "아이디어"], ["#/access", "열람·NDA"], ["#/loans", "대출 심사"], ["#/contracts", "계약·정산"], ["#/ledger", "원장"], ["#/audit", "감사 로그"]] : [];
  const cur = (location.hash || "#/").split("?")[0];
  $("#nav").innerHTML = links.map(([h, t]) => `<a href="${h}" class="${cur === h || (h !== "#/" && cur.startsWith(h)) ? "on" : ""}">${esc(t)}</a>`).join("");
  $("#who").innerHTML = ME ? String(html`<span class="nm">${ME.name} (${ME.username})</span><a class="linkbtn" href="#/security">보안 설정</a><button class="linkbtn" id="lo">로그아웃</button>`) : "";
  const lo = $("#lo");
  if (lo) lo.onclick = async () => { await api("POST", "/api/logout"); ME = null; MUST = MUST2FA = false; IB.setCsrf(null); route(); };
}

async function viewLogin() {
  let st = {};
  try { st = await api("GET", "/api/setup"); if (st.policy) POLICY = st.policy; } catch (_) {}
  if (st.needed) return viewSetup();
  render(html`<div class="auth card stack"><div><h1>관리자 로그인</h1><p class="lead">운영자 전용입니다. 모든 행동은 감사 로그에 남습니다.</p></div>
    <form class="form" id="f">
      <div class="field"><label for="u">관리자 아이디</label><input id="u" name="username" type="text" autocomplete="username" required></div>
      <div class="field"><label for="p">비밀번호</label><input id="p" name="password" type="password" autocomplete="current-password" required></div>
      <div class="field" id="codef" hidden><label for="code">인증 코드 (6자리)</label><input id="code" name="code" type="text" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9 ]{6,7}" maxlength="7"><span class="hint">휴대폰 인증 앱에 보이는 지금 코드를 넣으세요.</span></div>
      <p class="err" id="msg" hidden></p><button class="btn primary">로그인</button>
    </form>
    <p class="small muted">${st.recovery ? raw('<a href="#" id="forgot">비밀번호를 잊었나요?</a>') : "비밀번호를 잊었으면 다른 관리자나 운영자에게 재설정을 요청하세요."}</p></div>`);
  const fg = $("#forgot");
  if (fg) fg.onclick = (e) => { e.preventDefault(); viewRecover(); };
  $("#f").onsubmit = async (ev) => {
    ev.preventDefault();
    try {
      const r = await busy(ev.submitter, () => api("POST", "/api/login", IB.formData(ev.target)));
      if (r.need_code) {  // 비밀번호는 맞음 → 2단계 인증 코드
        $("#codef").hidden = false; $("#code").required = true; $("#code").focus();
        $("#msg").hidden = true; $("#u").readOnly = $("#p").readOnly = true;
        return;
      }
      setMe(r); route();
    }
    catch (e) { $("#msg").hidden = false; $("#msg").textContent = e.message; }
  };
}

// ── 첫 관리자 만들기 (관리자가 아직 없고 운영자가 설정 토큰을 켜 둔 경우만) ──
function viewSetup() {
  render(html`<div class="auth card stack"><div><h1>첫 관리자 만들기</h1><p class="lead">관리자 계정이 아직 없습니다. Vercel 환경 변수 <b>ADMIN_SETUP_TOKEN</b> 에 넣은 값을 적고 첫 관리자 계정을 만드세요. 한 명이 만들어지면 이 화면은 다시 열리지 않습니다.</p></div>
    <form class="form" id="sf">
      <div class="field"><label for="st">설정 토큰</label><input id="st" name="token" type="password" autocomplete="off" required></div>
      <div class="field"><label for="su">관리자 아이디</label><input id="su" name="username" type="text" autocomplete="username" pattern="[a-z][a-z0-9_]{1,31}" required><span class="hint">영문 소문자로 시작, 2~32자 (예: ceo)</span></div>
      <div class="field"><label for="sn">이름</label><input id="sn" name="name" type="text" required></div>
      <div class="field"><label for="sp">비밀번호</label><input id="sp" name="password" type="password" autocomplete="new-password" minlength="${POLICY.min_len}" required><span class="hint">${pwHint()}</span></div>
      <div class="field"><label for="sp2">비밀번호 확인</label><input id="sp2" type="password" autocomplete="new-password" minlength="${POLICY.min_len}" required></div>
      <p class="err" id="msg" hidden></p><button class="btn primary">관리자 만들기</button>
    </form></div>`);
  $("#sf").onsubmit = async (ev) => {
    ev.preventDefault();
    const msg = $("#msg");
    if ($("#sp").value !== $("#sp2").value) { msg.hidden = false; msg.textContent = "두 비밀번호가 다릅니다."; return; }
    try {
      await busy(ev.submitter, () => api("POST", "/api/setup", IB.formData(ev.target)));
      toast("관리자 계정을 만들었습니다. 로그인해 주세요.");
      viewLogin();
    } catch (e) { msg.hidden = false; msg.textContent = e.message; }
  };
}

// ── 비밀번호를 잊었을 때: 설정 토큰(ADMIN_SETUP_TOKEN)으로 재설정 ──
function viewRecover() {
  render(html`<div class="auth card stack"><div><h1>관리자 비밀번호 재설정</h1><p class="lead">Vercel 환경 변수 <b>ADMIN_SETUP_TOKEN</b> 값을 아는 운영자만 쓸 수 있습니다. 재설정하면 그 계정은 모든 기기에서 로그아웃되고, <b>2단계 인증도 꺼집니다</b>(휴대폰을 잃어버린 경우). 감사 로그에 남습니다.</p></div>
    <form class="form" id="rf">
      <div class="field"><label for="rt">설정 토큰</label><input id="rt" name="token" type="password" autocomplete="off" required></div>
      <div class="field"><label for="ru">관리자 아이디</label><input id="ru" name="username" type="text" autocomplete="username" required></div>
      <div class="field"><label for="rp">새 비밀번호</label><input id="rp" name="password" type="password" autocomplete="new-password" minlength="${POLICY.min_len}" required><span class="hint">${pwHint()}</span></div>
      <div class="field"><label for="rp2">새 비밀번호 확인</label><input id="rp2" type="password" autocomplete="new-password" minlength="${POLICY.min_len}" required></div>
      <p class="err" id="msg" hidden></p>
      <div class="btns"><button class="btn primary">비밀번호 재설정</button><a class="btn" href="#" id="back">로그인으로</a></div>
    </form></div>`);
  $("#back").onclick = (e) => { e.preventDefault(); viewLogin(); };
  $("#rf").onsubmit = async (ev) => {
    ev.preventDefault();
    const msg = $("#msg");
    if ($("#rp").value !== $("#rp2").value) { msg.hidden = false; msg.textContent = "두 비밀번호가 다릅니다."; return; }
    try {
      await busy(ev.submitter, () => api("POST", "/api/recover", IB.formData(ev.target)));
      toast("비밀번호를 바꿨습니다. 새 비밀번호로 로그인해 주세요.");
      viewLogin();
    } catch (e) { msg.hidden = false; msg.textContent = e.message; }
  };
}

// ── 보안 설정: 비밀번호 + 2단계 인증 ──
async function viewSecurity() {
  const on = ME.totp;
  render(html`<div class="auth card stack"><div><h1>보안 설정</h1><p class="lead">${ME.name} (${ME.username})</p></div>
    <section class="stack"><h2>비밀번호</h2><p class="small muted">${ME.pw_weak ? "임시(간단한) 비밀번호를 쓰고 있습니다." : "강한 비밀번호를 쓰고 있습니다."}</p>
      <p><a class="btn" href="#/password">비밀번호 변경</a></p></section>
    <section class="stack"><h2>2단계 인증 ${on ? raw('<span class="badge stamp">켜짐</span>') : raw('<span class="badge wait">꺼짐</span>')}</h2>
      <p class="small muted">로그인할 때 비밀번호와 함께 휴대폰 인증 앱(Google Authenticator, Microsoft Authenticator 등)의 6자리 코드를 넣습니다. 휴대폰을 잃어버리면 [비밀번호를 잊었나요?] 의 설정 토큰 재설정으로 2단계 인증도 초기화됩니다.</p>
      <div id="tfa"></div></section></div>`);
  const box = $("#tfa");
  if (on) {
    if (POLICY.require_2fa) { box.innerHTML = '<p class="small muted">정식 서비스 중에는 2단계 인증을 끌 수 없습니다.</p>'; return; }
    box.innerHTML = String(html`<form class="form" id="off"><div class="field"><label for="op">현재 비밀번호</label><input id="op" name="password" type="password" autocomplete="current-password" required></div>
      <div class="field"><label for="oc">인증 코드</label><input id="oc" name="code" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="7" required></div>
      <p class="err" id="omsg" hidden></p><button class="btn">2단계 인증 끄기</button></form>`);
    $("#off").onsubmit = async (ev) => {
      ev.preventDefault();
      try { const r = await busy(ev.submitter, () => api("POST", "/api/2fa/disable", IB.formData(ev.target))); setMe({ ...r, policy: POLICY }); toast("2단계 인증을 껐습니다."); viewSecurity(); nav(); }
      catch (e) { $("#omsg").hidden = false; $("#omsg").textContent = e.message; }
    };
    return;
  }
  box.innerHTML = '<button class="btn primary" id="start">2단계 인증 켜기</button>';
  $("#start").onclick = (e) => busy(e.currentTarget, async () => {
    const r = await api("POST", "/api/2fa/begin");
    const key = r.secret.match(/.{1,4}/g).join(" ");
    box.innerHTML = String(html`<ol class="small stack">
        <li>휴대폰에 인증 앱(Google Authenticator 또는 Microsoft Authenticator)을 설치합니다.</li>
        <li>앱에서 <b>+ → 설정 키 입력</b>(Enter a setup key)을 고르고 아래 값을 넣습니다. 휴대폰으로 이 화면을 보고 있다면 <a href="${r.uri}">여기를 누르면</a> 앱에 바로 추가됩니다.
          <div class="note"><p>계정 이름: <b>IdeaBank Admin (${r.account})</b></p><p>키: <b class="mono">${key}</b></p><p>종류: 시간 기준(TOTP)</p></div></li>
        <li>앱에 생긴 6자리 코드를 넣고 [켜기] 를 누릅니다.</li></ol>
      <form class="form" id="on"><div class="field"><label for="ec">인증 코드 (6자리)</label><input id="ec" name="code" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="7" required></div>
        <p class="err" id="emsg" hidden></p><button class="btn primary">켜기</button></form>`);
    $("#on").onsubmit = async (ev) => {
      ev.preventDefault();
      try {
        const r2 = await busy(ev.submitter, () => api("POST", "/api/2fa/enable", IB.formData(ev.target)));
        setMe({ ...r2, policy: r2.policy || POLICY });
        toast("2단계 인증을 켰습니다. 다음 로그인부터 코드를 물어봅니다.");
        if (MUST || MUST2FA) route(); else { viewSecurity(); nav(); }
      } catch (e2) { $("#emsg").hidden = false; $("#emsg").textContent = e2.message; }
    };
  });
}

// ── 내 비밀번호 변경 ──
function viewPassword() {
  render(html`<div class="auth card stack"><div><h1>비밀번호 변경</h1><p class="lead">${ME.name} (${ME.username}) 계정의 비밀번호를 바꿉니다. 바꾸면 다른 기기의 로그인은 끊기고, 감사 로그에 남습니다.</p>
    ${POLICY.launched ? "" : html`<p class="small muted">정식 서비스 전에는 간단한 비밀번호도 쓸 수 있지만, 정식 서비스용으로는 <b>${POLICY.strong_rule}</b> 을 권합니다.</p>`}</div>
    <form class="form" id="pf">
      <input type="text" name="username" autocomplete="username" value="${ME.username}" hidden>
      <div class="field"><label for="cp">현재 비밀번호</label><input id="cp" name="current_password" type="password" autocomplete="current-password" required></div>
      <div class="field"><label for="np">새 비밀번호</label><input id="np" name="new_password" type="password" autocomplete="new-password" minlength="${POLICY.min_len}" required><span class="hint">${pwHint()}</span></div>
      <div class="field"><label for="np2">새 비밀번호 확인</label><input id="np2" type="password" autocomplete="new-password" minlength="${POLICY.min_len}" required></div>
      <p class="err" id="msg" hidden></p>
      <div class="btns"><button class="btn primary">비밀번호 변경</button>${MUST ? "" : raw('<a class="btn" href="#/">취소</a>')}</div>
    </form></div>`);
  $("#pf").onsubmit = async (ev) => {
    ev.preventDefault();
    const msg = $("#msg");
    msg.hidden = true;
    if ($("#np").value !== $("#np2").value) { msg.hidden = false; msg.textContent = "새 비밀번호와 확인이 다릅니다."; return; }
    try {
      const r = await busy(ev.submitter, () => api("POST", "/api/password", { current_password: $("#cp").value, new_password: $("#np").value }));
      if (r.admin) ME = r.admin;
      MUST = false;
      toast(ME.pw_weak ? "비밀번호를 바꿨습니다. (아직 임시 기준 비밀번호입니다)" : "강한 비밀번호로 바꿨습니다."); go("#/");
    } catch (e) { msg.hidden = false; msg.textContent = e.message; }
  };
}

// ── 대시보드 ──
async function viewDash() {
  let d;
  try { d = await api("GET", "/api/dashboard"); } catch (e) { return errorView(e); }
  render(html`<div class="head-row"><div><h1>대시보드</h1><p class="lead">원장 기록 ${d.ledger.count}건 · 마지막 기록 ${kst(d.ledger.updated_at)}</p></div>
    <div class="btns"><button class="btn primary" id="vf">원장 무결성 검사</button><button class="btn amber" id="st" ${d.ledger.pending ? "" : raw("disabled")}>공인 시각 재요청 (${d.ledger.pending})</button></div></div>
  <div id="vr"></div>
  <div class="stats">
    <a class="stat" href="#/users"><b>${d.users.creator}</b><span>창안자</span></a>
    <a class="stat" href="#/users"><b>${d.users.business}</b><span>사업자</span></a>
    <a class="stat" href="#/ideas"><b>${d.ideas.total}</b><span>아이디어 (공개 ${d.ideas.listed} · 숨김 ${d.ideas.hidden})</span></a>
    <a class="stat" href="#/access"><b>${d.ndas}</b><span>NDA 서명</span></a>
    <a class="stat" href="#/access"><b>${d.views}</b><span>열람 기록</span></a>
    <a class="stat ${d.loans.submitted ? "warn" : ""}" href="#/loans"><b>${d.loans.submitted}</b><span>심사 대기 대출 신청</span></a>
    <a class="stat" href="#/contracts"><b>${d.contracts}</b><span>계약 기록 · 정산 ${won(d.settled_total)}</span></a>
    <div class="stat ${d.ledger.pending ? "warn" : ""}"><b>${d.ledger.pending}</b><span>공인 시각 대기</span></div>
  </div>
  <div class="cols">
    <section class="card stack"><h2>공인 시각 대기 기록</h2>${d.pending_events.length ? html`<ul class="events">${d.pending_events.map((e) => html`<li><b>#${e.seq} ${e.kind_label}</b><span class="small muted">${kst(e.created_at)}${e.tsa_error ? ` · 마지막 오류: ${e.tsa_error.slice(0, 80)}` : ""}</span></li>`)}</ul>` : html`<p class="small muted">모든 기록이 공인 시각을 받았습니다.</p>`}</section>
    <section class="card stack"><h2>원장 헤드</h2><p class="mono small">${d.ledger.head}</p><p class="small muted">정기적으로 외부에 공개하면 운영자도 과거 기록을 바꿀 수 없음을 보여 줄 수 있습니다.</p></section>
    <section class="card stack"><h2>최근 관리자 행동</h2><ul class="events">${d.recent_audit.map((a) => html`<li><b>${a.action}</b><span class="small muted">${a.admin_name} · ${kst(a.at)} ${a.target ? `· ${a.target}` : ""}</span></li>`)}</ul><a href="#/audit" class="small">감사 로그 전체 →</a></section>
  </div>`);
  $("#vf").onclick = (e) => busy(e.currentTarget, async () => {
    const r = await api("POST", "/api/ledger/verify");
    $("#vr").innerHTML = String(html`<div class="note ${r.ok && r.audit.ok ? "ok" : "bad"}"><b>${r.ok ? "원장 이상 없음" : "원장에서 문제를 찾았습니다"}</b>
      <p>기록 ${r.count}건 검사 · 공인 시각 대기 ${r.pending}건 · 감사 로그 체인 ${r.audit.ok ? "정상" : "손상"} · ${kstFull(r.checked_at)}</p>
      ${r.broken.map((b) => html`<p>#${b.seq}: ${b.reason}</p>`)}</div><br>`);
  });
  $("#st").onclick = (e) => busy(e.currentTarget, async () => { const r = await api("POST", "/api/ledger/stamp"); toast(`공인 시각 ${r.stamped}건 받음, 실패 ${r.failed}건`); route(); });
}

// ── 회원 ──
async function viewUsers() {
  let r;
  try { r = await api("GET", "/api/users"); } catch (e) { return errorView(e); }
  render(html`<h1>회원 관리</h1><p class="lead">창안자·사업자 계정. 정지하면 바로 로그아웃되고 로그인할 수 없습니다. 사유는 감사 로그에 남습니다.</p>
  <div class="tbl"><table class="t stack-sm"><thead><tr><th>#</th><th>이름</th><th>유형</th><th>이메일</th><th>활동</th><th>가입</th><th>상태</th></tr></thead><tbody>
  ${r.users.map((u) => html`<tr><td data-l="#">${u.id}</td><td data-l="이름"><b>${u.name}</b>${u.org ? html`<br><span class="small muted">${u.org}</span>` : ""}</td>
    <td data-l="유형">${u.role === "creator" ? "창안자" : "사업자"}</td><td data-l="이메일">${u.email}</td>
    <td data-l="활동" class="small">${u.role === "creator" ? `아이디어 ${u.ideas}` : `NDA ${u.ndas} · 신청 ${u.loans}`}</td><td data-l="가입">${kst(u.created_at, false)}</td>
    <td data-l="상태"><span class="badge ${u.status === "active" ? "ok" : "bad"}">${u.status === "active" ? "정상" : "정지"}</span>
      <button class="btn sm st" data-id="${u.id}" data-s="${u.status === "active" ? "suspended" : "active"}">${u.status === "active" ? "정지" : "재개"}</button></td></tr>`)}
  </tbody></table></div>`);
  $$(".st").forEach((b) => (b.onclick = async () => {
    const reason = prompt(`${b.dataset.s === "suspended" ? "이용 정지" : "이용 재개"} 사유를 적어 주세요 (감사 로그에 남습니다)`);
    if (!reason) return;
    await busy(b, () => api("POST", `/api/users/${b.dataset.id}/status`, { status: b.dataset.s, reason }));
    toast("변경했습니다."); route();
  }));
}

// ── 아이디어 (읽기 전용) ──
async function viewIdeas() {
  let r;
  try { r = await api("GET", "/api/ideas"); } catch (e) { return errorView(e); }
  render(html`<h1>아이디어 관리</h1><p class="lead">읽기 전용입니다. 아이디어는 고치거나 지울 수 없습니다. 공개 목록에서 숨기는 것만 가능하며 사유가 기록됩니다.
  관리자 화면에는 본문이 나오지 않고, 비공개 아이디어는 제목도 가립니다.</p>
  <div class="list">${r.ideas.map((d) => html`<a class="item" href="#/ideas/${d.seq}"><span class="no">${d.idea_no} · v${d.version} · ${d.owner}</span><h3>${d.title}</h3>
    ${d.summary ? html`<span class="sum">${d.summary}</span>` : ""}<span class="meta">열람 ${d.views} · NDA ${d.ndas} · 대출 신청 ${d.loans}</span>
    <span class="side">${d.tsa_time ? html`<span class="badge stamp">공인 시각 ${kst(d.tsa_time, false)}</span>` : html`<span class="badge wait">공인 시각 대기</span>`}<span class="badge">${d.disclosure_label}</span>${d.hidden ? html`<span class="badge bad">숨김</span>` : ""}</span></a>`)}</div>`);
}

async function viewIdea(seq) {
  let d;
  try { d = await api("GET", `/api/ideas/${seq}`); } catch (e) { return errorView(e); }
  render(html`<p><a href="#/ideas" class="small">← 아이디어 목록</a></p><div class="grid2"><div class="stack">
    <section class="card stack"><div><span class="mono muted">${d.idea_no} · v${d.version}</span><h1>${d.title}</h1><div class="btns"><span class="badge">${d.disclosure_label}</span>${d.hidden ? html`<span class="badge bad">공개 목록에서 숨김</span>` : ""}</div></div>
      ${d.summary ? html`<div class="note"><b>공개 요약</b><p class="body-text">${d.summary}</p></div>` : ""}
      ${d.hidden ? html`<div class="note bad"><b>숨김 사유</b><p>${d.hidden_reason}</p></div>` : ""}
      <div class="note small">본문은 관리자에게 표시하지 않습니다. 원문은 원장의 고유 지문으로 보호되며 수정·삭제 기능은 없습니다.</div></section>
    <section class="card stack"><h2>${d.hidden ? "공개 목록에 다시 표시" : "공개 목록에서 숨기기"}</h2>
      <form class="form" id="hf"><div class="field"><label for="rs">사유<span class="req">*</span></label><textarea id="rs" name="reason" class="short" required placeholder="예) 타인의 개인정보가 요약에 포함됨 — 창안자에게 수정 요청"></textarea></div>
      <div><button class="btn ${d.hidden ? "primary" : "danger"}">${d.hidden ? "다시 표시" : "숨기기"}</button></div></form></section>
    <section class="card"><h2>원장 기록</h2><ul class="events">${d.history.map((e) => html`<li><b>#${e.seq} ${e.kind_label}</b><span class="small muted">${kst(e.created_at)} · ${e.tsa_time ? `공인 시각 ${kst(e.tsa_time)}` : "공인 시각 대기"}</span><span class="mono muted">${e.content_hash}</span></li>`)}</ul></section>
  </div><aside class="card"><dl class="facts">
    <div><dt>창안자</dt><dd>${d.owner}<br><span class="small muted">${d.owner_email}</span></dd></div>
    <div><dt>등록 시각</dt><dd>${kstFull(d.created_at)}</dd></div>
    <div class="hl"><dt>공인 시각</dt><dd>${d.tsa_time ? kstFull(d.tsa_time) : "대기"}</dd></div>
    <div><dt>고유 지문</dt><dd class="mono">${d.content_hash}</dd></div>
    <div><dt>활동</dt><dd>열람 ${d.views} · NDA ${d.ndas} · 대출 신청 ${d.loans}</dd></div></dl></aside></div>`);
  $("#hf").onsubmit = async (ev) => {
    ev.preventDefault();
    await busy(ev.submitter, () => api("POST", `/api/ideas/${d.seq}/hidden`, { hidden: !d.hidden, reason: new FormData(ev.target).get("reason") }));
    toast(d.hidden ? "다시 표시했습니다." : "공개 목록에서 숨겼습니다."); route();
  };
}

// ── 열람·NDA ──
async function viewAccess() {
  let r;
  try { r = await api("GET", "/api/access"); } catch (e) { return errorView(e); }
  render(html`<h1>열람·NDA 기록</h1><p class="lead">모든 열람과 NDA 서명은 원장 이벤트이며 공인 시각을 받습니다.</p>
  <h2>NDA 서명 (${r.ndas.length})</h2>
  <div class="tbl"><table class="t stack-sm"><thead><tr><th>아이디어</th><th>서명자</th><th>서명 시각</th><th>공인 시각</th><th>문서 지문</th></tr></thead><tbody>
  ${r.ndas.map((n) => html`<tr><td data-l="아이디어">${n.title}<br><span class="mono muted">${n.idea_no}</span></td><td data-l="서명자"><b>${n.signer_name}</b><br><span class="small muted">${n.org}</span></td><td data-l="서명 시각">${kst(n.signed_at)}</td><td data-l="공인 시각">${n.tsa_time ? kst(n.tsa_time) : "대기"}</td><td data-l="문서 지문"><span class="mono muted" title="${n.doc_hash}">${short(n.doc_hash, 20)}</span></td></tr>`)}
  </tbody></table></div>
  <h2 class="mt">열람 (${r.views.length})</h2>
  <div class="tbl"><table class="t stack-sm"><thead><tr><th>아이디어</th><th>열람자</th><th>범위</th><th>열람 시각</th><th>공인 시각</th></tr></thead><tbody>
  ${r.views.map((v) => html`<tr><td data-l="아이디어">${v.title}<br><span class="mono muted">${v.idea_no}</span></td><td data-l="열람자"><b>${v.viewer}</b><br><span class="small muted">${v.org}</span></td><td data-l="범위">${v.level_label}${v.detail ? ` · ${v.detail}` : ""}</td><td data-l="열람 시각">${kst(v.at)}</td><td data-l="공인 시각">${v.tsa_time ? kst(v.tsa_time) : "대기"}</td></tr>`)}
  </tbody></table></div>`);
}

// ── 대출 심사 ──
function terms(t) {
  const pay = Object.entries(t.pay).map(([k, v]) => k === "upfront" ? `계약금 ${won(v.amount)}` : k === "equity" ? `지분 ${v.pct}%` : k === "royalty" ? `로열티 ${v.pct}%${v.annual_cap ? ` (연 상한 ${won(v.annual_cap)})` : ""} · ${v.years}년` : `이익 배당 ${v.pct}%`);
  return html`<dl class="facts"><div><dt>사용 분야</dt><dd>${t.field}</dd></div><div><dt>독점·지역·기간</dt><dd>${t.exclusive ? "독점" : "비독점"} · ${t.territory} · ${t.term_years}년</dd></div>
    <div><dt>대가</dt><dd>${pay.join(" / ")}</dd></div><div><dt>MVP 출시 목표</dt><dd>${t.mvp_months}개월</dd></div>${t.message ? html`<div><dt>메시지</dt><dd class="body-text">${t.message}</dd></div>` : ""}</dl>`;
}
async function viewLoans() {
  let r;
  try { r = await api("GET", "/api/loans"); } catch (e) { return errorView(e); }
  render(html`<h1>대출 신청 심사</h1><p class="lead">LA-2026-001 표준 조건 기준. 승인하면 계약·정산 화면에서 약정서를 기록할 수 있습니다.</p>
  <div class="stack">${r.loans.length ? r.loans.map((l) => html`<div class="card stack">
    <div class="head-row"><div><span class="mono muted">${l.loan_no} · ${l.idea_no}</span><h3>${l.title}</h3><span class="small muted">창안자 ${l.creator} ← 신청 ${l.org} ${l.business} · ${kst(l.created_at)}${l.tsa_time ? ` · 공인 시각 ${kst(l.tsa_time)}` : ""}</span></div>
      <div class="btns"><span class="badge ${l.status === "approved" ? "ok" : l.status === "rejected" ? "bad" : "wait"}">${l.status_label}</span><span class="badge ${l.creator_response === "accepted" ? "ok" : l.creator_response === "declined" ? "bad" : ""}">창안자 ${l.creator_response_label}</span></div></div>
    ${terms(l.terms)}
    ${l.creator_note ? html`<div class="note"><b>창안자 의견</b><p>${l.creator_note}</p></div>` : ""}
    ${l.status === "submitted" ? html`${l.creator_response !== "accepted" ? html`<div class="note amber small">창안자가 아직 조건에 동의하지 않았습니다. 승인 전에 창안자 의사를 확인하세요.</div>` : ""}
      <form class="form rv" data-id="${l.id}"><div class="field"><label>심사 의견 (반려 시 필수)</label><textarea name="note" class="short"></textarea></div>
      <div class="btns"><button class="btn primary" value="approved">승인</button><button class="btn danger" value="rejected">반려</button></div></form>`
      : html`<div class="note ${l.status === "approved" ? "ok" : "bad"}"><b>${l.status_label}</b> · ${kst(l.reviewed_at)}${l.review_note ? html`<p>${l.review_note}</p>` : ""}</div>`}
  </div>`) : html`<div class="card empty">대출 신청이 없습니다.</div>`}</div>`);
  $$("form.rv").forEach((f) => (f.onsubmit = async (ev) => {
    ev.preventDefault();
    const decision = ev.submitter.value;
    await busy(ev.submitter, () => api("POST", `/api/loans/${f.dataset.id}/review`, { decision, note: new FormData(f).get("note") }));
    toast(decision === "approved" ? "승인했습니다." : "반려했습니다."); route();
  }));
}

// ── 계약·정산 ──
async function viewContracts() {
  let r;
  try { r = await api("GET", "/api/contracts"); } catch (e) { return errorView(e); }
  render(html`<h1>계약·정산 기록</h1><p class="lead">v3 단계: 서명된 약정서와 정산 내역을 수작업으로 기록합니다. 대금·지분은 제휴 예탁기관이 보관하며 이 시스템은 기록만 합니다. (조회도 감사 로그에 남습니다)</p>
  ${r.approved_loans.length ? html`<section class="card stack"><h2>계약 기록 등록</h2>
    <form class="form" id="cf">
      <div class="row2"><div class="field"><label for="ln">승인된 대출 신청</label><select id="ln" name="loan_id">${r.approved_loans.map((l) => html`<option value="${l.id}">${l.loan_no} · ${l.title} · ${l.org}</option>`)}</select></div>
      <div class="field"><label for="so">약정일</label><input id="so" name="signed_on" type="date" required></div></div>
      <div class="field"><label for="dc">서명된 약정서 파일 (선택)</label><input id="dc" type="file"><span class="hint">파일의 고유 지문이 원장에 기록되고 공인 시각을 받습니다.</span></div>
      <div class="field"><label for="nt">메모</label><textarea id="nt" name="note" class="short" placeholder="예) 이사회 승인 2026-12-01, 변호사 검토 완료"></textarea></div>
      <div><button class="btn primary">계약 기록 등록</button></div>
    </form></section><br>` : ""}
  <div class="stack">${r.contracts.length ? r.contracts.map((c) => html`<section class="card stack">
    <div class="head-row"><div><span class="mono muted">${c.contract_no} · ${c.loan.loan_no}</span><h3>${c.loan.title}</h3><span class="small muted">창안자 ${c.loan.creator} · 사업자 ${c.loan.org} · 약정일 ${c.signed_on}${c.tsa_time ? ` · 공인 시각 ${kst(c.tsa_time)}` : ""}</span></div><span class="badge ok">정산 합계 ${won(c.settled_total)}</span></div>
    ${c.doc_hash ? html`<p class="small">약정서 <b>${c.doc_name}</b> <span class="mono muted">${c.doc_hash}</span></p>` : ""}
    ${terms(c.terms)}
    ${c.settlements.length ? html`<div class="tbl"><table class="t stack-sm"><thead><tr><th>기간</th><th>종류</th><th class="right">금액</th><th>지급일</th><th>메모</th><th>공인 시각</th></tr></thead><tbody>
      ${c.settlements.map((s) => html`<tr><td data-l="기간">${s.period}</td><td data-l="종류">${s.kind_label}</td><td data-l="금액" class="right">${won(s.amount)}</td><td data-l="지급일">${s.paid_on || "-"}</td><td data-l="메모">${s.note}</td><td data-l="공인 시각">${s.tsa_time ? kst(s.tsa_time) : "대기"}</td></tr>`)}</tbody></table></div>` : ""}
    <form class="inline-form sf" data-id="${c.id}">
      <div class="field"><label>기간</label><input name="period" type="text" placeholder="2027-1Q" required></div>
      <div class="field"><label>종류</label><select name="kind">${Object.entries(PAY).map(([k, v]) => html`<option value="${k}">${v}</option>`)}</select></div>
      <div class="field"><label>금액(원)</label><input name="amount" type="number" min="0" required></div>
      <div class="field"><label>지급일</label><input name="paid_on" type="date"></div>
      <div class="field"><label>메모</label><input name="note" type="text"></div>
      <button class="btn">정산 기록 추가</button></form>
  </section>`) : html`<div class="card empty">아직 계약 기록이 없습니다.</div>`}</div>`);
  const cf = $("#cf");
  if (cf) cf.onsubmit = async (ev) => {
    ev.preventDefault();
    const fd = Object.fromEntries(new FormData(cf));
    const file = $("#dc").files[0];
    if (file) { fd.doc_b64 = IB.b64(await file.arrayBuffer()); fd.doc_name = file.name; }
    await busy(ev.submitter, () => api("POST", "/api/contracts", fd));
    toast("계약 기록을 등록했습니다."); route();
  };
  $$("form.sf").forEach((f) => (f.onsubmit = async (ev) => {
    ev.preventDefault();
    await busy(ev.submitter, () => api("POST", `/api/contracts/${f.dataset.id}/settlements`, Object.fromEntries(new FormData(f))));
    toast("정산 기록을 추가했습니다."); route();
  }));
}

// ── 원장 ──
async function viewLedger(q) {
  const kind = q.get("kind") || "";
  let r;
  try { r = await api("GET", "/api/events?kind=" + encodeURIComponent(kind)); } catch (e) { return errorView(e); }
  render(html`<h1>원장</h1><p class="lead">하나의 해시 체인 이벤트 원장. 각 기록은 앞 기록의 고리값을 물고 있고, 고유 지문에 공인 시각을 받습니다.</p>
  <div class="chips"><button class="chip ${kind ? "" : "on"}" data-k="">전체</button>${Object.entries(r.kinds).map(([k, v]) => html`<button class="chip ${k === kind ? "on" : ""}" data-k="${k}">${v}</button>`)}</div>
  <div class="tbl"><table class="t stack-sm"><thead><tr><th>#</th><th>종류</th><th>행위자</th><th>기록 시각</th><th>공인 시각</th><th>고유 지문 / 고리값</th></tr></thead><tbody>
  ${r.events.map((e) => html`<tr><td data-l="#">${e.seq}</td><td data-l="종류">${e.kind_label}</td><td data-l="행위자" class="mono">${e.actor}</td><td data-l="기록 시각">${kst(e.created_at)}</td>
    <td data-l="공인 시각">${e.tsa_time ? kst(e.tsa_time) : html`<span class="badge wait">대기</span>`}</td><td data-l="지문" class="mono muted">${short(e.content_hash, 20)}<br>${short(e.entry_hash, 20)}</td></tr>`)}
  </tbody></table></div>`);
  $$(".chip").forEach((c) => (c.onclick = () => go("#/ledger?kind=" + encodeURIComponent(c.dataset.k))));
}

// ── 감사 로그 ──
async function viewAudit() {
  let r;
  try { r = await api("GET", "/api/audit"); } catch (e) { return errorView(e); }
  render(html`<h1>감사 로그</h1><p class="lead">관리자의 모든 행동(로그인, 숨김, 회원 정지, 대출 심사, 계약·정산 기록, 원장 검사 등). 감사 로그도 자체 해시 체인으로 묶여 있습니다.</p>
  <div class="note ${r.integrity.ok ? "ok" : "bad"} small"><b>감사 로그 체인 ${r.integrity.ok ? "정상" : "손상됨: " + r.integrity.broken.join(", ")}</b></div><br>
  <div class="tbl"><table class="t stack-sm"><thead><tr><th>#</th><th>시각</th><th>관리자</th><th>행동</th><th>대상</th><th>내용</th><th>IP</th></tr></thead><tbody>
  ${r.audit.map((a) => html`<tr><td data-l="#">${a.id}</td><td data-l="시각">${kst(a.at)}</td><td data-l="관리자">${a.admin_name}</td><td data-l="행동"><b>${a.action}</b></td><td data-l="대상" class="mono">${a.target}</td>
    <td data-l="내용" class="small">${Object.entries(a.detail).filter(([, v]) => v !== "" && v !== null).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ")}</td><td data-l="IP" class="mono muted">${a.ip}</td></tr>`)}
  </tbody></table></div>`);
}

const ROUTES = [[/^#?\/?$/, viewDash], [/^#\/users$/, viewUsers], [/^#\/ideas$/, viewIdeas], [/^#\/ideas\/(\d+)$/, viewIdea],
  [/^#\/access$/, viewAccess], [/^#\/loans$/, viewLoans], [/^#\/contracts$/, viewContracts], [/^#\/ledger$/, viewLedger], [/^#\/audit$/, viewAudit], [/^#\/password$/, viewPassword], [/^#\/security$/, viewSecurity]];
async function route() {
  nav();
  if (!ME) return viewLogin();
  if (MUST) return viewPassword();
  if (MUST2FA) { nav(); return viewSecurity(); }
  const [path, qs] = (location.hash || "#/").split("?");
  const q = new URLSearchParams(qs || "");
  for (const [rx, fn] of ROUTES) {
    const m = rx.exec(path);
    if (m) {
      render('<div class="empty"><span class="spin"></span> 불러오는 중</div>');
      try { await fn(m[1] || q, q); } catch (e) { if (e.status === 401) { ME = null; route(); } }
      return;
    }
  }
  render('<div class="card empty">없는 화면입니다.</div>');
}
window.addEventListener("hashchange", route);
(async () => { try { setMe(await api("GET", "/api/me")); } catch (_) {} route(); })();
