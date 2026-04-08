# korena-sugup

한국 주식시장의 **기관/외인 수급 동향**을 한눈에 보는 대시보드.

한국투자증권(KIS) OpenAPI의 「국내기관_외국인 매매종목가집계」 API를 하루 2회 호출해
데이터를 축적하고, 섹터 로테이션 · 연속 순매수 · 수급 전환 등 패턴을 자동 감지합니다.

전체 기획은 [`SUPPLY_DEMAND_DASHBOARD_SPEC.md`](SUPPLY_DEMAND_DASHBOARD_SPEC.md) 참조.

## 주요 기능

- **일일 자동 수집** (평일 15:40) — KIS API 하루 2회 호출 (코스피 + 코스닥)
- **섹터 수급 히트맵** — 대분류 섹터별 누적 순매수 가시화
- **연속 순매수 감지** — streak ≥ 3일, 쌍끌이 자동 분류
- **섹터 로테이션** — 최근 5일 vs 이전 5일 비교
- **수급 전환 신호** — 매도→매수 전환 종목 감지
- **외인/기관 동조·엇갈림** — 쌍끌이 매수/매도 및 엇갈림 케이스

## 빠른 시작

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정

`.env.example`를 복사해 `.env`를 만들고 KIS API 키를 채우세요.

```bash
cp .env.example .env
# .env 파일 편집
```

필수:

```env
KIS_APP_KEY=your_app_key
KIS_APP_SECRET=your_app_secret
KIS_BASE_URL=https://openapi.koreainvestment.com:9443
```

> 경고: KIS 가집계 API는 **실전 계정만 지원**합니다. 모의투자에서는 동작하지 않습니다.

### 3. 상장법인목록 배치 (선택)

섹터(업종) 매핑을 위해 KIND에서 `상장법인목록.xls`를 다운받아
`data/` 디렉토리에 넣어두세요. 파일이 없으면 `app/sector_map.json`의
샘플 데이터(대표 종목 ~30개)로 동작합니다.

```
data/상장법인목록.xls
```

### 4. 실행

```bash
# 서버 실행 (스케줄러 포함)
python run.py

# 수동 수집 1회 (테스트용, 서버 없이)
python run.py --collect
```

서버는 기본 `http://0.0.0.0:5000`에서 동작합니다.

- `/` — 홈
- `/supply-demand` — 수급 동향 대시보드
- `/api/supply-demand` — 데이터 JSON
- `/api/supply-demand/collect` (POST) — 수동 수집 (1일 1회 제한)
- `/api/health` — 헬스 체크

## 프로젝트 구조

```
korena-sugup/
├── run.py                         # 엔트리 포인트
├── requirements.txt
├── .env.example
├── app/
│   ├── config.py                  # 환경변수 로딩
│   ├── database.py                # SQLite + 테이블 스키마
│   ├── kis_client.py              # KIS API 세션/토큰
│   ├── supply_demand_collector.py # API 호출 + DB 저장
│   ├── patterns.py                # 패턴 감지 엔진
│   ├── sectors.py                 # 종목코드 → 업종 매핑
│   ├── sector_map.json            # 업종 대분류 매핑
│   ├── scheduler.py               # APScheduler
│   └── webhook_server.py          # Flask 앱 + API
├── templates/
│   ├── base.html
│   ├── index.html
│   └── supply_demand.html         # 대시보드 UI
├── static/
│   ├── css/dashboard.css
│   └── js/dashboard.js
└── data/
    ├── korena.db                  # SQLite (자동 생성)
    └── 상장법인목록.xls              # 사용자가 배치
```

## 수집 스케줄 & API 호출 제한

- 자동 수집: **평일 15:40** (장 마감 + 10분 여유)
- API 호출: 하루 **딱 2회** (KOSPI 1회 + KOSDAQ 1회)
- 수동 수집 버튼도 **1일 1회 제한**

> 경고: KIS는 과도한 토큰 발급/재접속 시 IP·앱키를 일시 차단할 수 있으니
> 수동 트리거 남발은 자제하세요.

## 데이터 축적 기간

처음 실행 시에는 데이터가 당일분밖에 없으므로 일부 패턴은 동작하지 않습니다.

| 패턴 | 최소 필요 일수 |
|---|---|
| 연속 순매수 | 3일 |
| 외인-기관 동조 | 5일 |
| 수급 전환 신호 | 8일 |
| 섹터 로테이션 | 10일 |
