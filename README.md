# 아이디어뱅크 (by FirstPrint) — v1 MVP

특허로 보호하기 어려운 아이디어를 자유롭게 적어 두고, **"그 시각에 이 내용이 있었고 그 뒤 바뀌지 않았다"** 를 제3자가 검증할 수 있게 증명하는 로컬 웹앱입니다.

- 사용법: [docs/USER_GUIDE.md](docs/USER_GUIDE.md) (앱의 "도움말" 메뉴와 같은 내용)
- 기획·설계: [docs/PRD.md](docs/PRD.md) · [docs/TRD.md](docs/TRD.md) · [docs/TASK.md](docs/TASK.md)

## 실행

**필요한 것:** Python 3.11 이상. 추가 패키지는 없습니다.

1. `run.bat` 을 더블클릭합니다. 브라우저가 `http://localhost:8080` 으로 열립니다.
2. 앱을 쓰는 동안 검은 창은 닫지 마세요.

명령줄로 실행할 수도 있습니다.

```bash
python server.py
```

설정은 `config.json` 에서 바꿉니다: 포트, 바인딩 주소, 데이터 폴더, 공인 시각 기관 목록.

시험할 때는 별도 보관함을 쓰세요. 등록한 기록은 지울 수 없습니다.

```bash
python server.py --data C:/temp/ib-test --port 8081
```

## 증명 방식 (3중)

1. **고유 지문**: 정규화한 원문(`canonical.json`)의 SHA-256 값입니다.
2. **해시 체인 원장**: 각 기록이 앞 기록의 고리값을 포함합니다. 중간 기록을 바꾸거나 지우면 바로 드러납니다.
3. **공인 시각**: RFC 3161 TSA(기본 DigiCert, 실패 시 FreeTSA)의 서명입니다. 외부로는 **고유 지문만** 보냅니다.

증명 파일(zip)에는 `VERIFY.txt` 가 들어 있어, 이 앱 없이도 `certutil`/`sha256sum` 과 `openssl ts` 로 검증할 수 있습니다.

## 폴더

```
server.py            HTTP 서버와 API (TRD §6)
ideabank/
  canonical.py       정규화 JSON, 해시 규칙
  store.py           SQLite 원장 (추가 전용), 검증
  tsa.py             RFC 3161 클라이언트 (표준 라이브러리만)
  bundle.py          증명 파일 만들기·검증
static/              화면 (index.html, app.js, style.css)
tools/import_idea.py 이미 공인 시각을 받은 기록 폴더 가져오기
tests/test_core.py   단위·변조 테스트
ideas/               1호 아이디어 원본 증명 자료
data/                보관함 (실행 시 생성, git 제외) ← 백업 대상
```

## 테스트

```bash
python -m unittest discover -s tests -v
```

테스트 범위는 다음과 같습니다. 테스트는 외부 공인 시각 기관에 접속하지 않습니다.
- 정규화와 해시 안정성
- DER 인코딩
- 실제 1호 아이디어 토큰 해석
- 개정 계보, 검색, 첨부 조회
- 변조 탐지: 본문 변경, 표시값 변경, 행 삭제, 해시 재계산, 첨부 바꿔치기
- 증명 파일 왕복 검증

## 백업

`data` 폴더를 통째로 복사하면 됩니다. 원장 끝 고리값(검증 화면에 표시)을 따로 적어 두면, 나중에 보관함 전체를 바꿔치기했는지도 확인할 수 있습니다.

## 알려진 한계

- 공인 시각 기관 인증서 체인 검증은 openssl 에 맡깁니다. 앱은 해시 일치와 시각만 확인합니다.
- 단일 사용자 로컬 앱입니다. 다중 사용자와 아이디어 대출 기능은 v2 이후에 들어갑니다(PRD §9–10). 별도 세션이 `web/`, `admin/` 에서 만들고 있습니다.
- 이 증명은 존재 시점과 무결성만 보여 줍니다. 최초 창안자임이나 독창성은 증명하지 않습니다.
