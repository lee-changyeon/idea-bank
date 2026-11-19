# 아이디어뱅크 온라인 (web)

PRD v2(열람 통제) 방향의 온라인 버전입니다. v3 대출 화면 일부가 들어 있습니다. 앱은 두 개입니다.

| 앱 | 폴더 | 주소 | 실행 |
|----|------|------|------|
| 사용자 웹 (창안자·사업자) | `web/` | http://localhost:8090 | `run_web.bat` |
| 관리자 사이트 | `admin/` | http://localhost:8091 | `run_admin.bat` |

v1 로컬 앱(`server.py`, 8080)과는 별개로 동작하고, 데이터도 따로 둡니다(`web/data/`).

## 1. 설치·실행

- Python 3.11 이상(개발 환경 3.13)만 있으면 됩니다. 외부 패키지는 쓰지 않습니다.
- `run_web.bat` 과 `run_admin.bat` 을 각각 더블클릭합니다.
  - DB 가 비어 있으면 먼저 데모 데이터를 만듭니다(`web/seed.py`).
  - 그다음 브라우저가 열립니다. 브라우저를 열지 않으려면 `IB_NO_BROWSER=1` 을 설정하세요.
- 직접 실행할 때:
  ```bash
  python web/seed.py                  # 빈 DB 에 데모 데이터
  python web/seed.py --reset          # web/data 를 지우고 새로 만들기 (확인 질문)
  python web/server.py                # 사용자 웹 :8090
  python admin/server.py              # 관리자 :8091
  ```
- 데모 계정은 [`seed_accounts.example.json`](seed_accounts.example.json)에 있습니다. 모두 가짜 데이터입니다.
  - 창안자 2, 사업자 1, 관리자(+ 대표·AI 직원)
  - 예시 아이디어 4건: NDA 공개 2, 요약 공개 1, 비공개 1
- 설정을 바꾸려면 `web/config.json` 을 만드세요. 넣을 수 있는 값은 `host`, `web_port`, `admin_port`, `tsa_urls` 입니다.
  - TSA 목록은 기본으로 루트 `config.json` 에서 읽기만 합니다.

## 2. 구조

```
web/
  server.py          사용자 앱 라우트 (창안자 /api/my/*, 사업자 /api/market/*, 공개 /api/verify, /api/lookup)
  seed.py            데모 데이터
  ibweb/             두 앱이 함께 쓰는 백엔드
    db.py            SQLite 스키마 (WAL, 두 프로세스가 같은 파일을 씀)
    ledger.py        하나의 해시 체인 이벤트 원장 + 공인 시각 작업자 + 무결성 검사
    service.py       업무 로직 (아이디어, 공개 단계, 열람, NDA, 대출, 계약·정산, 감사 로그)
    security.py      scrypt 비밀번호, 세션, CSRF, 로그인 시도 제한
    httpkit.py       http.server 기반 라우터 (역할 검사, 보안 헤더, 정적 파일)
    proof.py         증명 파일(zip) 만들기·검증 — v1 형식 그대로
    nda.py           표준 NDA 약정문 (판 번호 + 고유 지문)
  static/            index.html, app.js, lib.js(공용), app.css(공용)
admin/
  server.py          관리자 라우트 (/api/dashboard, users, ideas, access, loans, contracts, events, audit)
  static/            index.html, admin.js
```

### 증명 로직 재사용
- 정규화 JSON, 고유 지문, 고리값 규칙은 `ideabank.canonical` 을 그대로 import 합니다.
- RFC 3161 공인 시각은 `ideabank.tsa` 를 그대로 import 합니다.
- 증명 파일 검증은 `ideabank.bundle.verify` 를, 안내문은 `bundle.GUIDE` 를 그대로 씁니다.
- 아이디어 원문은 v1 과 같은 `ideabank/1` 스키마입니다. 그래서 웹에서 받은 증명 파일은 v1 검증기로도 통과합니다.
- 코어에 바라는 변경은 [`NOTES_FOR_CORE.md`](NOTES_FOR_CORE.md)에 적었습니다.

### 이벤트 원장 (TRD §10)
- `events` 테이블 하나가 해시 체인입니다. 규칙은 v1 과 같습니다.
  - `content_hash = sha256(payload)`
  - `entry_hash = sha256(prev:seq:content_hash)`
- 기록하는 이벤트:
  - 아이디어 등록
  - 공개 단계 변경
  - 요약·전문·첨부 열람
  - NDA 서명
  - 대출 신청, 창안자 응답, 심사
  - 숨김, 해제
  - 계약, 정산
- 등록 이벤트의 payload 는 아이디어 정규화 JSON 자체입니다. 그래서 아이디어의 고유 지문이 곧 이벤트 지문입니다.
- NDA 이벤트의 payload 는 서명 문서(약정문 지문 + 아이디어 지문 + 서명자)입니다. 그래서 NDA 문서 해시가 곧 이벤트 지문입니다.
- 모든 이벤트는 고유 지문에 공인 시각(RFC 3161)을 받습니다.
  - 등록과 NDA 서명은 그 자리에서 바로 받습니다.
  - 나머지는 백그라운드 작업자가 받습니다. 실패하면 다시 시도하고, 관리자 대시보드에서 재요청할 수도 있습니다.
- 관리자 감사 로그(`audit`)는 따로 해시 체인으로 묶여 있습니다. 대시보드의 [원장 무결성 검사]가 두 체인을 모두 검사합니다.

### 보안
- 비밀번호는 `hashlib.scrypt`(N=2^14, r=8, p=1, 솔트 16바이트)로 저장합니다. 로그인 실패가 10분에 5번이면 잠깁니다.
- 세션은 `HttpOnly; SameSite=Strict` 쿠키로 둡니다. DB 에는 토큰의 SHA-256 만 저장합니다.
  - 사용자 쿠키는 `ib_sess`, 관리자 쿠키는 `ib_admin` 입니다.
  - 관리자 로그인은 `admins` 테이블을 쓰며, 사용자 로그인과 완전히 분리되어 있습니다.
- 로그인한 상태의 모든 POST 는 `X-CSRF-Token` 이 필요합니다.
  - 모든 POST 는 `Origin` 이 같아야 하고, `Content-Type: application/json` 만 받습니다.
- 모든 API 에서 역할(창안자 / 사업자 / 관리자)을 검사합니다.
- 사업자에게 본문과 첨부를 보내는 곳은 `market_full`, `market_file` 두 함수뿐입니다.
  - 둘 다 "NDA 후 공개" 단계이고 서명한 NDA 가 있을 때만 응답합니다.
  - 응답할 때마다 열람 이벤트를 남깁니다.
  - 목록과 요약 응답에는 본문이 아예 들어가지 않습니다.
- 관리자 화면에도 본문은 보이지 않습니다. 비공개 아이디어는 제목도 가립니다.
  - 아이디어 수정·삭제 API 는 없습니다. 관리자는 공개 목록에서 숨기는 것만 할 수 있고, 사유가 기록됩니다.
- 보안 헤더: CSP(`'self'` 만 허용, 인라인 스크립트·스타일 없음), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`.

### 온라인 배포 (Vercel + Supabase)
- 사용자 웹만 온라인에 올립니다. 관리자 사이트는 로컬 전용입니다.
- `DATABASE_URL` 이 있으면 Postgres(Supabase), `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` 가 있으면 첨부를 Supabase Storage 에 둡니다. 없으면 지금처럼 SQLite + `web/data/files` 입니다.
- 설계와 환경 변수: [`DEPLOY_SUPABASE.md`](DEPLOY_SUPABASE.md). Vercel 입구는 루트의 `api/index.py`, `vercel.json` 입니다.
- 운영 주소: https://idea-bank-web-omega.vercel.app (DB 비밀번호 바꾸는 순서는 `DEPLOY_SUPABASE.md` §10)
- 전체 흐름 점검: `python web/tools/smoke.py <주소>` (로컬 테스트는 `tests/test_web.py` 가 임시 DB 로 같은 흐름을 돌립니다).

## 3. 아직 모의(목업)인 것

| 항목 | 지금 | 실제 서비스 전에 할 일 |
|------|------|------------------------|
| 전자서명(NDA) | 클릭 서명: 가입 이름 입력 + 동의, 서명 문서 해시 + 공인 시각 | 본인 확인 전자서명(공동·간편 인증서 등), 약정문 법률 검토 |
| 예탁·에스크로 | 없음. 계약금·로열티·지분은 기록만 함 | 신탁사·에스크로 제휴, 지급 지시 연동 (PRD v4) |
| 계약 체결 | 관리자가 약정일·약정서 파일(해시)을 수작업으로 기록 | LA-2026-001 템플릿 자동 작성, 양측 전자서명 |
| 정산 | 관리자 수작업 입력 | 매출 자료 연동, 분기 자동 정산 |
| 진행 보고 (제7조) | 없음 | 사업자 분기 보고 화면 → 원장 이벤트 |
| 이메일 인증·알림 | 없음 (가입 즉시 사용) | 이메일 인증, 신청·서명·열람 알림 |
| HTTPS | 없음 (localhost 용). 쿠키에 `Secure` 없음 | TLS 종단 + `Secure` 쿠키, 서버를 127.0.0.1 밖으로 열 때 필수 |
| 본문 암호화 | 평문 SQLite | 저장 시 암호화(해시는 평문 기준 유지, TRD §9) |
| 원장 헤드 공개 | 검증 화면에 표시만 | 정기 외부 공개(F12), OpenTimestamps 이중 앵커 |
| 관리자 권한 | 관리자 1종 | 역할 분리(심사·정산·감사 열람), 2단계 인증 |

## 4. 관리자 계정 관리 (`manage_admins.py`)

관리자 사이트(http://localhost:8091) 로그인 계정을 기존 DB(`web/data/ideabank_web.db`)에 추가하거나 비밀번호를 바꿉니다. DB 를 지우거나 초기화하지 않으며, 모든 변경은 감사 로그에 `cli` 로 남습니다.

```bash
python web/manage_admins.py list                     # 관리자 목록
python web/manage_admins.py add <username> <name>    # 계정 추가 (비밀번호 입력)
python web/manage_admins.py passwd <username>        # 비밀번호 변경
```

- 비밀번호를 칠 때 글자가 화면에 보이지 않는 것이 정상입니다. 그대로 입력하고 Enter 를 누르세요. 터미널에서 입력이 아예 안 되면 `--visible` 을 붙이면 글자가 보이게 입력합니다.
- 비밀번호를 비워 두거나 `--generate` 를 붙이면 무작위 비밀번호를 만들어 화면에 한 번만 보여 줍니다.
- username 은 영문 소문자로 시작하는 2~32자(a-z, 0-9, _), 비밀번호는 8자 이상입니다.
- 기본 계정: `ceo`(이창연, 대표)와 AI 직원 `hana` `coda` `gard` `loy` `mio` `ben` `sori`. 대표는 처음에 `python web/manage_admins.py passwd ceo` 로 직접 비밀번호를 정하세요.
- `seed_accounts.example.json` 의 비밀번호는 새 데모 DB 용 가짜 값입니다. 운영 DB 에서는 쓰지 마세요.
- 한글이 깨지면 `PYTHONUTF8=1` 을 설정하고 실행하세요.
