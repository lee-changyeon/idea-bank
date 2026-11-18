"""SQLite 저장소. web(8090) 과 admin(8091) 두 프로세스가 같은 DB 파일을 쓴다.

- WAL 모드 + busy_timeout 으로 프로세스 간 동시 접근을 처리한다.
- 원장 추가는 BEGIN IMMEDIATE 트랜잭션 안에서만 한다 → 두 프로세스가 동시에 써도 순번이 꼬이지 않는다.
"""
from __future__ import annotations

import json
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
  created_at TEXT NOT NULL
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

DATA_DIR = WEB_DIR / "data"


class DB:
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


def row(r) -> dict | None:
    return dict(r) if r is not None else None


def jl(s: str):
    return json.loads(s) if s else None
