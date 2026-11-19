"""SQLite 저장소. web(8090) 과 admin(8091) 두 프로세스가 같은 DB 파일을 쓴다.

- WAL 모드 + busy_timeout 으로 프로세스 간 동시 접근을 처리한다.
- 원장 추가는 BEGIN IMMEDIATE 트랜잭션 안에서만 한다 → 두 프로세스가 동시에 써도 순번이 꼬이지 않는다.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from . import WEB_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id         INTEGER PRIMARY KEY,
  email      TEXT UNIQUE NOT NULL,
  name       TEXT NOT NULL,
  role       TEXT NOT NULL CHECK (role IN ('creator','business')),
  org        TEXT NOT NULL DEFAULT '',
  pw         TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS admins (
  id         INTEGER PRIMARY KEY,
  username   TEXT UNIQUE NOT NULL,
  name       TEXT NOT NULL,
  pw         TEXT NOT NULL,
  created_at TEXT NOT NULL,
  pw_weak    INTEGER NOT NULL DEFAULT 0,  -- 강한 비밀번호 기준에 못 미치면 1 (정식 서비스 때 변경 유도)
  totp_secret TEXT,                       -- 2단계 인증(TOTP) 비밀 키 (켜기 전에는 등록 중인 키)
  totp_on    INTEGER NOT NULL DEFAULT 0,
  totp_last  INTEGER NOT NULL DEFAULT 0   -- 마지막으로 쓴 코드의 시각 칸 (같은 코드 재사용 방지)
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  kind       TEXT NOT NULL CHECK (kind IN ('user','admin')),
  subject_id INTEGER NOT NULL,
  csrf       TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at REAL NOT NULL
);

-- 하나의 해시 체인 이벤트 원장 (TRD §10). 추가 전용.
CREATE TABLE IF NOT EXISTS events (
  seq          INTEGER PRIMARY KEY,
  kind         TEXT NOT NULL,
  idea_seq     INTEGER,
  actor        TEXT NOT NULL,
  payload      BLOB NOT NULL,
  content_hash TEXT NOT NULL,
  prev_hash    TEXT NOT NULL,
  entry_hash   TEXT NOT NULL,
  created_at   TEXT NOT NULL,
  tsa_url      TEXT,
  tsa_time     TEXT,
  tsa_token    BLOB,
  tsa_error    TEXT,
  tsa_tries    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_ev_idea ON events(idea_seq);
CREATE INDEX IF NOT EXISTS ix_ev_hash ON events(content_hash);

-- 아이디어 (원문은 불변). disclosure/summary/hidden 은 공개 설정이라 바뀔 수 있고, 바뀔 때마다 원장에 기록된다.
CREATE TABLE IF NOT EXISTS ideas (
  seq          INTEGER PRIMARY KEY,
  idea_no      TEXT UNIQUE NOT NULL,
  owner_id     INTEGER NOT NULL,
  event_seq    INTEGER NOT NULL,
  parent_seq   INTEGER,
  root_seq     INTEGER NOT NULL,
  version      INTEGER NOT NULL,
  title        TEXT NOT NULL,
  body         TEXT NOT NULL,
  tags         TEXT NOT NULL,
  author       TEXT NOT NULL,
  canonical    BLOB NOT NULL,
  content_hash TEXT NOT NULL,
  created_at   TEXT NOT NULL,
  disclosure   TEXT NOT NULL DEFAULT 'private' CHECK (disclosure IN ('private','summary','nda')),
  summary      TEXT NOT NULL DEFAULT '',
  hidden       INTEGER NOT NULL DEFAULT 0,
  hidden_reason TEXT
);
CREATE INDEX IF NOT EXISTS ix_ideas_hash ON ideas(content_hash);
CREATE TABLE IF NOT EXISTS attachments (
  idea_seq INTEGER NOT NULL,
  name     TEXT NOT NULL,
  sha256   TEXT NOT NULL,
  size     INTEGER NOT NULL,
  mime     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_att_sha ON attachments(sha256);

CREATE TABLE IF NOT EXISTS ndas (
  id            INTEGER PRIMARY KEY,
  idea_seq      INTEGER NOT NULL,
  user_id       INTEGER NOT NULL,
  signer_name   TEXT NOT NULL,
  org           TEXT NOT NULL,
  template_ver  TEXT NOT NULL,
  template_hash TEXT NOT NULL,
  doc           BLOB NOT NULL,
  doc_hash      TEXT NOT NULL,
  event_seq     INTEGER NOT NULL,
  signed_at     TEXT NOT NULL,
  UNIQUE (idea_seq, user_id)
);
CREATE TABLE IF NOT EXISTS views (
  id        INTEGER PRIMARY KEY,
  idea_seq  INTEGER NOT NULL,
  user_id   INTEGER NOT NULL,
  level     TEXT NOT NULL,
  detail    TEXT NOT NULL DEFAULT '',
  event_seq INTEGER NOT NULL,
  at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_views_idea ON views(idea_seq);
CREATE TABLE IF NOT EXISTS loans (
  id               INTEGER PRIMARY KEY,
  loan_no          TEXT UNIQUE NOT NULL,
  idea_seq         INTEGER NOT NULL,
  business_id      INTEGER NOT NULL,
  terms            TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'submitted',
  creator_response TEXT NOT NULL DEFAULT 'pending',
  creator_note     TEXT NOT NULL DEFAULT '',
  review_note      TEXT NOT NULL DEFAULT '',
  reviewed_by      INTEGER,
  reviewed_at      TEXT,
  event_seq        INTEGER NOT NULL,
  created_at       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contracts (
  id          INTEGER PRIMARY KEY,
  contract_no TEXT UNIQUE NOT NULL,
  loan_id     INTEGER NOT NULL,
  signed_on   TEXT NOT NULL,
  terms       TEXT NOT NULL,
  doc_name    TEXT NOT NULL DEFAULT '',
  doc_hash    TEXT NOT NULL DEFAULT '',
  status      TEXT NOT NULL DEFAULT 'active',
  event_seq   INTEGER NOT NULL,
  created_by  INTEGER NOT NULL,
  created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settlements (
  id          INTEGER PRIMARY KEY,
  contract_id INTEGER NOT NULL,
  period      TEXT NOT NULL,
  kind        TEXT NOT NULL,
  amount      INTEGER NOT NULL,
  paid_on     TEXT NOT NULL DEFAULT '',
  note        TEXT NOT NULL DEFAULT '',
  event_seq   INTEGER NOT NULL,
  created_by  INTEGER NOT NULL,
  created_at  TEXT NOT NULL
);
-- 로그인 실패 기록 (서버리스에서는 인스턴스가 여러 개라 메모리 대신 DB 에 둔다)
CREATE TABLE IF NOT EXISTS login_fails (
  key TEXT NOT NULL,
  at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_lf_key ON login_fails(key);
-- 관리자 감사 로그. 자체 해시 체인을 가진다.
CREATE TABLE IF NOT EXISTS audit (
  id         INTEGER PRIMARY KEY,
  admin_id   INTEGER,
  admin_name TEXT NOT NULL,
  action     TEXT NOT NULL,
  target     TEXT NOT NULL DEFAULT '',
  detail     TEXT NOT NULL DEFAULT '{}',
  ip         TEXT NOT NULL DEFAULT '',
  at         TEXT NOT NULL,
  prev_hash  TEXT NOT NULL,
  entry_hash TEXT NOT NULL
);
"""

# 처음 스키마 뒤에 더한 admins 열 (기존 DB 는 시작할 때 자동으로 추가)
ADMIN_COLS = [("pw_weak", "INTEGER NOT NULL DEFAULT 0"), ("totp_secret", "TEXT"),
              ("totp_on", "INTEGER NOT NULL DEFAULT 0"), ("totp_last", "INTEGER NOT NULL DEFAULT 0")]

DATA_DIR = Path(os.environ.get("IB_DATA_DIR") or WEB_DIR / "data")  # 테스트는 임시 폴더를 쓴다


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "").strip()


def open_db():
    """DATABASE_URL 이 postgres 주소면 Postgres(Supabase), 아니면 로컬 SQLite."""
    url = database_url()
    if url.startswith(("postgres://", "postgresql://")):
        return PgDB(url)
    return DB()


class DB:
    kind = "sqlite"

    def __init__(self, path: Path | None = None):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "files").mkdir(exist_ok=True)
        self.path = Path(path or DATA_DIR / "ideabank_web.db")
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None, timeout=15)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=15000")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            cols = {r[1] for r in self.conn.execute("PRAGMA table_info(admins)")}
            for col, ddl in ADMIN_COLS:  # 예전에 만든 DB 에 나중에 더한 열
                if col not in cols:
                    self.conn.execute(f"ALTER TABLE admins ADD COLUMN {col} {ddl}")

    def q(self, sql: str, args=()) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, args).fetchall()

    def one(self, sql: str, args=()):
        with self.lock:
            return self.conn.execute(sql, args).fetchone()

    def val(self, sql: str, args=()):
        r = self.one(sql, args)
        return r[0] if r else None

    def exec(self, sql: str, args=()):
        with self.lock:
            return self.conn.execute(sql, args)

    @contextmanager
    def tx(self):
        """쓰기 트랜잭션. 프로세스 안에서는 RLock, 프로세스 사이에서는 BEGIN IMMEDIATE 로 직렬화."""
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self.conn
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
            else:
                self.conn.execute("COMMIT")


# ───────────────────────────── Postgres (Supabase) ─────────────────────────────
# 서비스 코드는 SQLite 문법(? 자리표시자)으로 쓰고, 여기서 Postgres 문법으로 바꾼다. 자세한 설명: web/DEPLOY_SUPABASE.md

LEDGER_LOCK = 7243100  # pg_advisory_xact_lock 키: 모든 쓰기 트랜잭션을 한 줄로 세운다 (= SQLite BEGIN IMMEDIATE)
ID_TABLES = {"users", "admins", "ndas", "views", "loans", "contracts", "settlements"}  # id 자동 번호 표
_INSERT = re.compile(r"^\s*INSERT\s+INTO\s+(\w+)", re.I)
_LIKE = re.compile(r"(?<![A-Za-z])LIKE(?![A-Za-z])")


def pg_sql(sql: str) -> str:
    """SQLite 문법 → Postgres 문법. 쿼리 안의 리터럴 % 는 쓰지 않는다(값은 모두 자리표시자로 넘긴다)."""
    sql = sql.replace("%", "%%").replace("?", "%s")
    return _LIKE.sub("ILIKE", sql)


class PgRow(dict):
    """sqlite3.Row 처럼 r["열"] 과 r[0] 둘 다 된다."""
    __slots__ = ("_vals",)

    def __init__(self, cols, vals):
        super().__init__(zip(cols, vals))
        self._vals = vals

    def __getitem__(self, k):
        if isinstance(k, int):
            return self._vals[k]
        return dict.__getitem__(self, k)


class PgCursor:
    def __init__(self, cur, lastrowid=None):
        self._cur = cur
        self.lastrowid = lastrowid
        self.rowcount = cur.rowcount

    def _wrap(self, r):
        if r is None:
            return None
        cols = [d.name for d in self._cur.description]
        return PgRow(cols, tuple(bytes(v) if isinstance(v, memoryview) else v for v in r))

    def fetchone(self):
        return self._wrap(self._cur.fetchone()) if self._cur.description else None

    def fetchall(self):
        return [self._wrap(r) for r in self._cur.fetchall()] if self._cur.description else []


class PgConn:
    """tx() 안에서 넘겨주는 연결. sqlite3 연결처럼 .execute(sql, args) 를 쓴다."""

    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql: str, args=()):
        m = _INSERT.match(sql)
        want_id = bool(m and m.group(1).lower() in ID_TABLES and "RETURNING" not in sql.upper())
        q = pg_sql(sql) + (" RETURNING id" if want_id else "")
        cur = self.raw.cursor()
        cur.execute(q, tuple(args))
        if want_id:
            return PgCursor(cur, cur.fetchone()[0])
        return PgCursor(cur)


class PgDB:
    kind = "postgres"

    def __init__(self, url: str):
        self.url = url
        self.lock = threading.RLock()
        self._raw = None
        self._schema_ok = False  # 첫 연결 때 확인. 시작할 때 연결하지 않으므로 DB 장애에도 정적 화면은 뜬다

    # 연결: 인스턴스마다 1개를 재사용, 끊기면 다시 연결 (Supabase 트랜잭션 풀러 → prepare 끔)
    def _connect(self):
        import psycopg  # Postgres 모드에서만 필요 (requirements.txt)
        try:
            self._raw = psycopg.connect(self.url, autocommit=True, prepare_threshold=None, connect_timeout=10)
        except psycopg.OperationalError:
            # 서버 로그용 진단 (비밀번호 자체는 남기지 않는다): 주소 형식이 맞는지 확인하는 데 쓴다
            from urllib.parse import urlparse
            u = urlparse(self.url)
            print(f"[DB] 연결 실패: user={u.username!r} host={u.hostname!r} port={u.port} db={u.path!r} "
                  f"password_length={len(u.password or '')} password_has_space={(u.password or '') != (u.password or '').strip()}")
            raise
        if not self._schema_ok:
            self._ensure_schema(self._raw)
            self._schema_ok = True
        return self._raw

    @property
    def raw(self):
        if self._raw is None or self._raw.closed:
            return self._connect()
        return self._raw

    def _run(self, fn):
        try:
            return fn(PgConn(self.raw))
        except Exception as ex:
            import psycopg
            if isinstance(ex, psycopg.OperationalError) and self._raw is not None and self._raw.closed:
                return fn(PgConn(self._connect()))  # 한 번만 다시 연결해서 재시도
            raise

    @staticmethod
    def _ensure_schema(raw):
        if not raw.execute("SELECT to_regclass('public.login_fails')").fetchone()[0]:
            sql = (Path(__file__).with_name("schema_pg.sql")).read_text(encoding="utf-8")
            with raw.transaction():
                raw.execute("SELECT pg_advisory_xact_lock(%s)", (LEDGER_LOCK,))
                raw.execute(sql)
        # 나중에 더한 열 (이미 있으면 아무것도 안 함)
        for col, ddl in ADMIN_COLS:
            raw.execute(f"ALTER TABLE admins ADD COLUMN IF NOT EXISTS {col} {ddl}")

    @property
    def conn(self):  # ideabank.bundle.verify 등 .execute 만 쓰는 곳을 위한 어댑터
        return PgConn(self.raw)

    def q(self, sql: str, args=()) -> list:
        with self.lock:
            return self._run(lambda c: c.execute(sql, args).fetchall())

    def one(self, sql: str, args=()):
        with self.lock:
            return self._run(lambda c: c.execute(sql, args).fetchone())

    def val(self, sql: str, args=()):
        r = self.one(sql, args)
        return r[0] if r else None

    def exec(self, sql: str, args=()):
        with self.lock:
            return self._run(lambda c: c.execute(sql, args))

    @contextmanager
    def tx(self):
        """쓰기 트랜잭션. 원장 순번이 꼬이지 않도록 전역 advisory lock 으로 모든 쓰기를 직렬화한다."""
        with self.lock:
            raw = self.raw
            if raw.closed:
                raw = self._connect()
            with raw.transaction():
                raw.execute("SELECT pg_advisory_xact_lock(%s)", (LEDGER_LOCK,))
                yield PgConn(raw)


def row(r) -> dict | None:
    return dict(r) if r is not None else None


def jl(s: str):
    return json.loads(s) if s else None
