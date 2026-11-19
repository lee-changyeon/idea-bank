# 아이디어뱅크 온라인(v2) — 후속 작업 인계 메모

> 다른 컴퓨터에서 이어서 작업하기 위한 메모입니다. 작성: 2026-11-19, 기준 커밋 `fee1355` (`main`).
> **비밀 값(DB 비밀번호, Supabase 키, 토큰)은 이 문서에 없습니다.** Vercel 환경 변수에만 있습니다.

## 1. 지금 상태 한눈에

| 항목 | 값 |
|---|---|
| 사용자 웹 | https://idea-bank-web-omega.vercel.app |
| 관리자 사이트 | https://idea-bank-admin.vercel.app (관리자 계정 1개 생성됨) |
| 회의실 페이지 (별개) | https://idea-bank-meeting.vercel.app — Vercel 프로젝트 `idea-bank-meeting`, 건드리지 않음 |
| Vercel 프로젝트 | `idea-bank-web` (팀 `changyeon0-gmailcoms-projects`, Hobby) — 사용자 웹 + 관리자가 **같은 함수** |
| Supabase 프로젝트 | `idea-bank-web` (서울 ap-northeast-2, ID `ucdeggbifpnnvsqertay`) — Postgres + Storage 버킷 `ideabank-files`(비공개) |
| GitHub | `lee-changyeon/idea-bank`, `main` 에 푸시하면 Vercel 이 자동 배포 |
| 함수 지역 | 서울 `icn1` (`vercel.json`) |
| 정식 서비스 여부 | **아직 아님** (`IB_LAUNCHED` 없음) |

점검 결과(2026-11-19): 로컬 테스트 21개 통과, 온라인 전체 흐름 점검 24개 통과, 온라인 20MB 첨부 점검 통과, 로컬 :8090/:8091 실행 흐름 통과.

## 2. 다른 컴퓨터에서 시작하기

```bash
git clone https://github.com/lee-changyeon/idea-bank.git
cd idea-bank
```

- Python 3.11 이상(개발은 3.13). Windows 에서는 `PYTHONUTF8=1` 을 켜고 실행하세요.
- 로컬 실행에는 외부 패키지가 필요 없습니다(SQLite). Postgres 를 로컬에서 시험할 때만 `pip install -r requirements.txt` (psycopg) 를 설치합니다.
- `web/data/`(로컬 DB·첨부), `.env*`, `ideas/`, `exports/` 는 git 에 없습니다. 새 컴퓨터의 로컬 DB 는 비어 있고, 처음 실행하면 데모 데이터가 만들어집니다.

```bash
python -m unittest discover -s tests       # 테스트 (21개)
run_web.bat     # 사용자 웹 http://localhost:8090  (빈 DB 면 데모 데이터 생성)
run_admin.bat   # 관리자    http://localhost:8091
```

- 데모 계정: `web/seed_accounts.example.json` (가짜 값, 로컬 전용).
- 온라인 점검:
  ```bash
  python web/tools/smoke.py https://idea-bank-web-omega.vercel.app        # 전체 흐름 24항목
  python web/tools/smoke_big.py https://idea-bank-web-omega.vercel.app 20 # 20MB 첨부
  ```
  - 두 스크립트 모두 실행할 때마다 운영 DB 에 `smoke-…@example.com` 계정과 아이디어를 새로 만듭니다.
  - 원장은 지울 수 없으므로 꼭 필요할 때만 돌리세요.

## 3. 구조 (핵심 파일)

| 파일 | 역할 |
|---|---|
| `api/index.py` | Vercel 입구. 호스트 이름으로 앱을 고름(`IB_ADMIN_HOSTS`, 기본 `idea-bank-admin.vercel.app` → 관리자). `/api/cron/*` 는 항상 사용자 앱 |
| `vercel.json` | `builds`(`@vercel/python`) + `routes`, 지역 `icn1`, Cron `0 3 * * *` → `/api/cron/tsa` |
| `web/server.py` / `admin/server.py` | 두 앱의 라우트 (로컬에서는 각각 :8090 / :8091) |
| `web/ibweb/db.py` | `DATABASE_URL` 이 있으면 Postgres(`PgDB`), 없으면 SQLite. 쓰기는 `pg_advisory_xact_lock` 으로 직렬화 |
| `web/ibweb/schema_pg.sql` | Postgres 스키마 (원장 수정·삭제 금지 트리거, 모든 표 RLS 켜고 anon 권한 회수) |
| `web/ibweb/files.py` | 첨부 저장: 로컬 `web/data/files` / Supabase Storage. 서명 올리기·내려받기, 임시 업로드 정리 |
| `web/ibweb/ledger.py` | 해시 체인 원장 + 공인 시각(RFC 3161). 서버리스에서는 요청 끝에서 짧게 처리 + Cron |
| `web/ibweb/security.py` | scrypt, 세션, 로그인 제한(DB), 관리자 비밀번호 정책 |
| `web/DEPLOY_SUPABASE.md` | **설계·운영 문서 (자세한 내용은 여기)** — §7 환경 변수, §10 DB 비밀번호 변경, §11 관리자 온라인, §12 비밀번호 정책 |

증명 규칙(`ideabank/canonical.py`: `ideabank/1` 정규화 JSON, `entry_hash = sha256(prev:seq:content_hash)`)은 바꾸지 않았습니다. 온라인 증명 파일도 v1 검증기로 통과합니다.

## 4. Vercel 환경 변수 (이름만 — 값은 Vercel 에만)

| 이름 | 내용 |
|---|---|
| `DATABASE_URL` | Supabase Transaction pooler (`postgres.ucdeggbifpnnvsqertay@aws-1-ap-northeast-2.pooler.supabase.com:6543`) + DB 비밀번호 |
| `SUPABASE_URL` | `https://ucdeggbifpnnvsqertay.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service_role 키 |
| `CRON_SECRET` | Cron 인증용 무작위 문자열 |
| `ADMIN_SETUP_TOKEN` | 첫 관리자 만들기 / 관리자 비밀번호 재설정용 토큰 (대표가 따로 보관) |
| (정식 서비스 때) `IB_LAUNCHED=1` | 관리자 강한 비밀번호 강제 |
| (선택) `IB_ADMIN_HOSTS`, `IB_STORAGE_BUCKET` | 관리자 주소, Storage 버킷 이름 |

## 5. 운영하면서 겪은 함정 (꼭 읽기)

1. **환경 변수를 바꾸면 반드시 다시 배포**해야 적용됩니다. Deployments → ⋯ → Redeploy, 또는 `main` 에 푸시하면 됩니다.
2. Vercel 에서 저장·배포할 때 **본인 확인(2단계 인증) 창**이 자주 뜹니다. 코드를 입력하고 Verify 까지 눌러야 실제로 저장됩니다. 저장 뒤 목록에 "Updated just now" 가 보이는지 확인하세요.
3. 저장하지 않은 Vercel 입력창을 새로 고치면 입력한 값이 사라집니다.
4. DB 연결이 안 되면 Vercel → Logs 에서 `password_length` 를 검색하세요. `[DB] 연결 실패` 줄에 사용자 이름·호스트·포트·비밀번호 길이가 나옵니다(비밀번호 자체는 없음). 길이로 새 값이 실제로 들어갔는지 확인할 수 있습니다.
5. DB 비밀번호는 영문·숫자만 쓰세요. 특수문자가 들어가면 주소에서 깨집니다. 채팅 기록에 남은 비밀번호는 쓰지 말고 Supabase 에서 재설정하세요.
6. Supabase 무료 프로젝트는 오래 쓰지 않으면 일시 정지됩니다. 예전 프로젝트("changyeon's Project")는 1년 넘게 정지돼 복구할 수 없었습니다.
7. Vercel 은 `functions` 설정만으로는 `api/index.py` 를 인식하지 못해 빌드가 실패했습니다(`unused_function`). 그래서 `builds` 방식을 씁니다.
8. 운영 DB 에는 점검용 계정·아이디어가 여러 건 있습니다(`smoke-…@example.com`). 원장이 추가 전용이라 지울 수 없습니다. 깨끗하게 시작하려면 DB 를 통째로 다시 만들어야 합니다.

## 6. 후속 작업 목록 (우선순위 순)

1. **정식 서비스 전 보안**
   - ~~관리자 2단계 인증(TOTP)~~ — 2026-11-19 추가됨 (`web/DEPLOY_SUPABASE.md` §13). 남은 것: QR 코드 표시, 예비 복구 코드
   - 관리자 접속 IP 제한
   - 정식 오픈 때 Vercel 에 `IB_LAUNCHED=1` 을 넣고 다시 배포해 관리자 강한 비밀번호를 강제
   - `ADMIN_SETUP_TOKEN` 은 길고 무작위로 유지 (재설정에 쓰이므로 지우면 재설정 기능도 꺼짐)
2. **본인 확인·알림**
   - 회원 이메일 인증, 비밀번호 찾기(사용자)
   - NDA 서명·열람·대출 신청 알림 메일
3. **NDA 전자서명 고도화**: 지금은 클릭 서명입니다. 본인 확인 전자서명으로 바꾸고, 약정문은 법률 검토를 받으세요.
4. **큰 증명 파일 검증**: 3MB 를 넘는 zip 은 온라인 [검증] 화면에서 검사할 수 없습니다. 브라우저 안에서 zip 을 풀어 검증하는 방식을 검토하세요.
5. **원장 헤드 정기 공개**: F12 외부 공개, OpenTimestamps 이중 앵커.
6. **본문 저장 시 암호화**: TRD §9, 해시는 평문 기준을 유지합니다.
7. **계약·정산 자동화**: LA-2026-001 템플릿 자동 작성, 에스크로 연동(PRD v4).
8. **관리자 권한 분리**: 심사·정산·감사 열람.
9. 사용자 지정 도메인 연결: 지금은 `*.vercel.app` 입니다. 연결하면 `IB_ADMIN_HOSTS` 도 바꿔야 합니다.
10. 운영 DB 정리: 정식 오픈 전에 DB 를 새로 만들지 결정하세요(점검 데이터 제거).

## 7. 관련 문서

- `web/DEPLOY_SUPABASE.md` — 온라인 설계·운영 전체
- `web/README.md` — 웹·관리자 앱 사용법, 아직 모의(목업)인 기능 표
- `web/NOTES_FOR_CORE.md` — 코어(`ideabank/`)에 바라는 변경
- `docs/PRD.md`, `docs/TRD.md`, `docs/TASK.md` — 제품·기술 요구사항
