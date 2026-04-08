# 📊 수급 동향 대시보드 개발 명세서

> **작성일**: 2026-04-08
> **목적**: 기관/외인 수급 동향을 한눈에 보는 대시보드 페이지 추가
> **작업자**: Claude Code
> **원칙**: 기존 매매 로직에 영향 없는 독립 모듈. 하루 1회 API 호출로 데이터 축적.

---

## 1. 개요

### 1-1. 뭘 보고 싶은가

- **어떤 종목**에 기관/외인 수급이 들어오는지
- **어떤 섹터(업종)**에 돈이 몰리는지
- 최근 한 달간 수급 **추세** (연속 순매수일 등)

### 1-2. 데이터 소스

**국내기관_외국인 매매종목가집계 API** — 하루 1회 호출

```
TR_ID:  FHPTJ04400000
URL:    /uapi/domestic-stock/v1/quotations/foreign-institution-total
Method: GET
모의투자: 미지원 (실전만)
```

장중 가집계 데이터로, 최종 확정은 장 종료 후.
→ **매일 15:40에 1회 호출** (15:30 확정 + 여유 10분)

### 1-3. API 응답 핵심 필드

```
Output (배열):
  hts_kor_isnm        — 종목명
  mksc_shrn_iscd      — 종목코드 (6자리)
  ntby_qty            — 순매수 수량
  stck_prpr           — 현재가
  prdy_vrss           — 전일 대비
  prdy_ctrt           — 전일 대비율 (%)
  acml_vol            — 누적 거래량
  frgn_ntby_qty       — 외국인 순매수 수량
  orgn_ntby_qty       — 기관계 순매수 수량
  frgn_ntby_tr_pbmn   — 외국인 순매수 대금 (백만원)
  orgn_ntby_tr_pbmn   — 기관계 순매수 대금 (백만원)
```

### 1-4. API 파라미터

```python
params = {
    "FID_COND_MRKT_DIV_CODE": "V",        # 고정
    "FID_COND_SCR_DIV_CODE":  "16449",    # 고정
    "FID_INPUT_ISCD":         "0001",     # 0000:전체, 0001:코스피, 1001:코스닥
    "FID_DIV_CLS_CODE":       "1",        # 0:수량정렬, 1:금액정렬
    "FID_RANK_SORT_CLS_CODE": "0",        # 0:순매수상위
    "FID_ETC_CLS_CODE":       "0",        # 0:전체, 1:외국인, 2:기관계
}
```

**호출 계획**: 하루 **딱 2회** — 코스피 1회 + 코스닥 1회

| # | FID_INPUT_ISCD | FID_RANK_SORT_CLS_CODE | 의미 |
|---|---|---|---|
| 1 | 0001 (코스피) | 0 (순매수상위) | 코스피 TOP |
| 2 | 1001 (코스닥) | 0 (순매수상위) | 코스닥 TOP |

순매수 상위로 호출해도 응답의 `frgn_ntby_qty`, `orgn_ntby_qty` 필드가 음수로 올 수 있으므로 순매도 종목 데이터도 자연스럽게 포함됨. 순매도 상위를 별도 호출할 필요 없음.

→ 하루 총 **2회 API 호출**. KIS 계정 정지 리스크 제로.

> **⚠️ KIS API 과다 호출 주의**: 한국투자증권은 무한 연결 접속/종료 반복 또는 토큰 남용 시 IP 및 앱키를 일시 차단한다고 공지. 하루 2회는 전혀 문제없지만, 수동 트리거 남발은 자제할 것. 수동 수집 버튼에 **1일 1회 제한** 적용.

---

## 2. 섹터(업종) 매핑

### 2-1. 데이터 소스

상장법인목록 파일 (`상장법인목록.xls`, HTML 테이블 형식)에서 추출.

```python
# 필요한 컬럼만:
# 종목코드 → 업종
# 예: "005930" → "반도체 제조업"

import pandas as pd
df = pd.read_html("상장법인목록.xls")[0]
SECTOR_MAP = dict(zip(df["종목코드"].astype(str).str.zfill(6), df["업종"]))
```

### 2-2. 섹터 그룹핑 (대분류)

상장법인목록의 업종은 세분류(~150종)라 대시보드용으로 대분류 매핑 필요:

```python
SECTOR_GROUP = {
    "반도체 제조업":           "IT/반도체",
    "전자부품 제조업":         "IT/반도체",
    "통신 및 방송 장비 제조업": "IT/반도체",
    "자동차용 엔진 및 자동차 제조업": "자동차",
    "자동차 신품 부품 제조업":  "자동차",
    "기초 화학물질 제조업":    "화학",
    "의약품 제조업":           "바이오/제약",
    "의료용 기기 제조업":      "바이오/제약",
    "은행 및 저축기관":        "금융",
    "기타 금융업":             "금융",
    "금융 지원 서비스업":      "금융",
    "건물 건설업":             "건설",
    "철강 압연 및 가공업":     "철강/소재",
    "1차 철강 제조업":         "철강/소재",
    "전기업":                  "에너지/유틸리티",
    # ... 나머지는 "기타"로 fallback
}

def get_sector_group(sector_name: str) -> str:
    return SECTOR_GROUP.get(sector_name, "기타")
```

**⚠️ 매핑 테이블 완성**: 실제 구현 시 상장법인목록의 고유 업종 목록을 추출하고, 10~15개 대분류로 매핑. 수동으로 전부 매핑하기 어려우면 키워드 기반 자동 분류 + 수동 보정.

---

## 3. 데이터 저장

### 3-1. DB 테이블

기존 봇의 DB(SQLite 또는 PostgreSQL)에 테이블 추가:

```sql
CREATE TABLE IF NOT EXISTS supply_demand_daily (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    collected_at    TEXT NOT NULL,          -- 수집 시각 (ISO format)
    biz_date        TEXT NOT NULL,          -- 영업일 (YYYYMMDD)
    market          TEXT NOT NULL,          -- "KOSPI" / "KOSDAQ"
    ticker          TEXT NOT NULL,          -- 종목코드 (6자리)
    name            TEXT NOT NULL,          -- 종목명
    sector          TEXT,                   -- 업종 (상장법인목록 기준)
    sector_group    TEXT,                   -- 대분류 섹터
    price           INTEGER,               -- 현재가
    price_change_pct REAL,                 -- 전일 대비율 (%)
    frgn_net_qty    INTEGER DEFAULT 0,     -- 외국인 순매수 수량
    orgn_net_qty    INTEGER DEFAULT 0,     -- 기관 순매수 수량
    frgn_net_amt    INTEGER DEFAULT 0,     -- 외국인 순매수 대금 (백만원)
    orgn_net_amt    INTEGER DEFAULT 0,     -- 기관 순매수 대금 (백만원)
    acml_vol        INTEGER DEFAULT 0,     -- 누적 거래량
    
    UNIQUE(biz_date, ticker)               -- 같은 날 같은 종목 중복 방지
);

CREATE INDEX IF NOT EXISTS idx_sd_date ON supply_demand_daily(biz_date);
CREATE INDEX IF NOT EXISTS idx_sd_ticker ON supply_demand_daily(ticker);
CREATE INDEX IF NOT EXISTS idx_sd_sector ON supply_demand_daily(sector_group);
```

### 3-2. 데이터 크기 추정

- 하루 4회 호출 × 각 ~50종목 = 최대 200행/일 (중복 제거 후 ~100~150행)
- 한 달 ≈ 22영업일 × 150 = ~3,300행
- 1년 ≈ ~40,000행 → SQLite로 충분

---

## 4. 수집 모듈 (`supply_demand_collector.py`)

### 4-1. API 호출 함수

```python
def fetch_institution_foreign_top(
    market_code: str = "0001",   # 0001:코스피, 1001:코스닥
    sort_code: str = "0",        # 0:순매수상위, 1:순매도상위
    cls_code: str = "0",         # 0:전체, 1:외국인, 2:기관계
) -> list[dict]:
    """국내기관_외국인 매매종목가집계 API 호출.
    
    TR_ID: FHPTJ04400000
    """
    tr_id = "FHPTJ04400000"
    url = f"{config.KIS_BASE_URL}/uapi/domestic-stock/v1/quotations/foreign-institution-total"
    
    params = {
        "FID_COND_MRKT_DIV_CODE": "V",
        "FID_COND_SCR_DIV_CODE":  "16449",
        "FID_INPUT_ISCD":         market_code,
        "FID_DIV_CLS_CODE":       "1",           # 금액정렬
        "FID_RANK_SORT_CLS_CODE": sort_code,
        "FID_ETC_CLS_CODE":       cls_code,
    }
    
    try:
        resp = _get_session().get(
            url, headers=_common_headers(tr_id), params=params, timeout=10
        )
        data = resp.json()
    except Exception as e:
        logger.error("수급 가집계 API 실패: %s", e)
        return []
    
    if data.get("rt_cd") != "0":
        logger.error("수급 가집계 API 에러: %s %s", data.get("msg_cd"), data.get("msg1"))
        return []
    
    return data.get("output", [])
```

### 4-2. 일일 수집 함수

```python
def collect_daily_supply_demand():
    """하루 수급 데이터 수집 — 15:40에 스케줄 실행."""
    
    biz_date = datetime.now().strftime("%Y%m%d")
    market_map = {"0001": "KOSPI", "1001": "KOSDAQ"}
    
    all_records = []
    
    for market_code, market_name in market_map.items():
        results = fetch_institution_foreign_top(
            market_code=market_code,
            sort_code="0",   # 순매수상위 1회만 — 음수 데이터도 포함됨
        )
        
        for item in results:
            ticker = item.get("mksc_shrn_iscd", "")
            if not ticker:
                continue
            
            record = {
                "biz_date":         biz_date,
                "market":           market_name,
                "ticker":           ticker,
                "name":             item.get("hts_kor_isnm", ""),
                "sector":           SECTOR_MAP.get(ticker, ""),
                "sector_group":     get_sector_group(SECTOR_MAP.get(ticker, "")),
                "price":            _safe_int(item.get("stck_prpr")),
                "price_change_pct": _safe_float(item.get("prdy_ctrt")),
                "frgn_net_qty":     _safe_int(item.get("frgn_ntby_qty")),
                "orgn_net_qty":     _safe_int(item.get("orgn_ntby_qty")),
                "frgn_net_amt":     _safe_int(item.get("frgn_ntby_tr_pbmn")),
                "orgn_net_amt":     _safe_int(item.get("orgn_ntby_tr_pbmn")),
                "acml_vol":         _safe_int(item.get("acml_vol")),
            }
            all_records.append(record)
        
        time.sleep(1.0)  # API 호출 간격 — 넉넉하게 1초
    
    # DB 저장 (UPSERT — 같은 날 같은 종목이면 업데이트)
    saved = _save_records(all_records)
    logger.info("[수급 수집] %s — %d건 저장 완료", biz_date, saved)
    return saved
```

### 4-3. 스케줄러

```python
# 기존 봇의 스케줄러에 추가 (APScheduler 또는 threading.Timer)

def schedule_supply_demand():
    """평일 15:40에 수급 데이터 수집."""
    scheduler.add_job(
        collect_daily_supply_demand,
        trigger="cron",
        day_of_week="mon-fri",
        hour=15, minute=40,
        id="supply_demand_daily",
        replace_existing=True,
    )
```

**참고**: 스케줄러가 없으면 간단히 threading 기반 타이머로 구현해도 됨.

---

## 5. API 엔드포인트

### 5-1. 수급 데이터 조회

```python
@app.route("/api/supply-demand", methods=["GET"])
def api_supply_demand():
    """수급 동향 데이터 조회.
    
    Query params:
        days:     조회 기간 (기본 20 = 약 한 달)
        market:   KOSPI / KOSDAQ / all (기본 all)
        investor: foreign / institution / all (기본 all)
        top:      상위 N개 (기본 30)
    """
    days = request.args.get("days", 20, type=int)
    market = request.args.get("market", "all")
    investor = request.args.get("investor", "all")
    top_n = request.args.get("top", 30, type=int)
    
    # --- 1. 종목별 누적 순매수 ---
    stock_summary = _query_stock_summary(days, market)
    # 외인/기관 누적 순매수 대금 기준 정렬
    
    # --- 2. 섹터별 누적 순매수 ---
    sector_summary = _query_sector_summary(days, market)
    
    return jsonify({
        "period_days": days,
        "market": market,
        "summary": _query_summary(days, market),
        "stock_top_buy": stock_summary["top_buy"][:top_n],
        "stock_top_sell": stock_summary["top_sell"][:top_n],
        "sector_summary": sector_summary,
        "sector_rotation": detect_sector_rotation(days),
        "consecutive_buy": detect_consecutive_buying(days),
        "flow_reversals": detect_flow_reversal(days),
        "investor_alignment": detect_investor_alignment(min(days, 5)),
        "last_updated": _get_last_collection_date(),
        "total_records": _get_total_record_count(),
        "data_days": _get_collected_day_count(),
    })
```

### 5-2. 쿼리 함수 예시

```python
def _query_stock_summary(days: int, market: str) -> dict:
    """종목별 기간 누적 순매수 대금."""
    
    cutoff = (datetime.now() - timedelta(days=days * 1.5)).strftime("%Y%m%d")
    # days * 1.5 → 영업일 보정 (주말/공휴일)
    
    query = """
        SELECT 
            ticker, name, sector_group, market,
            SUM(frgn_net_amt) as total_frgn_amt,
            SUM(orgn_net_amt) as total_orgn_amt,
            SUM(frgn_net_amt) + SUM(orgn_net_amt) as total_net_amt,
            COUNT(*) as appear_days,
            AVG(price_change_pct) as avg_change_pct
        FROM supply_demand_daily
        WHERE biz_date >= ?
    """
    params = [cutoff]
    
    if market != "all":
        query += " AND market = ?"
        params.append(market)
    
    query += """
        GROUP BY ticker
        ORDER BY total_net_amt DESC
    """
    
    results = db.execute(query, params).fetchall()
    
    top_buy = [r for r in results if r["total_net_amt"] > 0]
    top_sell = sorted(
        [r for r in results if r["total_net_amt"] < 0],
        key=lambda x: x["total_net_amt"]
    )
    
    return {"top_buy": top_buy, "top_sell": top_sell}


def _query_sector_summary(days: int, market: str) -> list:
    """섹터별 기간 누적 순매수 대금."""
    
    cutoff = (datetime.now() - timedelta(days=days * 1.5)).strftime("%Y%m%d")
    
    query = """
        SELECT 
            sector_group,
            SUM(frgn_net_amt) as total_frgn_amt,
            SUM(orgn_net_amt) as total_orgn_amt,
            SUM(frgn_net_amt) + SUM(orgn_net_amt) as total_net_amt,
            COUNT(DISTINCT ticker) as stock_count
        FROM supply_demand_daily
        WHERE biz_date >= ? AND sector_group IS NOT NULL AND sector_group != ''
    """
    params = [cutoff]
    
    if market != "all":
        query += " AND market = ?"
        params.append(market)
    
    query += " GROUP BY sector_group ORDER BY total_net_amt DESC"
    
    return db.execute(query, params).fetchall()

# 참고: 연속 순매수, 섹터 로테이션, 수급 전환 등 패턴 감지 함수는 섹션 6에 정의
```

### 5-3. 수동 수집 트리거 (1일 1회 제한)

```python
_last_manual_collect = None

@app.route("/api/supply-demand/collect", methods=["POST"])
def api_supply_demand_collect():
    """수동으로 수급 데이터 수집 트리거. 1일 1회 제한."""
    global _last_manual_collect
    
    now = datetime.now()
    if _last_manual_collect and (now - _last_manual_collect).total_seconds() < 86400:
        remaining = 86400 - (now - _last_manual_collect).total_seconds()
        hours = int(remaining // 3600)
        return jsonify({"status": "rate_limited", 
                        "message": f"1일 1회 제한. {hours}시간 후 가능"}), 429
    
    saved = collect_daily_supply_demand()
    _last_manual_collect = now
    return jsonify({"status": "ok", "saved": saved})
```

---

## 6. 패턴 자동 감지 엔진

### 6-1. 연속 순매수 감지

DB에 쌓인 일별 데이터에서 **종목별 연속 순매수일**을 자동 계산.

```python
def detect_consecutive_buying(days: int = 20) -> list[dict]:
    """외인+기관 합산 연속 순매수일 감지.
    
    Returns: [
        {
            "ticker": "005930", "name": "삼성전자",
            "sector_group": "IT/반도체", "market": "KOSPI",
            "streak_days": 8,
            "total_net_amt": 4567,  # 억원
            "streak_start": "20260325",
            "avg_daily_amt": 571,   # 억원/일
            "investor": "both",     # "foreign" / "institution" / "both"
        },
        ...
    ]
    """
    # 최근 → 과거 순으로 날짜 탐색하며 연속 양수인 날 카운트
    # streak_days >= 3 인 것만 반환
    # "both": 외인+기관 동시 순매수, "foreign": 외인만, "institution": 기관만
```

**감지 기준**:
- `frgn_net_amt + orgn_net_amt > 0` → 합산 순매수일
- 연속 3일 이상만 표시
- "쌍끌이" 라벨: 외인+기관 동시 순매수 5일 이상 → 🔥 표시

### 6-2. 섹터 로테이션 감지

일별 섹터 수급 데이터에서 **최근 5일 vs 이전 5일** 비교로 자금 이동 방향 감지.

```python
def detect_sector_rotation(days: int = 20) -> dict:
    """섹터 로테이션 감지 — 최근 vs 이전 구간 비교.
    
    Returns: {
        "rotating_in": [        # 자금 유입 가속 섹터
            {"sector": "IT/반도체", "recent_amt": 3400, "prev_amt": 1200, 
             "change_pct": +183.3, "label": "🔺 유입 가속"},
        ],
        "rotating_out": [       # 자금 유출 전환 섹터
            {"sector": "금융", "recent_amt": -800, "prev_amt": 500,
             "change_pct": -260.0, "label": "🔻 유출 전환"},
        ],
        "steady_in": [          # 꾸준히 유입 중
            {"sector": "바이오/제약", "recent_amt": 900, "prev_amt": 850,
             "change_pct": +5.9, "label": "➡️ 유입 유지"},
        ],
    }
    """
    # 로직:
    # 1. 최근 5영업일 섹터별 합산 순매수 (recent)
    # 2. 그 이전 5영업일 섹터별 합산 순매수 (prev)
    # 3. 변화율 계산: (recent - prev) / abs(prev) * 100
    # 4. 분류:
    #    - recent > 0 AND change_pct > +50% → "유입 가속"
    #    - recent < 0 AND prev > 0           → "유출 전환" 
    #    - recent > 0 AND change_pct < -50%  → "유입 둔화"
    #    - recent > 0 AND |change_pct| <= 50 → "유입 유지"
    #    - recent < 0 AND prev < 0           → "유출 지속"
```

### 6-3. 수급 전환 신호 감지

개별 종목에서 외인/기관이 **매도→매수로 전환**하는 포인트 감지.

```python
def detect_flow_reversal(days: int = 20) -> list[dict]:
    """수급 전환 종목 감지 — 최근 3일 순매수 전환.
    
    조건: 이전 5일 중 4일 이상 순매도 → 최근 3일 연속 순매수
    
    Returns: [
        {
            "ticker": "035720", "name": "카카오",
            "sector_group": "IT/반도체",
            "prev_5d_amt": -230,       # 이전 5일 합산 (억원)
            "recent_3d_amt": +180,     # 최근 3일 합산 (억원)
            "reversal_type": "foreign", # 누가 전환했는가
            "label": "🔄 외인 매수 전환",
        },
    ]
    """
```

### 6-4. 외인-기관 동조/엇갈림 감지

```python
def detect_investor_alignment(days: int = 5) -> list[dict]:
    """외인과 기관이 같은 방향인지, 엇갈리는지 감지.
    
    Returns: [
        {
            "ticker": "005930", "name": "삼성전자",
            "frgn_5d_amt": +1200,
            "orgn_5d_amt": +890,
            "alignment": "쌍끌이 매수",  # 동시 순매수
            "label": "🔥",
        },
        {
            "ticker": "035420", "name": "NAVER",
            "frgn_5d_amt": +500,
            "orgn_5d_amt": -300,
            "alignment": "외인↑ 기관↓",  # 엇갈림
            "label": "⚡",
        },
    ]
    """
```

---

## 7. 대시보드 UI

### 7-1. 페이지 전체 레이아웃

```
┌─────────────────────────────────────────────────────────┐
│  📊 수급 동향 대시보드                                     │
│  [5일] [10일] [20일]     [코스피] [코스닥] [전체]          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ❶ 오늘의 수급 요약 카드 (3개)                             │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐       │
│  │ 외인 순매수   │ │ 기관 순매수   │ │ 쌍끌이 종목   │       │
│  │ +2,340억     │ │ +1,560억     │ │ 12개         │       │
│  │ ▲ 어제 대비 ↑│ │ ▼ 어제 대비 ↓│ │ ▲ +3개      │       │
│  └─────────────┘ └─────────────┘ └─────────────┘       │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ❷ 섹터 수급 히트맵                                       │
│  ┌─────────────────────────────────────────────────┐   │
│  │  IT/반도체  ████████████████  +3,400억 🔺유입가속  │   │
│  │  바이오     ████████         +1,200억 ➡️유입유지  │   │
│  │  자동차     ██████           +780억  🔺유입가속   │   │
│  │  에너지     ██               +120억  🆕유입전환   │   │
│  │  ─────── 경계선 ───────                          │   │
│  │  금융       ████             -560억  🔻유출전환   │   │
│  │  건설       ██████████       -1,800억 ⬇️유출지속  │   │
│  └─────────────────────────────────────────────────┘   │
│  ※ 막대 색상: 파랑(유입) ↔ 빨강(유출)                     │
│  ※ 오른쪽 라벨: 전주 대비 변화 (섹터 로테이션 감지 결과)     │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ❸ 🔥 연속 순매수 종목 (streak ≥ 3일)                     │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 종목       섹터      연속  누적금액  투자자  강도   │   │
│  │ SK하이닉스  IT/반도체  12일  +4,567억  🔥쌍끌이 ████│   │
│  │ 삼성전자   IT/반도체   8일  +2,345억  🔥쌍끌이 ███ │   │
│  │ 셀트리온   바이오      6일  +890억   👤외인    ██  │   │
│  │ 현대차     자동차      5일  +670억   🏛기관    ██  │   │
│  │ 카카오     IT         3일  +230억   🔄전환    █   │   │
│  └─────────────────────────────────────────────────┘   │
│  ※ 강도 바: 일평균 순매수 금액 기준                        │
│  ※ 🔥쌍끌이: 외인+기관 동시 순매수 5일+                    │
│  ※ 🔄전환: 직전 매도에서 매수 전환된 종목                   │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ❹ 수급 전환 신호 (최근 감지)                              │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 🔄 카카오 — 외인 매수 전환                         │   │
│  │   이전 5일: -230억(순매도) → 최근 3일: +180억       │   │
│  │   ▓▓▓▓▓░░░░░░░████ (빨강→파랑 타임라인)           │   │
│  │                                                   │   │
│  │ 🔄 삼성SDI — 기관 매수 전환                        │   │
│  │   이전 5일: -450억 → 최근 3일: +320억               │   │
│  │   ▓▓▓▓▓░░░░████ (빨강→파랑)                       │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ❺ 외인 TOP 10 / 기관 TOP 10 (탭 전환)                   │
│  ┌──────────────────────┬──────────────────────────┐   │
│  │ [외인 순매수]  [기관]  │  종목   금액   수량  등락  │   │
│  │                      │  삼성전자 +1,234억 ... +1.2%│   │
│  │                      │  SK하이  +567억  ... +2.3% │   │
│  │                      │  ...                       │   │
│  └──────────────────────┴──────────────────────────┘   │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  📅 데이터: 2026-04-08 ~ 2026-04-08 (1일)               │
│  마지막 수집: 15:40 | 총 레코드: 98건 | [🔄 수동 수집]     │
└─────────────────────────────────────────────────────────┘
```

### 7-2. 각 섹션 상세

#### ❶ 요약 카드 (3개)

| 카드 | 메인 수치 | 서브 수치 |
|------|----------|----------|
| 외인 순매수 | 선택 기간 합산 (억원) | 전일/전주 대비 변화 |
| 기관 순매수 | 선택 기간 합산 (억원) | 전일/전주 대비 변화 |
| 쌍끌이 종목 수 | 외인+기관 동시 순매수 종목 | 전일 대비 증감 |

```python
# API 응답 예시
{
    "summary": {
        "foreign_total_amt":     2340,    # 억원
        "foreign_prev_amt":      1890,    # 이전 동일 기간
        "institution_total_amt": 1560,
        "institution_prev_amt":  1780,
        "dual_buy_count":        12,
        "dual_buy_prev_count":   9,
    }
}
```

#### ❷ 섹터 히트맵

- 가로 막대 차트: 양수(파랑) ↔ 음수(빨강)
- 막대 오른쪽에 **섹터 로테이션 라벨** 자동 표시 (6-2 감지 결과)
- 라벨 종류: 🔺유입가속 / ➡️유입유지 / 🔻유출전환 / ⬇️유출지속 / 🆕유입전환 / 📉유입둔화
- 기간 전환(5일/10일/20일) 시 차트 + 라벨 모두 재계산

#### ❸ 연속 순매수 테이블

- streak_days 내림차순 정렬
- "강도" 컬럼: 일평균 순매수 금액을 미니 바로 시각화
- 투자자 컬럼: 🔥쌍끌이 / 👤외인 / 🏛기관 / 🔄전환
- 행 클릭 시 해당 종목의 일별 수급 미니 차트 expand

#### ❹ 수급 전환 신호

- 카드 형태로 최근 감지된 전환 종목 표시
- 미니 타임라인 바: 최근 10영업일의 일별 순매수를 빨강/파랑 셀로 시각화
- 전환 직후(3일 이내)만 표시 → 오래되면 자동 숨김

#### ❺ TOP 10 테이블

- 외인/기관 탭 전환
- 순매수 금액, 수량, 등락률 표시
- 기간(5/10/20일) 합산 기준

### 7-3. 데이터 부족 시 (수집 초기)

수집 시작 후 데이터가 부족할 때 빈 차트 대신 안내 메시지:

```
📊 데이터 수집 중입니다
현재 3일치 데이터가 쌓였습니다.
• 연속 순매수 감지: 3일 이상 필요 ✅ 가능
• 섹터 로테이션: 10일 이상 필요 ⏳ 7일 후
• 수급 전환 신호: 8일 이상 필요 ⏳ 5일 후
```

각 패턴별 필요 최소 데이터 일수:
- 연속 순매수: **3일** (최소 기능 동작)
- 섹터 로테이션: **10일** (5일 vs 5일 비교)
- 수급 전환: **8일** (5일 매도 + 3일 매수)
- 외인-기관 동조: **5일**

---

## 8. config.py 파라미터

```python
# ---------------------------------------------------------------------------
# 수급 동향 대시보드
# ---------------------------------------------------------------------------
SUPPLY_DEMAND_ENABLED = os.getenv("SUPPLY_DEMAND_ENABLED", "true").lower() == "true"
SUPPLY_DEMAND_COLLECT_HOUR = _int_env("SUPPLY_DEMAND_COLLECT_HOUR", 15)
SUPPLY_DEMAND_COLLECT_MINUTE = _int_env("SUPPLY_DEMAND_COLLECT_MINUTE", 40)
```

→ Settings UI 추가 불필요 (ON/OFF 정도면 환경변수로 충분).

---

## 9. 파일 구조

```
project/
├── supply_demand_collector.py    # API 호출 + DB 저장 모듈
├── templates/
│   └── supply_demand.html        # 대시보드 UI
├── webhook_server.py             # 기존 — 라우트 추가만
└── sector_map.json               # 업종 → 대분류 매핑 (별도 파일)
```

---

## 10. 구현 순서

```
Step 1: 상장법인목록에서 종목코드→업종 매핑 로드 + 대분류 매핑 생성
Step 2: supply_demand_daily 테이블 생성
Step 3: supply_demand_collector.py — API 호출(하루 2회) + DB 저장
Step 4: 패턴 감지 함수 구현 (연속 순매수, 섹터 로테이션, 수급 전환, 동조/엇갈림)
Step 5: /api/supply-demand 엔드포인트 (패턴 데이터 포함)
Step 6: /api/supply-demand/collect 수동 트리거 (1일 1회 제한)
Step 7: supply_demand.html 대시보드 페이지 (5개 섹션 UI)
Step 8: 스케줄러 등록 (15:40 자동 수집)
Step 9: 기존 nav에 "수급" 탭 링크 추가
```

---

## 11. 주의사항

1. **모의투자 미지원**: 가집계 API는 실전만 가능. 우리는 실전만 쓰므로 문제없음.
2. **데이터 축적 필요**: 방법 A라서 처음엔 데이터가 1일치뿐. 패턴별 필요 일수: 연속순매수 3일, 섹터로테이션 10일, 수급전환 8일.
3. **업종 매핑 유지보수**: 신규 상장/상폐 시 상장법인목록 갱신 필요. 분기 1회 정도.
4. **API 호출 최소화**: 하루 딱 2회 (코스피+코스닥). 수동 수집도 1일 1회 제한. KIS 계정 정지 리스크 없음.
5. **기존 봇 영향 없음**: 별도 테이블, 별도 모듈, 별도 스케줄. 매매 로직과 완전 분리.
6. **금액 단위 변환**: API 응답은 백만원 → 대시보드는 억원(÷100)으로 표시.
