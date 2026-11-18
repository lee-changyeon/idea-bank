# 아이디어뱅크 (Idea Bank) — TRD

> 기술 요구사항 정의서 · v0.1 · 2026-11-18 · 관련 문서: [PRD.md](PRD.md), [TASK.md](TASK.md)

## 1. 기술 스택

| 영역 | 선택 | 이유 |
|------|------|------|
| 런타임 | Python 3.11+ (개발 환경 3.13) | 설치 PC에 Node 없음, Python 표준 라이브러리만으로 구현 가능 |
| 웹 서버 | `http.server.ThreadingHTTPServer` | 의존성 0, 로컬 단일 사용자 용도에 충분 |
| 저장소 | SQLite (`sqlite3`) + 파일 저장소 | 단일 파일 DB, 백업 용이 |
| 해시 | SHA-256 (`hashlib`) | 표준, TSA·openssl 호환 |
| 타임스탬프 | RFC 3161 TSA (DER 직접 인코딩, `urllib`) | 공인 제3자 시점 증명, openssl 로 독립 검증 가능 |
| 프런트엔드 | 정적 HTML + Vanilla JS + CSS | 빌드 도구 불필요 |
| 브라우저 해시 | Web Crypto `crypto.subtle.digest` | 파일 조회 시 파일을 서버에 보내지 않음 |

## 2. 아키텍처

```
브라우저 (static/index.html, app.js)
   │  JSON REST
   ▼
server.py  ── ideabank/store.py ── SQLite (data/ideabank.db)
   │                 │
   │                 └─ data/files/<sha256>   (첨부, 내용주소 저장)
   └─ ideabank/tsa.py ── HTTPS ──▶ 외부 TSA (해시만 전송)
```

## 3. 디렉터리 구조

```
idea-bank/
├─ server.py              # HTTP 서버, 라우팅
├─ ideabank/
│  ├─ __init__.py
│  ├─ canonical.py        # 정규화 JSON, 해시 함수
│  ├─ store.py            # DB 스키마, 등록, 원장, 검증
│  ├─ tsa.py              # RFC 3161 클라이언트
│  └─ bundle.py           # 증명 번들 zip 생성/검증
├─ static/                # index.html, app.js, style.css, cert.html
├─ config.json            # TSA 목록, 포트 등 (선택)
├─ data/                  # 실행 시 생성 (git 제외)
└─ docs/                  # PRD, TRD, TASK
```

## 4. 데이터 모델

### 4.1 `ideas` 테이블 (추가 전용)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `seq` | INTEGER PK | 원장 순번 (1부터, 공백 없음) |
| `idea_no` | TEXT UNIQUE | 표시용 등록번호 `IB-YYYYMMDD-NNNNNN` |
| `parent_seq` | INTEGER NULL | 개정 대상 원본 |
| `root_seq` | INTEGER | 개정 계보의 최초 판 |
| `version` | INTEGER | 판 번호 (원본 = 1) |
| `canonical` | TEXT | 해시 대상이 되는 정규화 JSON 원문 |
| `content_hash` | TEXT | `sha256(canonical)` hex |
| `prev_hash` | TEXT | 직전 항목의 `entry_hash` (최초는 `"0"*64`) |
| `entry_hash` | TEXT | `sha256(prev_hash + ":" + seq + ":" + content_hash)` |
| `created_at` | TEXT | 서버 등록 시각 (UTC ISO-8601, 밀리초) |
| `tsa_url` | TEXT NULL | 사용한 TSA |
| `tsa_time` | TEXT NULL | 토큰 genTime (UTC) |
| `tsa_token` | BLOB NULL | TimeStampToken DER |
| `tsa_error` | TEXT NULL | 마지막 실패 사유 |

검색 편의용 컬럼(`title`, `body`, `tags`, `author`)은 `canonical`에서 파생하여 함께 저장한다. **진실의 원천은 `canonical`.**

### 4.2 `attachments` 테이블

| 컬럼 | 설명 |
|------|------|
| `seq` | 소속 아이디어 |
| `name` | 원본 파일명 |
| `sha256` | 파일 해시 (저장 파일명) |
| `size` | 바이트 |
| `mime` | MIME 타입 |

### 4.3 정규화 JSON (canonical) 스키마

```json
{
  "schema": "ideabank/1",
  "title": "...",
  "body": "...",
  "tags": ["정렬됨", "중복제거"],
  "author": "...",
  "created_at": "2026-11-18T04:30:12.345Z",
  "parent": "<부모 content_hash 또는 null>",
  "attachments": [{"name": "a.pdf", "sha256": "...", "size": 1234}]
}
```

- 직렬화: `json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))` → UTF-8
- 텍스트는 NFC 정규화, 줄바꿈 `\n` 통일
- 첨부는 **파일 해시**만 포함 → 첨부 내용이 바뀌면 `content_hash`가 바뀜
- 부모의 `content_hash`를 포함 → 개정 계보 자체도 해시로 묶임

## 5. 시점 증명 설계

### 5.1 3중 증명

1. **내용 해시**: `content_hash` — 내용이 한 글자라도 바뀌면 달라짐
2. **해시 체인 원장**: 각 항목이 직전 `entry_hash`를 포함 → 중간 항목 변조·삭제·순서 변경 시 이후 체인이 모두 깨짐
3. **RFC 3161 TSA 토큰**: 외부 공인 기관이 `content_hash`에 서명한 시각 → 운영자도 조작 불가

### 5.2 TSA 연동

- 요청: `TimeStampReq { version 1, messageImprint {sha256, content_hash}, nonce(64bit 랜덤), certReq TRUE }`
- 기본 TSA 목록 (순서대로 폴백, `config.json`에서 변경 가능):
  1. `http://timestamp.digicert.com`
  2. `https://freetsa.org/tsr`
- 응답 처리: PKIStatus 0/1 확인 → 토큰 추출 → 토큰 내부 messageImprint가 요청 해시와 같은지 확인 → `genTime` 추출
- 실패 시 아이디어는 등록하되 `tsa_error` 기록, "타임스탬프 재요청" 가능
- 타임아웃 15초

### 5.3 외부 독립 검증 (번들 안내문에 포함)

```bash
openssl ts -reply -in token.tsr -text                       # 시각·해시 확인
openssl ts -verify -digest <content_hash> -in token.tsr -CAfile tsa-ca.pem
sha256sum canonical.json                                     # content_hash 재계산
```

> 저장되는 토큰은 TimeStampToken(ContentInfo)이므로 번들에는 openssl 호환을 위해 `token.tsr`(TimeStampResp 형태로 재포장)과 `token.der` 둘 다 넣는다.

## 6. API 명세

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/status` | 건수, 원장 헤드 해시, TSA 설정 |
| GET | `/api/ideas?q=&tag=` | 목록·검색 (최신순) |
| GET | `/api/ideas/{seq}` | 상세 + 첨부 + 개정 이력 |
| POST | `/api/ideas` | 등록. body: `{title, body, tags[], author, parent_seq?, attachments:[{name, mime, data_b64}], timestamp: bool}` |
| POST | `/api/ideas/{seq}/timestamp` | TSA 재요청 (토큰 없는 항목만) |
| GET | `/api/ideas/{seq}/files/{sha256}` | 첨부 다운로드 |
| GET | `/api/ideas/{seq}/bundle` | 증명 번들 zip |
| GET | `/api/verify/chain` | 원장 전체 검사 → `{ok, count, broken:[{seq, reason}]}` |
| POST | `/api/verify/bundle` | `{zip_b64}` → 해시·토큰·원장 일치 결과 |
| GET | `/api/lookup/{sha256}` | 내용 해시 또는 첨부 해시로 등록 항목 조회 |

- 모든 수정·삭제 API는 **존재하지 않음** (불변성).
- 오류 응답: `{ "error": "메시지" }` + 4xx/5xx
- 요청 본문 최대 30MB (첨부 base64 포함), 첨부 1개 최대 20MB

## 7. 원장 검증 알고리즘

```
prev = "0"*64
for row in ideas order by seq:
    assert row.seq == 기대 순번                      # 삭제 탐지
    assert sha256(row.canonical) == row.content_hash  # 내용 변조 탐지
    assert row.prev_hash == prev
    assert sha256(prev:seq:content_hash) == row.entry_hash
    for att in row 첨부: assert sha256(파일) == att.sha256 and att ∈ canonical
    if row.tsa_token: assert token 내 해시 == content_hash
    prev = row.entry_hash
```

## 8. 보안·프라이버시

- 서버는 기본 `127.0.0.1` 바인딩 (LAN 공개는 설정으로만)
- 외부 전송 데이터: TSA로 해시 32바이트 + nonce 만
- 정적 파일 경로 탐색(path traversal) 차단, 첨부 파일명 sanitize
- 첨부 다운로드 시 `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`
- 동시 등록 시 원장 순서 보장: SQLite `BEGIN IMMEDIATE` 트랜잭션

## 9. 한계와 향후 과제

- 로컬 DB 전체를 새로 만들어 바꿔치기하는 공격은 체인만으로 막을 수 없음 → TSA 토큰(외부 시각)과 원장 헤드 정기 공개(F12)로 보완
- TSA 인증서 체인 검증은 openssl 에 위임 (앱 내부는 해시 일치·시각 추출까지)
- v2: 사용자 인증, 본문 암호화(해시는 평문 기준 유지), OpenTimestamps 이중 앵커

## 10. 아이디어 대출(v2~)을 위한 설계 고려

> PRD §10. 아래는 v1 구현 때 **나중에 막히지 않도록** 지켜 둘 원칙이다. 상세 설계는 TRD v0.2(T7.1)에서 한다.

- **온라인 전환**: 창안자와 사업자가 만나야 하므로 v2부터는 서버형 서비스가 된다.
  - v1의 `canonical` 형식, 해시 규칙, 원장 구조는 그대로 옮길 수 있게 유지한다.
  - `schema: "ideabank/1"` 은 바꾸지 않고, 필드를 추가할 때는 버전을 올린다.
- **이벤트 원장 일반화**: v1 원장은 "아이디어 등록"만 기록한다. v2부터는 같은 해시 체인에 아래 이벤트도 기록한다.
  - 열람 (누가, 언제, 어떤 아이디어를)
  - NDA 서명
  - 계약 체결
  - 진행 보고
  - 정산
  
  v1의 `ideas` 테이블은 이벤트 원장의 한 종류로 옮길 수 있게 설계한다.
- **열람 기록**: 열람자 ID, 아이디어 `content_hash`, NDA 문서 해시, 시각을 묶어 해시하고 공인 시각을 받는다.
- **계약·정산 데이터**는 금액과 지분 정보를 포함하므로 접근 권한을 분리하고, 감사 로그를 남긴다.
- **보관하지 않는 것**: 지분·대금은 제휴 기관이 보관한다. 시스템은 지시와 기록만 담당한다.
