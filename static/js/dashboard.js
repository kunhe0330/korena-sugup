/* Korena 수급 동향 대시보드 - 클라이언트 스크립트 */
(function () {
  "use strict";

  const state = {
    days: 20,
    market: "all",
    topTab: "foreign",
    data: null,
  };

  // --------------------------------------------------------------
  // 유틸
  // --------------------------------------------------------------
  function fmtAmt(val) {
    if (val === null || val === undefined || isNaN(val)) return "-";
    const sign = val > 0 ? "+" : "";
    if (Math.abs(val) >= 10000) {
      return `${sign}${(val / 10000).toFixed(1)}조`;
    }
    return `${sign}${val.toLocaleString("ko-KR", { maximumFractionDigits: 1 })}억`;
  }

  function fmtPct(val) {
    if (val === null || val === undefined || isNaN(val)) return "-";
    const sign = val > 0 ? "+" : "";
    return `${sign}${val.toFixed(2)}%`;
  }

  function $(sel, parent) {
    return (parent || document).querySelector(sel);
  }
  function $$(sel, parent) {
    return Array.from((parent || document).querySelectorAll(sel));
  }

  // --------------------------------------------------------------
  // API 호출
  // --------------------------------------------------------------
  async function fetchData() {
    const params = new URLSearchParams({
      days: state.days,
      market: state.market,
      top: 30,
    });
    const resp = await fetch(`/api/supply-demand?${params}`);
    if (!resp.ok) throw new Error(`API 실패: ${resp.status}`);
    return resp.json();
  }

  async function refresh() {
    try {
      state.data = await fetchData();
      render();
    } catch (e) {
      console.error(e);
      alert("데이터 로드 실패: " + e.message);
    }
  }

  // --------------------------------------------------------------
  // 렌더링
  // --------------------------------------------------------------
  function render() {
    const d = state.data;
    if (!d) return;

    renderDataWarning(d.data_days);
    renderSummary(d.summary);
    renderHeatmap(d.sector_summary);
    renderConsecutive(d.consecutive_buy);
    renderFlowReversal(d.flow_reversals);
    renderTopTable();

    $("#data-days").textContent = d.data_days ?? "-";
    $("#total-records").textContent = d.total_records ?? "-";
    $("#last-updated").textContent = d.last_updated || "-";
  }

  // ❶ 요약 카드
  function renderSummary(s) {
    if (!s) return;
    setCard("card-foreign", s.foreign_total_amt, s.foreign_prev_amt);
    setCard("card-institution", s.institution_total_amt, s.institution_prev_amt);
    setDualCard(s.dual_buy_count, s.dual_buy_prev_count);
  }

  function setCard(cardId, cur, prev) {
    const card = document.getElementById(cardId);
    if (!card) return;
    card.querySelector('[data-field$="_total_amt"]').textContent = fmtAmt(cur);
    const sub = card.querySelector('[data-field$="_delta"]');
    if (sub) {
      const delta = cur - prev;
      const arrow = delta > 0 ? "▲" : delta < 0 ? "▼" : "─";
      sub.textContent = `${arrow} 이전 기간 대비 ${fmtAmt(delta)}`;
      sub.className = "card-sub " + (delta > 0 ? "sub-up" : delta < 0 ? "sub-down" : "");
    }
  }

  function setDualCard(cur, prev) {
    const card = document.getElementById("card-dual");
    if (!card) return;
    card.querySelector('[data-field="dual_buy_count"]').textContent = `${cur || 0}개`;
    const sub = card.querySelector('[data-field="dual_delta"]');
    const delta = (cur || 0) - (prev || 0);
    const arrow = delta > 0 ? "▲" : delta < 0 ? "▼" : "─";
    sub.textContent = `${arrow} 이전 대비 ${delta > 0 ? "+" : ""}${delta}개`;
    sub.className = "card-sub " + (delta > 0 ? "sub-up" : delta < 0 ? "sub-down" : "");
  }

  // ❷ 섹터 히트맵
  function renderHeatmap(sectors) {
    const container = $("#sector-heatmap");
    container.innerHTML = "";
    if (!sectors || sectors.length === 0) {
      container.innerHTML = '<div class="empty">섹터 데이터가 없습니다.</div>';
      return;
    }

    const maxAbs = Math.max(...sectors.map((s) => Math.abs(s.total_net_amt)), 1);
    for (const s of sectors) {
      const row = document.createElement("div");
      row.className = "heatmap-row";
      const amt = s.total_net_amt;
      const isPos = amt >= 0;
      const widthPct = Math.min(100, (Math.abs(amt) / maxAbs) * 100);

      row.innerHTML = `
        <div class="heatmap-sector">${escapeHtml(s.sector_group)}</div>
        <div class="heatmap-bar-wrap">
          <div class="heatmap-bar ${isPos ? "inflow" : "outflow"}" style="width:${widthPct}%"></div>
        </div>
        <div class="heatmap-amount ${isPos ? "inflow" : "outflow"}">${fmtAmt(amt)}</div>
        <div class="heatmap-label">${escapeHtml(s.label || "")}</div>
      `;
      container.appendChild(row);
    }
  }

  // ❸ 연속 순매수 테이블
  function renderConsecutive(rows) {
    const tbody = $("#consecutive-table tbody");
    tbody.innerHTML = "";
    if (!rows || rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty">감지된 연속 순매수 종목이 없습니다.</td></tr>';
      return;
    }
    const maxAvg = Math.max(...rows.map((r) => r.avg_daily_amt), 1);
    for (const r of rows) {
      const tr = document.createElement("tr");
      const investorLabel = {
        both: "🔥쌍끌이",
        foreign: "👤외인",
        institution: "🏛기관",
      }[r.investor] || "-";
      const streakBadge = r.is_dual_strong ? "🔥 " : "";
      const widthPct = (r.avg_daily_amt / maxAvg) * 100;
      tr.innerHTML = `
        <td><strong>${escapeHtml(r.name)}</strong> <span class="text-dim">${r.ticker}</span></td>
        <td>${escapeHtml(r.sector_group)}</td>
        <td class="num">${streakBadge}${r.streak_days}일</td>
        <td class="num ${r.total_net_amt >= 0 ? "amt-pos" : "amt-neg"}">${fmtAmt(r.total_net_amt)}</td>
        <td>${investorLabel}</td>
        <td class="num"><span class="strength-bar" style="width:${Math.max(widthPct, 4)}px"></span></td>
      `;
      tbody.appendChild(tr);
    }
  }

  // ❹ 수급 전환 카드
  function renderFlowReversal(items) {
    const container = $("#flow-reversal-list");
    container.innerHTML = "";
    if (!items || items.length === 0) {
      container.innerHTML = '<div class="empty">최근 감지된 전환 신호가 없습니다.</div>';
      return;
    }

    for (const it of items) {
      const card = document.createElement("div");
      card.className = "reversal-card";
      // 간단 타임라인: 이전 5일(빨강) + 최근 3일(파랑)
      const cells = [];
      for (let i = 0; i < 5; i++) cells.push('<div class="rc-cell neg"></div>');
      for (let i = 0; i < 3; i++) cells.push('<div class="rc-cell pos"></div>');
      card.innerHTML = `
        <div class="rc-title">${it.label} · ${escapeHtml(it.name)} <span class="text-dim">${it.ticker}</span></div>
        <div class="rc-sub">
          이전 5일 <span class="amt-neg">${fmtAmt(it.prev_5d_amt)}</span> →
          최근 3일 <span class="amt-pos">${fmtAmt(it.recent_3d_amt)}</span>
        </div>
        <div class="rc-bar">${cells.join("")}</div>
      `;
      container.appendChild(card);
    }
  }

  // ❺ TOP 테이블
  function renderTopTable() {
    const tbody = $("#top-table tbody");
    tbody.innerHTML = "";
    const d = state.data;
    if (!d) return;

    let rows = [];
    if (state.topTab === "foreign") {
      rows = [...(d.stock_top_buy || [])]
        .filter((r) => r.total_frgn_amt > 0)
        .sort((a, b) => b.total_frgn_amt - a.total_frgn_amt)
        .slice(0, 20);
    } else if (state.topTab === "institution") {
      rows = [...(d.stock_top_buy || [])]
        .filter((r) => r.total_orgn_amt > 0)
        .sort((a, b) => b.total_orgn_amt - a.total_orgn_amt)
        .slice(0, 20);
    } else {
      rows = (d.stock_top_sell || []).slice(0, 20);
    }

    if (rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty">데이터 없음</td></tr>';
      return;
    }

    rows.forEach((r, idx) => {
      const tr = document.createElement("tr");
      const amt =
        state.topTab === "foreign"
          ? r.total_frgn_amt
          : state.topTab === "institution"
          ? r.total_orgn_amt
          : r.total_net_amt;
      tr.innerHTML = `
        <td class="num">${idx + 1}</td>
        <td><strong>${escapeHtml(r.name)}</strong> <span class="text-dim">${r.ticker}</span></td>
        <td>${escapeHtml(r.market || "-")}</td>
        <td>${escapeHtml(r.sector_group || "-")}</td>
        <td class="num ${amt >= 0 ? "amt-pos" : "amt-neg"}">${fmtAmt(amt)}</td>
        <td class="num ${r.avg_change_pct >= 0 ? "pct-pos" : "pct-neg"}">${fmtPct(r.avg_change_pct)}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  // 데이터 부족 안내
  function renderDataWarning(dataDays) {
    const warn = $("#data-warning");
    if (!warn) return;
    if (dataDays >= 10) {
      warn.hidden = true;
      warn.innerHTML = "";
      return;
    }
    warn.hidden = false;
    const lines = [
      `📊 현재 ${dataDays || 0}일치 데이터가 쌓였습니다.`,
      `<ul style="margin:6px 0 0 18px;padding:0;">`,
      `<li>연속 순매수 감지: 3일 이상 필요 ${dataDays >= 3 ? "✅" : "⏳"}</li>`,
      `<li>외인-기관 동조: 5일 이상 필요 ${dataDays >= 5 ? "✅" : "⏳"}</li>`,
      `<li>수급 전환 신호: 8일 이상 필요 ${dataDays >= 8 ? "✅" : "⏳"}</li>`,
      `<li>섹터 로테이션: 10일 이상 필요 ${dataDays >= 10 ? "✅" : "⏳"}</li>`,
      `</ul>`,
    ];
    warn.innerHTML = lines.join("");
  }

  function escapeHtml(s) {
    if (s === null || s === undefined) return "";
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[c]);
  }

  // --------------------------------------------------------------
  // 이벤트 바인딩
  // --------------------------------------------------------------
  function bindEvents() {
    $$('.btn-group[data-role="period"] button').forEach((btn) => {
      btn.addEventListener("click", () => {
        $$('.btn-group[data-role="period"] button').forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.days = parseInt(btn.dataset.days, 10);
        refresh();
      });
    });

    $$('.btn-group[data-role="market"] button').forEach((btn) => {
      btn.addEventListener("click", () => {
        $$('.btn-group[data-role="market"] button').forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.market = btn.dataset.market;
        refresh();
      });
    });

    $$(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        $$(".tab-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.topTab = btn.dataset.tab;
        renderTopTable();
      });
    });

    $("#manual-collect-btn").addEventListener("click", async () => {
      if (!confirm("수급 데이터를 수동 수집하시겠습니까? (1일 1회 제한)")) return;
      try {
        const resp = await fetch("/api/supply-demand/collect", { method: "POST" });
        const result = await resp.json();
        if (resp.status === 429) {
          alert(result.message || "1일 1회 제한");
          return;
        }
        if (resp.ok) {
          alert(`수집 완료: ${result.saved}건`);
          refresh();
        } else {
          alert(`수집 실패: ${result.message || "알 수 없는 오류"}`);
        }
      } catch (e) {
        alert("수집 실패: " + e.message);
      }
    });
  }

  // --------------------------------------------------------------
  // 시작
  // --------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    refresh();
  });
})();
