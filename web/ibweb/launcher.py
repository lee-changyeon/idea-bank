"""run_web.bat / run_admin.bat 에서 쓰는 시작 도우미: 빈 DB 면 데모 데이터 만들기, 브라우저 열기."""
from __future__ import annotations

import os
import threading
import webbrowser


def prepare(argv: list[str], db, port: int, label: str):
    if "--seed-if-empty" in argv and not db.val("SELECT COUNT(*) FROM admins"):
        print("처음 실행: 데모 데이터를 만듭니다 (web/seed_accounts.example.json)...")
        import seed  # web/seed.py
        seed.main([])
    print(f"아이디어뱅크 {label}: http://localhost:{port}   (이 창을 닫으면 꺼집니다)")
    if "--open" in argv and os.environ.get("IB_NO_BROWSER") != "1":
        threading.Timer(1.0, webbrowser.open, args=(f"http://localhost:{port}",)).start()
