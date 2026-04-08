"""수급 패턴 자동 감지 엔진.

- 연속 순매수 감지 (streak)
- 섹터 로테이션 감지
- 수급 전환 신호 감지
- 외인-기관 동조/엇갈림 감지

모든 함수는 supply_demand_daily 테이블을 소스로 사용.
금액 단위: API 응답은 백만원 → 반환 시 억원(÷100)으로 변환.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta

from . import database

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------
def _mil_to_eok(amount_mil: int | float | None) -> float:
    """백만원 → 억원 (÷100, 소수 1자리)."""
    if amount_mil is None:
        return 0.0
    return round(float(amount_mil) / 100.0, 1)


def _cutoff_biz_date(days: int) -> str:
    """days 영업일을 커버하는 cutoff (주말/공휴일 여유로 1.5배)."""
    cutoff = datetime.now() - timedelta(days=int(days * 1.5) + 1)
    return cutoff.strftime("%Y%m%d")


def _get_distinct_biz_dates(market: str = "all") -> list[str]:
    """저장된 biz_date를 최신순으로 반환."""
    with database.get_conn() as conn:
        q = "SELECT DISTINCT biz_date FROM supply_demand_daily"
        params: list = []
        if market != "all":
            q += " WHERE market = ?"
            params.append(market)
        q += " ORDER BY biz_date DESC"
        rows = conn.execute(q, params).fetchall()
        return [r["biz_date"] for r in rows]


# ---------------------------------------------------------------------------
# 종목별 요약 / 섹터 요약
# ---------------------------------------------------------------------------
def query_stock_summary(days: int = 20, market: str = "all") -> dict[str, list[dict]]:
    """종목별 기간 누적 순매수 대금 — top_buy / top_sell 분리."""
    cutoff = _cutoff_biz_date(days)

    q = """
        SELECT
            ticker, name, sector_group, market,
            SUM(frgn_net_amt) AS total_frgn_amt,
            SUM(orgn_net_amt) AS total_orgn_amt,
            SUM(frgn_net_amt) + SUM(orgn_net_amt) AS total_net_amt,
            COUNT(*) AS appear_days,
            AVG(price_change_pct) AS avg_change_pct,
            MAX(price) AS last_price
        FROM supply_demand_daily
        WHERE biz_date >= ?
    """
    params: list = [cutoff]
    if market != "all":
        q += " AND market = ?"
        params.append(market)
    q += " GROUP BY ticker ORDER BY total_net_amt DESC"

    with database.get_conn() as conn:
        rows = conn.execute(q, params).fetchall()

    records = []
    for r in rows:
        records.append({
            "ticker": r["ticker"],
            "name": r["name"],
            "sector_group": r["sector_group"] or "기타",
            "market": r["market"],
            "total_frgn_amt": _mil_to_eok(r["total_frgn_amt"]),
            "total_orgn_amt": _mil_to_eok(r["total_orgn_amt"]),
            "total_net_amt": _mil_to_eok(r["total_net_amt"]),
            "appear_days": r["appear_days"],
            "avg_change_pct": round(r["avg_change_pct"] or 0, 2),
            "last_price": r["last_price"] or 0,
        })

    top_buy = [r for r in records if r["total_net_amt"] > 0]
    top_sell = sorted(
        [r for r in records if r["total_net_amt"] < 0],
        key=lambda x: x["total_net_amt"],
    )
    return {"top_buy": top_buy, "top_sell": top_sell}


def query_sector_summary(days: int = 20, market: str = "all") -> list[dict]:
    """섹터별 기간 누적 순매수 대금."""
    cutoff = _cutoff_biz_date(days)

    q = """
        SELECT
            sector_group,
            SUM(frgn_net_amt) AS total_frgn_amt,
            SUM(orgn_net_amt) AS total_orgn_amt,
            SUM(frgn_net_amt) + SUM(orgn_net_amt) AS total_net_amt,
            COUNT(DISTINCT ticker) AS stock_count
        FROM supply_demand_daily
        WHERE biz_date >= ? AND sector_group IS NOT NULL AND sector_group != ''
    """
    params: list = [cutoff]
    if market != "all":
        q += " AND market = ?"
        params.append(market)
    q += " GROUP BY sector_group ORDER BY total_net_amt DESC"

    with database.get_conn() as conn:
        rows = conn.execute(q, params).fetchall()

    return [
        {
            "sector_group": r["sector_group"],
            "total_frgn_amt": _mil_to_eok(r["total_frgn_amt"]),
            "total_orgn_amt": _mil_to_eok(r["total_orgn_amt"]),
            "total_net_amt": _mil_to_eok(r["total_net_amt"]),
            "stock_count": r["stock_count"],
        }
        for r in rows
    ]


def query_summary(days: int = 20, market: str = "all") -> dict:
    """요약 카드용 수치 — 외인/기관 총 순매수, 쌍끌이 개수, 이전 기간 대비."""
    cutoff = _cutoff_biz_date(days)
    prev_cutoff = (
        datetime.now() - timedelta(days=int(days * 3))
    ).strftime("%Y%m%d")

    with database.get_conn() as conn:
        mkt_clause = ""
        params_cur: list = [cutoff]
        params_prev: list = [prev_cutoff, cutoff]
        if market != "all":
            mkt_clause = " AND market = ?"
            params_cur.append(market)
            params_prev.append(market)

        # 현재 기간
        row_cur = conn.execute(
            f"""
            SELECT
                COALESCE(SUM(frgn_net_amt), 0) AS frgn,
                COALESCE(SUM(orgn_net_amt), 0) AS orgn
            FROM supply_demand_daily
            WHERE biz_date >= ?{mkt_clause}
            """,
            params_cur,
        ).fetchone()

        # 이전 기간 (같은 길이)
        row_prev = conn.execute(
            f"""
            SELECT
                COALESCE(SUM(frgn_net_amt), 0) AS frgn,
                COALESCE(SUM(orgn_net_amt), 0) AS orgn
            FROM supply_demand_daily
            WHERE biz_date >= ? AND biz_date < ?{mkt_clause}
            """,
            params_prev,
        ).fetchone()

        # 쌍끌이: 기간 합산 외인+기관 둘 다 양수
        dual_buy_q = f"""
            SELECT ticker
            FROM supply_demand_daily
            WHERE biz_date >= ?{mkt_clause}
            GROUP BY ticker
            HAVING SUM(frgn_net_amt) > 0 AND SUM(orgn_net_amt) > 0
        """
        dual_cur = conn.execute(dual_buy_q, params_cur).fetchall()

        dual_prev_params = [prev_cutoff, cutoff]
        if market != "all":
            dual_prev_params.append(market)
        dual_prev_q = f"""
            SELECT ticker
            FROM supply_demand_daily
            WHERE biz_date >= ? AND biz_date < ?{mkt_clause}
            GROUP BY ticker
            HAVING SUM(frgn_net_amt) > 0 AND SUM(orgn_net_amt) > 0
        """
        dual_prev = conn.execute(dual_prev_q, dual_prev_params).fetchall()

    return {
        "foreign_total_amt": _mil_to_eok(row_cur["frgn"]),
        "foreign_prev_amt": _mil_to_eok(row_prev["frgn"]),
        "institution_total_amt": _mil_to_eok(row_cur["orgn"]),
        "institution_prev_amt": _mil_to_eok(row_prev["orgn"]),
        "dual_buy_count": len(dual_cur),
        "dual_buy_prev_count": len(dual_prev),
    }


# ---------------------------------------------------------------------------
# 6-1. 연속 순매수 감지
# ---------------------------------------------------------------------------
def detect_consecutive_buying(days: int = 20, min_streak: int = 3) -> list[dict]:
    """외인+기관 합산 연속 순매수일 감지."""
    cutoff = _cutoff_biz_date(days)

    with database.get_conn() as conn:
        rows = conn.execute(
            """
            SELECT ticker, name, sector_group, market, biz_date,
                   frgn_net_amt, orgn_net_amt
            FROM supply_demand_daily
            WHERE biz_date >= ?
            ORDER BY ticker, biz_date DESC
            """,
            [cutoff],
        ).fetchall()

    # ticker별 날짜 역순 그룹핑
    grouped: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        grouped[r["ticker"]].append(dict(r))

    results: list[dict] = []
    for ticker, records in grouped.items():
        if not records:
            continue
        streak_days = 0
        total_net_mil = 0
        streak_start = records[0]["biz_date"]
        frgn_positive_days = 0
        orgn_positive_days = 0

        for rec in records:
            frgn = rec["frgn_net_amt"] or 0
            orgn = rec["orgn_net_amt"] or 0
            net = frgn + orgn
            if net > 0:
                streak_days += 1
                total_net_mil += net
                streak_start = rec["biz_date"]
                if frgn > 0:
                    frgn_positive_days += 1
                if orgn > 0:
                    orgn_positive_days += 1
            else:
                break

        if streak_days < min_streak:
            continue

        # 투자자 분류
        if frgn_positive_days >= streak_days * 0.8 and orgn_positive_days >= streak_days * 0.8:
            investor = "both"
        elif frgn_positive_days >= orgn_positive_days:
            investor = "foreign"
        else:
            investor = "institution"

        total_net_eok = _mil_to_eok(total_net_mil)
        avg_daily = round(total_net_eok / streak_days, 1) if streak_days else 0.0

        results.append({
            "ticker": ticker,
            "name": records[0]["name"],
            "sector_group": records[0]["sector_group"] or "기타",
            "market": records[0]["market"],
            "streak_days": streak_days,
            "total_net_amt": total_net_eok,
            "streak_start": streak_start,
            "avg_daily_amt": avg_daily,
            "investor": investor,
            "is_dual_strong": investor == "both" and streak_days >= 5,
        })

    results.sort(key=lambda x: (-x["streak_days"], -x["total_net_amt"]))
    return results


# ---------------------------------------------------------------------------
# 6-2. 섹터 로테이션 감지
# ---------------------------------------------------------------------------
def detect_sector_rotation(days: int = 20, window: int = 5) -> dict[str, list[dict]]:
    """섹터 로테이션 — 최근 `window`일 vs 이전 `window`일 비교."""
    biz_dates = _get_distinct_biz_dates()
    if len(biz_dates) < 2:
        return {"rotating_in": [], "rotating_out": [], "steady_in": [], "steady_out": []}

    recent_dates = biz_dates[:window]
    prev_dates = biz_dates[window:window * 2]

    def _sector_sum(date_list: list[str]) -> dict[str, float]:
        if not date_list:
            return {}
        placeholders = ",".join("?" * len(date_list))
        with database.get_conn() as conn:
            rows = conn.execute(
                f"""
                SELECT sector_group,
                       SUM(frgn_net_amt) + SUM(orgn_net_amt) AS total
                FROM supply_demand_daily
                WHERE biz_date IN ({placeholders})
                  AND sector_group IS NOT NULL AND sector_group != ''
                GROUP BY sector_group
                """,
                date_list,
            ).fetchall()
        return {r["sector_group"]: _mil_to_eok(r["total"]) for r in rows}

    recent = _sector_sum(recent_dates)
    prev = _sector_sum(prev_dates)

    all_sectors = set(recent.keys()) | set(prev.keys())

    rotating_in, rotating_out, steady_in, steady_out = [], [], [], []

    for sector in all_sectors:
        r_amt = recent.get(sector, 0.0)
        p_amt = prev.get(sector, 0.0)

        if p_amt == 0:
            change_pct = 100.0 if r_amt > 0 else (-100.0 if r_amt < 0 else 0.0)
        else:
            change_pct = round((r_amt - p_amt) / abs(p_amt) * 100.0, 1)

        item = {
            "sector": sector,
            "recent_amt": r_amt,
            "prev_amt": p_amt,
            "change_pct": change_pct,
        }

        if r_amt > 0 and p_amt <= 0:
            item["label"] = "🆕 유입 전환"
            rotating_in.append(item)
        elif r_amt > 0 and change_pct > 50:
            item["label"] = "🔺 유입 가속"
            rotating_in.append(item)
        elif r_amt > 0 and change_pct < -50:
            item["label"] = "📉 유입 둔화"
            steady_in.append(item)
        elif r_amt > 0:
            item["label"] = "➡️ 유입 유지"
            steady_in.append(item)
        elif r_amt < 0 and p_amt > 0:
            item["label"] = "🔻 유출 전환"
            rotating_out.append(item)
        elif r_amt < 0:
            item["label"] = "⬇️ 유출 지속"
            steady_out.append(item)

    rotating_in.sort(key=lambda x: -x["recent_amt"])
    rotating_out.sort(key=lambda x: x["recent_amt"])
    steady_in.sort(key=lambda x: -x["recent_amt"])
    steady_out.sort(key=lambda x: x["recent_amt"])

    return {
        "rotating_in": rotating_in,
        "rotating_out": rotating_out,
        "steady_in": steady_in,
        "steady_out": steady_out,
    }


def build_sector_labels(days: int = 20) -> dict[str, str]:
    """sector_group → 라벨 dict. 히트맵 렌더링용."""
    rotation = detect_sector_rotation(days)
    labels: dict[str, str] = {}
    for bucket in ("rotating_in", "rotating_out", "steady_in", "steady_out"):
        for item in rotation[bucket]:
            labels[item["sector"]] = item["label"]
    return labels


# ---------------------------------------------------------------------------
# 6-3. 수급 전환 신호 감지
# ---------------------------------------------------------------------------
def detect_flow_reversal(
    days: int = 20,
    prev_window: int = 5,
    recent_window: int = 3,
    min_sell_days: int = 4,
) -> list[dict]:
    """수급 전환 종목 — 이전 5일 중 4일 이상 순매도 → 최근 3일 연속 순매수."""
    biz_dates = _get_distinct_biz_dates()
    needed = prev_window + recent_window
    if len(biz_dates) < needed:
        return []

    recent_dates = biz_dates[:recent_window]
    prev_dates = biz_dates[recent_window:recent_window + prev_window]

    placeholders = ",".join("?" * needed)
    all_dates = recent_dates + prev_dates

    with database.get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT ticker, name, sector_group, biz_date,
                   frgn_net_amt, orgn_net_amt
            FROM supply_demand_daily
            WHERE biz_date IN ({placeholders})
            """,
            all_dates,
        ).fetchall()

    by_ticker: dict[str, dict] = defaultdict(lambda: {
        "name": "",
        "sector_group": "",
        "recent": [],
        "prev": [],
    })
    for r in rows:
        slot = "recent" if r["biz_date"] in recent_dates else "prev"
        info = by_ticker[r["ticker"]]
        info["name"] = r["name"]
        info["sector_group"] = r["sector_group"] or "기타"
        info[slot].append(dict(r))

    results: list[dict] = []
    for ticker, info in by_ticker.items():
        recent = info["recent"]
        prev = info["prev"]
        if len(recent) < recent_window or len(prev) < prev_window:
            continue

        # 최근 3일 연속 순매수(합산)
        recent_nets = [(x["frgn_net_amt"] or 0) + (x["orgn_net_amt"] or 0) for x in recent]
        if not all(n > 0 for n in recent_nets):
            continue

        # 이전 5일 중 4일 이상 순매도
        prev_nets = [(x["frgn_net_amt"] or 0) + (x["orgn_net_amt"] or 0) for x in prev]
        sell_days = sum(1 for n in prev_nets if n < 0)
        if sell_days < min_sell_days:
            continue

        prev_sum_mil = sum(prev_nets)
        recent_sum_mil = sum(recent_nets)

        # 누가 전환했는가 (최근 3일 외인/기관 각각 합산)
        frgn_recent = sum(x["frgn_net_amt"] or 0 for x in recent)
        orgn_recent = sum(x["orgn_net_amt"] or 0 for x in recent)

        if frgn_recent > 0 and orgn_recent > 0:
            reversal_type = "both"
            label = "🔄 쌍끌이 매수 전환"
        elif frgn_recent >= orgn_recent:
            reversal_type = "foreign"
            label = "🔄 외인 매수 전환"
        else:
            reversal_type = "institution"
            label = "🔄 기관 매수 전환"

        results.append({
            "ticker": ticker,
            "name": info["name"],
            "sector_group": info["sector_group"],
            "prev_5d_amt": _mil_to_eok(prev_sum_mil),
            "recent_3d_amt": _mil_to_eok(recent_sum_mil),
            "reversal_type": reversal_type,
            "label": label,
        })

    results.sort(key=lambda x: -x["recent_3d_amt"])
    return results


# ---------------------------------------------------------------------------
# 6-4. 외인-기관 동조/엇갈림 감지
# ---------------------------------------------------------------------------
def detect_investor_alignment(days: int = 5) -> list[dict]:
    """외인과 기관의 방향 동조 여부."""
    biz_dates = _get_distinct_biz_dates()
    if not biz_dates:
        return []

    target_dates = biz_dates[:days]
    placeholders = ",".join("?" * len(target_dates))

    with database.get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT ticker, name, sector_group,
                   SUM(frgn_net_amt) AS frgn,
                   SUM(orgn_net_amt) AS orgn
            FROM supply_demand_daily
            WHERE biz_date IN ({placeholders})
            GROUP BY ticker
            """,
            target_dates,
        ).fetchall()

    results: list[dict] = []
    for r in rows:
        frgn = r["frgn"] or 0
        orgn = r["orgn"] or 0

        if frgn > 0 and orgn > 0:
            alignment = "쌍끌이 매수"
            label = "🔥"
        elif frgn < 0 and orgn < 0:
            alignment = "쌍끌이 매도"
            label = "❄️"
        elif frgn > 0 and orgn < 0:
            alignment = "외인↑ 기관↓"
            label = "⚡"
        elif frgn < 0 and orgn > 0:
            alignment = "외인↓ 기관↑"
            label = "⚡"
        else:
            continue

        results.append({
            "ticker": r["ticker"],
            "name": r["name"],
            "sector_group": r["sector_group"] or "기타",
            "frgn_5d_amt": _mil_to_eok(frgn),
            "orgn_5d_amt": _mil_to_eok(orgn),
            "alignment": alignment,
            "label": label,
        })

    results.sort(key=lambda x: -(abs(x["frgn_5d_amt"]) + abs(x["orgn_5d_amt"])))
    return results
