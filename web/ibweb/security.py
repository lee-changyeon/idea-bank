"""비밀번호 해시(scrypt), 세션, CSRF, 로그인 시도 제한."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time

from ideabank import canonical as C

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1

# ── 관리자 비밀번호 정책 ──
# 정식 서비스 전(IB_LAUNCHED 가 없음): 간단한 비밀번호(4자 이상)도 허용하되, 화면에서 계속 바꾸라고 안내한다.
# 정식 서비스(IB_LAUNCHED=1): 강한 비밀번호만 허용. 약한 비밀번호로 로그인하면 바꾸기 전에는 다른 기능을 쓸 수 없다.
PRELAUNCH_MIN = 4
STRONG_MIN = 12
STRONG_RULE = f"{STRONG_MIN}자 이상, 영문 소문자·대문자·숫자·특수문자 중 3가지 이상"


def launched() -> bool:
    return os.environ.get("IB_LAUNCHED", "").strip() == "1"


def admin_pw_strong(pw: str) -> bool:
    kinds = sum([any(c.islower() for c in pw), any(c.isupper() for c in pw), any(c.isdigit() for c in pw),
                 any(not c.isalnum() for c in pw)])
    return len(pw) >= STRONG_MIN and kinds >= 3


def admin_pw_problem(pw: str) -> str | None:
    """정책에 맞지 않으면 안내 문구, 맞으면 None."""
    if launched():
        return None if admin_pw_strong(pw) else f"정식 서비스 중에는 강한 비밀번호만 쓸 수 있습니다: {STRONG_RULE}."
    return None if len(pw) >= PRELAUNCH_MIN else f"비밀번호는 {PRELAUNCH_MIN}자 이상으로 정해 주세요."


def admin_policy() -> dict:
    on = launched()
    return {"launched": on, "min_len": STRONG_MIN if on else PRELAUNCH_MIN, "strong_rule": STRONG_RULE}
SESSION_TTL = 8 * 3600


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${h.hex()}"


def check_password(pw: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, h = stored.split("$")
        assert algo == "scrypt"
        got = hashlib.scrypt(pw.encode("utf-8"), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(got.hex(), h)
    except Exception:
        return False


# 존재하지 않는 계정에도 같은 시간이 걸리도록 비교용 더미 해시
DUMMY_HASH = hash_password(secrets.token_hex(8))


def _th(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(db, kind: str, subject_id: int) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    db.exec("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
    db.exec("INSERT INTO sessions (token_hash, kind, subject_id, csrf, created_at, expires_at) VALUES (?,?,?,?,?,?)",
            (_th(token), kind, subject_id, csrf, C.now_iso(), time.time() + SESSION_TTL))
    return token, csrf


def get_session(db, kind: str, token: str | None):
    if not token:
        return None
    s = db.one("SELECT * FROM sessions WHERE token_hash=? AND kind=?", (_th(token), kind))
    if not s or s["expires_at"] < time.time():
        return None
    return s


def end_session(db, token: str | None):
    if token:
        db.exec("DELETE FROM sessions WHERE token_hash=?", (_th(token),))


def csrf_ok(session, header_value: str | None) -> bool:
    return bool(session and header_value) and hmac.compare_digest(session["csrf"], header_value)


class Throttle:
    """IP+계정별 로그인 실패 제한: 10분 안에 5번 실패하면 10분 잠금.
    db 를 주면 login_fails 표에 기록한다 (서버리스는 인스턴스가 여러 개라 메모리로는 막을 수 없다)."""

    def __init__(self, limit=5, window=600, db=None):
        self.limit, self.window, self.db = limit, window, db
        self.fails: dict[str, list[float]] = {}
        self.lock = threading.Lock()

    def blocked(self, key: str) -> bool:
        now = time.time()
        if self.db is not None:
            self.db.exec("DELETE FROM login_fails WHERE at < ?", (now - self.window,))
            return (self.db.val("SELECT COUNT(*) FROM login_fails WHERE key=?", (key,)) or 0) >= self.limit
        with self.lock:
            xs = [t for t in self.fails.get(key, []) if now - t < self.window]
            self.fails[key] = xs
            return len(xs) >= self.limit

    def fail(self, key: str):
        if self.db is not None:
            self.db.exec("INSERT INTO login_fails (key, at) VALUES (?,?)", (key, time.time()))
            return
        with self.lock:
            self.fails.setdefault(key, []).append(time.time())

    def clear(self, key: str):
        if self.db is not None:
            self.db.exec("DELETE FROM login_fails WHERE key=?", (key,))
            return
        with self.lock:
            self.fails.pop(key, None)
