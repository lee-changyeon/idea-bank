"""관리자(admin 사이트, 8091) 계정 관리 CLI.

기존 DB(web/data/ideabank_web.db)에 계정을 추가하거나 비밀번호를 바꾼다. DB 를 지우거나 초기화하지 않는다.
모든 변경은 감사 로그(audit)에 'cli' 로 남는다.

  python web/manage_admins.py list
  python web/manage_admins.py add <username> <name> [--generate | --visible]
  python web/manage_admins.py passwd <username> [--generate | --visible]
  python web/manage_admins.py reset2fa <username>     # 2단계 인증 초기화 (휴대폰 분실 등)

비밀번호는 getpass 로 입력받는다. 입력한 글자는 화면에 보이지 않으니 그대로 치고 Enter 를 누른다.
터미널에서 입력이 아예 안 되면 --visible 을 붙여 글자가 보이게 입력한다.
입력을 비워 두거나 --generate 를 붙이면 무작위 비밀번호를 만들어 한 번만 화면에 보여 준다.
"""
from __future__ import annotations

import getpass
import re
import secrets
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ibweb import security as S, service as svc  # noqa: E402
from ibweb.db import DB  # noqa: E402
from ideabank import canonical as C  # noqa: E402

USERNAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
MIN_PW = S.PRELAUNCH_MIN  # 정식 서비스 전 최소 길이. 정식 서비스 기준은 S.STRONG_RULE


def _password(generate: bool, visible: bool = False) -> tuple[str, bool]:
    """(비밀번호, 자동 생성 여부)."""
    if not generate:
        read = input if visible else getpass.getpass
        if not visible:
            print("(입력한 글자는 화면에 보이지 않습니다. 그대로 입력하고 Enter 를 누르세요.)")
        pw = read("비밀번호 (비워 두면 자동 생성): ")
        if pw:
            if len(pw) < MIN_PW:
                sys.exit(f"비밀번호는 {MIN_PW}자 이상이어야 합니다.")
            if read("비밀번호 확인: ") != pw:
                sys.exit("두 비밀번호가 다릅니다.")
            return pw, False
    return secrets.token_urlsafe(12), True


def _show_generated(username: str, pw: str):
    print(f"  {username} 의 임시 비밀번호: {pw}")
    print("  (이 화면에서 한 번만 보여 줍니다. 안전한 곳에 옮기거나 passwd 로 바꾸세요.)")


def cmd_list(db: DB):
    rows = db.q("SELECT id, username, name, created_at FROM admins ORDER BY id")
    if not rows:
        print("관리자 계정이 없습니다.")
        return
    print(f"{'id':>3}  {'username':<12} {'name':<16} created_at")
    for r in rows:
        print(f"{r['id']:>3}  {r['username']:<12} {r['name']:<16} {r['created_at']}")


def cmd_add(db: DB, username: str, name: str, generate: bool, visible: bool = False):
    if not USERNAME_RE.match(username):
        sys.exit("username 은 영문 소문자로 시작하는 2~32자 (a-z, 0-9, _) 여야 합니다.")
    name = name.strip()
    if not name:
        sys.exit("name 을 입력하세요.")
    if db.val("SELECT 1 FROM admins WHERE username=?", (username,)):
        sys.exit(f"이미 있는 관리자 아이디입니다: {username}")
    pw, gen = _password(generate, visible)
    db.exec("INSERT INTO admins (username, name, pw, created_at) VALUES (?,?,?,?)",
            (username, name, S.hash_password(pw), C.now_iso()))
    db.exec("UPDATE admins SET pw_weak=? WHERE username=?", (0 if S.admin_pw_strong(pw) else 1, username))
    svc.audit(db, None, "관리자 계정 추가", username, {"name": name, "via": "manage_admins.py"}, "cli")
    print(f"추가했습니다: {username} ({name})")
    if gen:
        _show_generated(username, pw)


def cmd_passwd(db: DB, username: str, generate: bool, visible: bool = False):
    if not db.val("SELECT 1 FROM admins WHERE username=?", (username,)):
        sys.exit(f"없는 관리자 아이디입니다: {username}")
    pw, gen = _password(generate, visible)
    db.exec("UPDATE admins SET pw=?, pw_weak=? WHERE username=?",
            (S.hash_password(pw), 0 if S.admin_pw_strong(pw) else 1, username))
    svc.audit(db, None, "관리자 비밀번호 변경", username, {"via": "manage_admins.py"}, "cli")
    print(f"비밀번호를 바꿨습니다: {username}")
    if gen:
        _show_generated(username, pw)


def cmd_reset2fa(db: DB, username: str):
    if not db.val("SELECT 1 FROM admins WHERE username=?", (username,)):
        sys.exit(f"없는 관리자 아이디입니다: {username}")
    db.exec("UPDATE admins SET totp_on=0, totp_secret=NULL, totp_last=0 WHERE username=?", (username,))
    db.exec("DELETE FROM sessions WHERE kind='admin' AND subject_id=(SELECT id FROM admins WHERE username=?)", (username,))
    svc.audit(db, None, "관리자 2단계 인증 초기화", username, {"via": "manage_admins.py"}, "cli")
    print(f"2단계 인증을 껐습니다: {username} (다음 로그인 뒤 [보안 설정] 에서 다시 켜세요)")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    generate = "--generate" in argv
    visible = "--visible" in argv
    args = [a for a in argv if a not in ("--generate", "--visible")]
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    db = DB()
    cmd = args[0]
    if cmd == "list" and len(args) == 1:
        cmd_list(db)
    elif cmd == "add" and len(args) == 3:
        cmd_add(db, args[1], args[2], generate, visible)
    elif cmd == "passwd" and len(args) == 2:
        cmd_passwd(db, args[1], generate, visible)
    elif cmd == "reset2fa" and len(args) == 2:
        cmd_reset2fa(db, args[1])
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
