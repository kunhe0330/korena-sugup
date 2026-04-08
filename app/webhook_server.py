"""Flask 웹서버 — 수급 동향 대시보드 API + UI."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from . import config, database, patterns, sectors
from .supply_demand_collector import collect_daily_supply_demand

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(_PROJECT_ROOT / "templates"),
        static_folder=str(_PROJECT_ROOT / "static"),
    )

    # 초기화
    database.init_db()
    sectors.load_sector_data()

    _last_manual_collect: dict[str, datetime | None] = {"ts": None}

    # ------------------------------------------------------------------
    # 페이지 라우트
    # ------------------------------------------------------------------
    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/supply-demand")
    def supply_demand_page():
        return render_template("supply_demand.html")

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    @app.route("/api/supply-demand", methods=["GET"])
    def api_supply_demand():
        days = request.args.get("days", 20, type=int)
        market = request.args.get("market", "all")
        top_n = request.args.get("top", 30, type=int)

        days = max(1, min(days, 120))
        top_n = max(1, min(top_n, 100))
        if market not in ("all", "KOSPI", "KOSDAQ"):
            market = "all"

        stock_summary = patterns.query_stock_summary(days, market)
        sector_summary = patterns.query_sector_summary(days, market)

        rotation = patterns.detect_sector_rotation(days)
        sector_labels = patterns.build_sector_labels(days)
        for row in sector_summary:
            row["label"] = sector_labels.get(row["sector_group"], "")

        consecutive = patterns.detect_consecutive_buying(days)
        flow_rev = patterns.detect_flow_reversal(days)
        alignment = patterns.detect_investor_alignment(min(days, 5))

        return jsonify({
            "period_days": days,
            "market": market,
            "summary": patterns.query_summary(days, market),
            "stock_top_buy": stock_summary["top_buy"][:top_n],
            "stock_top_sell": stock_summary["top_sell"][:top_n],
            "sector_summary": sector_summary,
            "sector_rotation": rotation,
            "consecutive_buy": consecutive,
            "flow_reversals": flow_rev,
            "investor_alignment": alignment,
            "last_updated": database.get_last_collection_date(),
            "total_records": database.get_total_record_count(),
            "data_days": database.get_collected_day_count(),
        })

    @app.route("/api/supply-demand/collect", methods=["POST"])
    def api_supply_demand_collect():
        """수동 수집 트리거 — 1일 1회 제한."""
        now = datetime.now()
        last_ts = _last_manual_collect["ts"]
        if last_ts and (now - last_ts).total_seconds() < 86400:
            remaining = 86400 - (now - last_ts).total_seconds()
            hours = int(remaining // 3600)
            return jsonify({
                "status": "rate_limited",
                "message": f"1일 1회 제한. {hours}시간 후 가능",
            }), 429

        try:
            saved = collect_daily_supply_demand()
        except Exception as e:
            logger.exception("수동 수급 수집 실패")
            return jsonify({"status": "error", "message": str(e)}), 500

        _last_manual_collect["ts"] = now
        return jsonify({"status": "ok", "saved": saved})

    @app.route("/api/health", methods=["GET"])
    def api_health():
        return jsonify({
            "status": "ok",
            "supply_demand_enabled": config.SUPPLY_DEMAND_ENABLED,
            "last_collection": database.get_last_collection_date(),
            "total_records": database.get_total_record_count(),
            "data_days": database.get_collected_day_count(),
        })

    return app
