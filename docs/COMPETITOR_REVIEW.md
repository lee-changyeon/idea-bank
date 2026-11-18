# 경쟁사 조사: FirstPrint / 아이디어뱅크

- 작성일: 2026-11-18
- 조사 방법: 웹 검색, 공식 사이트, 언론·DB(CB Insights, Dealroom 등) 교차 확인
- 표기 원칙: 출처로 확인하지 못한 항목은 "확인 불가"로 적었습니다. 집계 사이트(CB Insights, Dealroom, PitchBook)의 상태 정보는 늦게 갱신될 수 있습니다.

---

## 1. 요약

- **A+B+C를 모두 결합한 서비스는 확인되지 않았습니다.** 아이디어 존재 시점 증명, 아이디어 대여(라이선스), 사업 성과에 따른 창작자 환원(로열티·지분, 에스크로), NDA 열람 로그를 한 서비스에서 묶어 운영하는 곳은 찾지 못했습니다. 다만 각 요소는 이미 시장에 있습니다.
- **증명 계층(A)은 이미 성숙했고 경쟁이 치열합니다.** 국내에는 영업비밀 원본증명제도가 있습니다. 한국지식재산보호원과 민간 지정기관 3곳(2025.1 지정)이 운영하며, 해시와 시점을 등록하고 아포스티유 발급도 지원합니다. 해외에는 Bernstein, OriginStamp, OpenTimestamps(무료)가 있습니다. MVP 단독으로는 차별화가 어렵습니다.
- **가장 겹치는 곳은 아이디어 거래(B·C) 쪽의 특허청 '아이디어로'입니다.** 표준계약서·NDA·보상금 기반 아이디어 거래를 2021년부터 운영 중이며, 2023년 누적 거래액 2억 원을 돌파했습니다. 단, 일회성 보상금 구조이고 사업 성과 연동 환원은 확인되지 않았습니다.
- **'성과 연동 환원'을 시도한 선례는 대부분 실패하거나 축소됐습니다.** Quirky(2015 파산), Edison Nation(2020 Vinco Ventures로 전환), IPXI(2015 폐쇄), WIPO PROOF(2022 신규 발급 중단)가 그 예입니다. 원인은 마진 구조, 수요 검증 부족, 사업성 재평가였습니다.
- **결론:** 정확히 같은 모델은 비어 있습니다. 다만 비어 있는 이유가 시장 실패일 수 있다는 점(아이디어 단독 가치의 낮은 거래성, 성과 정산의 어려움)이 가장 큰 위험입니다.

---

## 2. 카테고리별 표

### A. 아이디어·문서 존재 증명 / 타임스탬프

| 서비스 | 국가 | 내용 | 비즈니스 모델·가격 | 현재 상태 | 중복도 | 출처 |
|---|---|---|---|---|---|---|
| 영업비밀 원본증명서비스 (한국지식재산보호원 영업비밀보호센터) | 한국 | 원본 파일의 전자지문(해시), 전자서명, 시간정보를 등록해 보유 시점을 증명. 원본은 등록자가 보관. 2025년부터 원본증명서 아포스티유 발급 지원 | 공식 현행 수수료 확인 불가. 과거 민간 연계 사이트 기준 건당 1만 원 보도가 있으나 현재 요금으로 보기 어려움 | **운영 중.** 2010.11 한국특허정보원에서 시작해 2019.1 한국지식재산보호원으로 이관 | **높음** (MVP와 거의 동일한 기능, 공적 신뢰) | https://www.etoday.co.kr/news/view/2450104 , https://m.boannews.com/html/detail.html?idx=139251 |
| 민간 원본증명기관 (온누리국제영업비밀보호센터, LG CNS, 레드윗) | 한국 | 위 제도의 민간 지정기관 | 개별 요금 확인 불가 | **운영 중** (2025.1 지정) | 높음 | https://economist.co.kr/article/view/ecn202501200006 |
| WIPO PROOF | 국제(WIPO) | 파일 해시 기반 디지털 타임스탬프 토큰 발급 | 토큰당 유료(당시 기준) | **종료.** 2020.5 출시, 2022.1.31 신규 토큰 발급 중단. 기존 토큰은 계속 유효하며 기존 계정 보관·검증은 5년간 지원(약 2027년 초까지) | 중간 (종료됨) | https://www.wipo.int/en/web/wipo-proof/w/news/2021/news_0003 |
| Bernstein | 독일 | 파일 해시를 비트코인 블록체인에 앵커링한 IP 증명서. 브라우저 암호화 보관, 버전 이력, 보안 공유. EU 적격 타임스탬프와 중국 신뢰 타임스탬프 포함(상위 요금제). 로펌용 화이트라벨. 사이트에 'Licensing' 활용 사례 페이지는 있으나 라이선스 중개 기능은 확인 불가 | 사이트 표시가(원화): 건당 ₩89,000, 월 ₩69,000(1건), ₩149,000(5건), ₩419,000(30건) | **운영 중** (2016~, 2026.11 블로그 업데이트 확인) | **높음** (증명서, 영업비밀, NDA 활용 사례까지 겹침) | https://www.bernstein.io |
| OriginStamp | 스위스 | 해시를 여러 블록체인에 앵커링하는 타임스탬프 API와 증명서 | 크레딧 기반 API. 연간 패키지 12,000 USD(월 50만 건) 등. 과거 무료 월 5건 | **운영 중** (공식 사이트와 문서 갱신 확인) | 중간 (B2B API 중심) | https://docs.originstamp.com/faq , https://originstamp.com/pricing |
| Proof of Existence | 미국(오픈 프로젝트) | 브라우저에서 해시를 만들어 비트코인 트랜잭션에 기록. 파일 미업로드 | 과거 건당 0.005 BTC 수준(현재 확인 불가) | **확인 불가** (사이트 제목만 응답. 운영 근거 없음) | 낮음 | https://github.com/proofofexistence/docs |
| OpenTimestamps | 오픈소스 | 무료 비트코인 타임스탬프 표준과 도구 | 무료 | 운영 중 (오픈소스) | 중간 (무료 대체재) | https://en.wikipedia.org/wiki/OpenTimestamps |
| 블로코 CCCV, 메타노니아 블록체인 TSA 등 | 한국 | 창작물·전자문서 블록체인 타임스탬프 | 확인 불가 | **확인 불가** (2019~2020 보도만 확인) | 중간 | https://www.ajunews.com/view/20201031124016101 |
| 행정안전부 GTSA (전자문서진본확인센터) | 한국 | 공공 전자문서 시점확인(TSA) | 공공 | 운영 중 | 낮음 (공공문서용) | https://smartcity.go.kr/wp-content/uploads/2023/10/KR29.전자증명서_발급_유통_시스템_Digital-Government-Certificate-Management-System.pdf |

### B. 아이디어 마켓플레이스 / 크라우드소싱 발명 플랫폼

| 서비스 | 국가 | 내용 | 비즈니스 모델·가격 | 현재 상태 | 중복도 | 출처 |
|---|---|---|---|---|---|---|
| Quirky | 미국 | 커뮤니티 발명 아이디어를 제품화하고 판매액 일부를 발명자에게 환원 | 직판 매출의 30%(2013.7 이후 10%), 리테일 매출의 10%를 커뮤니티에 환원. 2017 재출범 후 라이선스 중개 모델 | **2015.9 파산(Chapter 11).** 2017 라이선스 모델로 재출범. 2023~2025 운영 근거 없음(Dealroom은 비활성으로 표기). 현재 상태 확인 불가 | **높음** (성과 연동 환원 모델의 대표 실패 사례) | https://www.entrepreneur.com/business-news/how-a-quirky-28-year-old-plowed-through-150-million-and/245678 , https://www.axios.com/2017/12/15/the-rebirth-of-quirky-1513305743 , https://dealroom.co/companies/quirky/ |
| Edison Nation | 미국 | 발명 아이디어 접수, 심사, 라이선스, 로열티 배분 | 제출 수수료 $25~100. 발명자는 딜 로열티의 50% | **2020.11 Vinco Ventures로 사명 변경** 후 디지털 미디어 지주사로 전환. 발명 플랫폼의 현재 운영은 확인 불가. 2026.2 SEC가 전 경영진을 제소(PPE 관련) | 높음 (로열티 환원 구조) | https://www.inventorsdigest.com/articles/kicking-the-tires-of-edison-nation/ , https://www.tipranks.com/stocks/bbig/stock-analysis |
| Enventys Partners | 미국 | 제품 개발·런칭 대행(구 Edison Nation 계열). 발명가 대상 유료 서비스 | 서비스 수수료 | 운영 중으로 표기(CB Insights). 최신 활동 근거 2024.1 | 낮음 | https://www.cbinsights.com/company/enventys-partners |
| InnoCentive → Wazoku Crowd → Innocentive | 미국/영국 | 기업이 과제를 올리면 솔버가 해결안을 내고, 상금을 받고 IP를 이전 | 기업 대상 구독·과제 수수료. 솔버는 상금 | **운영 중.** 2020.7 Wazoku가 인수. 2022.8 Wazoku Crowd로 개명, 2025.6 Innocentive 명칭 복원 | 중간 (수요 주도형이고 IP를 일괄 이전. 성과 연동 없음) | https://en.wikipedia.org/wiki/InnoCentive |
| IdeaConnection | 캐나다 | 오픈 이노베이션 솔버 네트워크. 상금 기반 문제 해결과 IP 이전, 기술 스카우팅 | 기업 대상 서비스 수수료(세부 확인 불가) | 2020.5 Planbox가 인수. 이후 독립 운영 여부 확인 불가(사이트 403) | 중간 | https://www.newswire.com/news/planbox-acquires-ideaconnection-the-best-in-class-open-innovation-21142347 |
| 아이디어로 (idearo, 특허청·한국발명진흥회) | 한국 | 기업·공공기관 과제에 국민 아이디어를 제안하고 거래. 거래 규정, 표준계약서, 비밀유지협약 구비 | 기관이 보상금을 지급(최소·최대 보상금 제시). 2023년 누적 거래 509건, 2억 원 돌파 | **운영 중** (2021.3 개통. 현재 ipmarket.or.kr/idearo로 리다이렉트) | **높음** (국내 공공 아이디어 거래와 NDA. 다만 일회성 보상) | https://newsseoul.co.kr/news/view/1065589217110911 , https://www.ipmarket.or.kr/idearo/ |
| 아이디어오디션 (주식회사 아이디어오디션) | 한국 | 생활 아이디어를 크라우드로 발전시켜 제품화하고 판매수익을 배분(국내판 Quirky) | 판매 매출의 약 7%를 기여자 수익금으로 배분(2014 보도). 순수익 5~15%를 아이디어 제공자에게 배분한다는 보도도 있음 | 2012.8 설립. 일부 서비스 '종료' 표시. 현재 운영 여부 확인 불가 | **높음** (성과 연동 환원) | https://thevc.kr/ideaaudition , https://www.korea.kr/briefing/policyBriefingView.do?newsId=148766633 |
| 창조경제타운 | 한국(미래창조과학부) | 국민 아이디어 제안, 멘토링, 사업화 연계 | 무료 공공 플랫폼 | 2013~2015 운영 확인. 종료 시점 확인 불가(정권 교체 이후 사실상 중단된 것으로 보이나 공식 근거 미확인) | 중간 | https://www.korea.kr/news/policyNewsView.do?newsId=148768619 |

### C. 비특허 IP·기술 라이선스 마켓 (원창작자 환원 포함)

| 서비스 | 국가 | 내용 | 비즈니스 모델·가격 | 현재 상태 | 중복도 | 출처 |
|---|---|---|---|---|---|---|
| 국가기술은행 NTB (산업통상자원부, KIAT) | 한국 | AI·빅데이터 기반 기술거래 플랫폼. 기술 추천, 거래·평가 정보, 기술나눔 | 중개수수료 체계 확인 불가 | **운영 중** (2026 기술나눔 공고가 NTB로 접수) | 낮음~중간 (특허·공공기술 중심) | https://www.ntb.kr , https://kidd.co.kr/news/221369 |
| IP-Market (한국발명진흥회) | 한국 | 지식재산 거래와 IP 금융 통합 플랫폼 | 확인 불가 | 운영 중 | 중간 (특허 중심. 아이디어로와 연계) | https://www.ipmarket.or.kr/idearo/ |
| IPXI (Intellectual Property Exchange International) | 미국 | 특허 라이선스를 'Unit License Right'로 표준화해 거래소에서 판매 | 거래 수수료 | **2015 폐쇄** | 중간 (라이선스 표준화의 실패 사례) | https://www.iam-media.com/litigation/broken-system-encourages-bad-behaviours-ipxi-closes-down |
| Quirky 재출범(2017~)과 Edison Nation | 미국 | 발명 아이디어를 기업에 라이선스하고 발명자에게 로열티 배분 | 로열티 분배 | 위 B 표 참조 | 높음 | 위 B 표 참조 |
| IBTC (백서) | 한국 | 블록체인 기반 아이디어 등록, 평가, 거래, 지분화 구상 | 토큰·지분 구조(구상) | **실제 운영 확인 불가** (백서 단계) | 중간 | https://ibtc-whitepaper.gitbook.io/kor/abstract |

### D. A+B+C 결합 (존재 증명, 라이선스, 성과 연동 환원)

| 후보 | 결합 정도 | 판단 |
|---|---|---|
| Bernstein | A 강함. NDA·라이선스 활용 사례를 제시하지만 중개나 정산 기능은 확인 불가 | 증명 플랫폼일 뿐 마켓은 아님 |
| 아이디어로 | B 강함, 일부 C(계약·NDA). 증명 계층 없음. 일회성 보상 | 성과 연동 환원 없음 |
| Quirky, 아이디어오디션, Edison Nation | B+C(로열티 환원). 증명 계층 없음 | 다수가 실패·전환·상태 불명 |
| IBTC | A+B+C를 구상 | 운영 확인 불가 |
| USPTO 특허 US 7,043,454 | 암호 기술 기반 아이디어 제출, 구매, 라이선스 네트워크 | 선행 개념 존재. 권리 존속 여부는 확인 불가이므로 FTO 검토 필요 |

**판단:** 운영 중인 서비스 중 A+B+C 전체를 결합한 사례는 확인되지 않았습니다. 그중 TSA 기반 존재 증명, NDA 하의 열람 로그(부정경쟁방지법 증거), 에스크로 기반 성과 환원의 조합은 확인한 범위에서 유일합니다. (출처: https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7043454)

---

## 3. 실패·폐업 사례에서 배울 점

| 사례 | 원인 (출처 기반) | FirstPrint 시사점 |
|---|---|---|
| **Quirky (2015 파산)** | 연 50개 이상 제품을 내면서 초점이 사라짐. 자체 제조·유통으로 고비용. 리테일 채널에 마진 잠식. 매출의 10~30% 커뮤니티 환원을 마진이 감당하지 못함(발명자 지급 900만 달러 이상, 손실 1.5억 달러 이상). 수요 검증 부족 | 직접 사업화(제조)는 하지 말고 중개·증명·정산에만 머물 것. 환원율은 '매출'이 아니라 '라이선시의 이익·성과'에 연동하고 상한을 둘 것 |
| **Edison Nation** | 발명 플랫폼에서 상장 후 사업 다각화. 2020 Vinco Ventures로 전환하며 본업 이탈. 이후 경영진 SEC 제소 | 제출 수수료 수익 구조는 발명가 착취라는 비판을 받기 쉬움. 투명한 정산과 거버넌스가 신뢰의 핵심 |
| **WIPO PROOF (2022 발급 중단)** | 시장의 빠른 변화와 사업성 재평가(WIPO 공지) | 공적 기관조차 '타임스탬프 단독' 사업성을 인정하지 않음. 증명은 미끼 기능이고 수익은 다른 곳(거래·정산)에서 나와야 함. 또한 서비스가 종료돼도 증명이 독립 검증 가능해야 함(RFC 3161 표준 사용은 장점) |
| **IPXI (2015 폐쇄)** | 라이선스 표준화 상품이 실사용자 수요를 얻지 못함. 법무부 반독점 우려. CEO는 성실한 라이선스 협상을 유인하지 않는 특허제도를 원인으로 지목 | 라이선시(기업)가 '빌려야 할 이유'가 약하면 시장이 서지 않음. 수요 측 유인 설계가 공급(아이디어 축적)보다 먼저 |
| **창조경제타운** | 정책 주도 플랫폼으로, 운영 지속성이 정권·예산에 좌우된 것으로 보임(공식 종료 근거는 확인 불가) | 공공사업 연계는 초기 유입에는 좋지만 의존하면 위험 |

---

## 4. FirstPrint의 차별화 포인트와 위험

### 차별화 포인트
1. **내용 비전송(로컬 보관, 해시만 외부 전송)과 RFC 3161 TSA, 해시 체인 원장의 조합.** 블록체인 앵커링 위주인 Bernstein·OriginStamp와 달리 국제 표준 TSA를 쓰고, 검증 번들을 독립적으로 검증할 수 있습니다. 운영사가 사라져도 증명이 남는다는 점은 WIPO PROOF 사례에 대한 직접적인 답입니다.
2. **열람 로그를 증거로 남기는 구조.** 'NDA 하에서 누가 언제 어떤 아이디어를 봤는지'를 타임스탬프로 남겨, 부정경쟁방지법의 아이디어 탈취 조항(제2조 제1호 차목, 2018 신설) 입증 요건인 '거래 과정에서 제공받은 아이디어'에 맞춘 증거를 만듭니다. 조사한 경쟁사 중 이 기능을 명시한 곳은 없었습니다.
3. **성과 연동 환원(로열티, 이익배분, 지분)과 에스크로·신탁.** 아이디어로의 일회성 보상, InnoCentive의 상금과 IP 일괄 이전과 다르게 사업 성과를 장기적으로 나눕니다.
4. **'특허 불가·비실용' 영역(BM, 컨셉, 노하우)에 집중.** NTB와 IP-Market은 특허 중심이라 이 영역이 비어 있습니다.

### 위험
1. **MVP 단독 경쟁력 부족.** 영업비밀 원본증명은 공적 제도이고 아포스티유까지 지원하며, 민간 지정기관 3곳이 추가됐습니다. 해외 Bernstein이나 무료 OpenTimestamps도 있습니다. 법적 추정력 면에서 공적 원본증명보다 약할 수 있으므로 원본증명기관 지정 요건 검토나 제휴가 필요합니다.
2. **아이디어 단독 가치의 낮은 거래성.** 아이디어로의 누적 거래액은 약 2억 원(509건, 건당 평균 약 40만 원)입니다. 실행 없는 아이디어에 대한 기업의 지불 의사가 낮다는 신호입니다.
3. **성과 정산의 집행 난이도.** 라이선시의 매출·이익 보고에 의존하므로 감사권, 정산 분쟁, 우회 사업화(아이디어를 변형해 사용)를 막기 어렵습니다. 지분 환원은 자본시장법·증권성 이슈 검토가 필요합니다.
4. **에스크로·신탁 규제.** 자금을 보관하면 전자금융업, 신탁업 등 인허가 이슈가 생길 수 있으므로 외부 신탁사·에스크로 제휴가 필요합니다.
5. **기업 측의 오염(contamination) 우려.** 기업은 미요청 아이디어 열람으로 분쟁 위험을 지는 것을 꺼립니다(그래서 InnoCentive·아이디어로는 수요 주도형입니다). 열람 로그는 창작자에게는 장점이지만 기업에게는 진입 장벽이 됩니다.
6. **선행 특허(US 7,043,454 등) 관련 FTO 확인 필요.**
7. **공공 플랫폼(아이디어로)과의 정면 경쟁.** 무료이고 공공 신뢰도가 있습니다. 경쟁보다는 연계(증명 계층 공급)가 현실적일 수 있습니다.

---

## 5. 출처

- WIPO PROOF 종료 공지: https://www.wipo.int/en/web/wipo-proof/w/news/2021/news_0003
- 영업비밀 원본증명 칼럼(이투데이, 2025): https://www.etoday.co.kr/news/view/2450104
- 원본증명기관 추가 지정(이코노미스트, 2025.1): https://economist.co.kr/article/view/ecn202501200006
- 원본증명서 아포스티유(보안뉴스): https://m.boannews.com/html/detail.html?idx=139251
- Bernstein: https://www.bernstein.io
- OriginStamp FAQ·가격: https://docs.originstamp.com/faq , https://originstamp.com/pricing
- Proof of Existence: https://github.com/proofofexistence/docs
- OpenTimestamps: https://en.wikipedia.org/wiki/OpenTimestamps
- 국내 블록체인 TSA(아주경제, 2020): https://www.ajunews.com/view/20201031124016101
- Quirky 실패 분석: https://www.entrepreneur.com/business-news/how-a-quirky-28-year-old-plowed-through-150-million-and/245678 , https://d3.harvard.edu/platform-digit/submission/quirky-why-the-crowdsourcing-platform-failed-and-its-broader-learnings-for-the-open-innovation-movement/ , https://hn.jakechampion.name/reader/http://www.theverge.com/2015/4/24/8488531/quirky-invention-powered-by-quirky
- Quirky 재출범·현황: https://www.axios.com/2017/12/15/the-rebirth-of-quirky-1513305743 , https://dealroom.co/companies/quirky/
- Edison Nation: https://www.inventorsdigest.com/articles/kicking-the-tires-of-edison-nation/ , https://www.tipranks.com/stocks/bbig/stock-analysis
- Enventys Partners: https://www.cbinsights.com/company/enventys-partners
- InnoCentive/Wazoku: https://en.wikipedia.org/wiki/InnoCentive
- IdeaConnection 인수: https://www.newswire.com/news/planbox-acquires-ideaconnection-the-best-in-class-open-innovation-21142347
- 아이디어로 실적: https://newsseoul.co.kr/news/view/1065589217110911 , https://www.ipmarket.or.kr/idearo/
- 아이디어오디션: https://thevc.kr/ideaaudition , https://www.korea.kr/briefing/policyBriefingView.do?newsId=148766633
- 창조경제타운: https://www.korea.kr/news/policyNewsView.do?newsId=148768619
- 국가기술은행 NTB: https://www.ntb.kr , https://kidd.co.kr/news/221369
- IPXI 폐쇄: https://www.iam-media.com/litigation/broken-system-encourages-bad-behaviours-ipxi-closes-down
- IBTC 백서: https://ibtc-whitepaper.gitbook.io/kor/abstract
- USPTO US 7,043,454: https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7043454
