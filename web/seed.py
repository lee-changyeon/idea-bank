"""데모 데이터 만들기: 창안자 2, 사업자 1, 관리자 1, 예시 아이디어 몇 건.

계정 정보는 web/seed_accounts.example.json 에 있다 (가짜 데이터).
  python web/seed.py            # 비어 있는 DB 에만 넣음
  python web/seed.py --reset    # web/data 를 지우고 새로 만듦 (확인 질문 있음)
  python web/seed.py --no-tsa   # 공인 시각 없이 (오프라인일 때)
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ibweb import config, ledger as L, security as S, service as svc  # noqa: E402
from ibweb.db import DATA_DIR, DB  # noqa: E402
from ideabank import canonical as C  # noqa: E402


def main(args=None):
    args = sys.argv[1:] if args is None else args
    if "--reset" in args and DATA_DIR.exists():
        if "--yes" not in args and input(f"{DATA_DIR} 를 지우고 새로 만들까요? (y/N) ").strip().lower() != "y":
            print("취소했습니다.")
            return
        shutil.rmtree(DATA_DIR)
    seed = json.loads((HERE / "seed_accounts.example.json").read_text(encoding="utf-8"))
    db = DB()
    if db.val("SELECT COUNT(*) FROM users") or db.val("SELECT COUNT(*) FROM admins"):
        print("이미 데이터가 있습니다. 새로 만들려면 --reset 을 붙이세요.")
        return
    stamper = L.Stamper(db, config.load()["tsa_urls"])
    for a in seed["admins"]:
        db.exec("INSERT INTO admins (username, name, pw, created_at) VALUES (?,?,?,?)",
                (a["username"], a["name"], S.hash_password(a["password"]), C.now_iso()))
    users = {}
    for u in seed["users"]:
        users[u["key"]] = svc.signup(db, u["email"], u["password"], u["name"], u["role"], u["org"])
    for i in seed["ideas"]:
        d = svc.create_idea(db, stamper, users[i["owner"]], title=i["title"], body=i["body"], tags=i["tags"],
                            attachments=[], disclosure=i["disclosure"], summary=i["summary"],
                            timestamp="--no-tsa" not in args)
        print(f"  {d['idea_no']}  {d['title']}  공인 시각: {d['tsa_time'] or '대기'}")
    print(f"완료: 관리자 {len(seed['admins'])}, 회원 {len(seed['users'])}, 아이디어 {len(seed['ideas'])}")
    print("계정 정보: web/seed_accounts.example.json")


if __name__ == "__main__":
    main()
