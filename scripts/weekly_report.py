"""
scripts/weekly_report.py
每週績效報告（週五 17:05 由 GitHub Actions 觸發，推播 LINE）
內容：本週平倉明細、未平倉部位損益、累計戰績、大盤環境
資料來源：results/positions.csv + 即時報價
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from datetime import datetime, timedelta

from position_tracker import _last_close, load_positions
from notify import line_bot


def run():
    pos = load_positions()
    if pos.empty:
        print("無持倉記錄")
        return

    today    = datetime.now()
    week_ago = (today - timedelta(days=7)).strftime("%Y%m%d")
    lines    = [f"📊 週報 {today.strftime('%Y/%m/%d')}",
                "━━━━━━━━━━━━━━"]

    # ── 本週平倉 ─────────────────────────────────────────────────────────
    closed_all  = pos[pos["status"].isin(["stopped", "expired"])].copy()
    closed_all["ret_pct"] = pd.to_numeric(closed_all["ret_pct"], errors="coerce")
    closed_week = closed_all[closed_all["exit_date"].astype(str) >= week_ago]

    if not closed_week.empty:
        lines.append(f"✂️ 本週平倉（{len(closed_week)} 筆）")
        for _, r in closed_week.iterrows():
            icon = "💰" if r["ret_pct"] > 0 else "🛑"
            lines.append(f"  {icon} {line_bot.stock_label(r['stock_id'])} "
                         f"{r['ret_pct']:+.1f}%")
        lines.append("")

    # ── 未平倉部位 ───────────────────────────────────────────────────────
    open_pos = pos[pos["status"].isin(["open", "target"])]
    if not open_pos.empty:
        lines.append(f"📂 持倉中（{len(open_pos)} 檔）")
        unrealized = []
        for _, r in open_pos.iterrows():
            now = _last_close(str(r["stock_id"]))
            entry = float(r["entry_price"])
            if now <= 0 or entry <= 0:
                continue
            ret = (now - entry) / entry * 100
            unrealized.append(ret)
            icon = "🔥" if r["status"] == "target" else ("🟢" if ret > 0 else "🔴")
            lines.append(f"  {icon} {line_bot.stock_label(r['stock_id'])} "
                         f"{ret:+.1f}%（{int(r['days_held'])}日）")
        if unrealized:
            lines.append(f"  合計未實現：{sum(unrealized)/len(unrealized):+.2f}%")
        lines.append("")

    # ── 累計戰績 ─────────────────────────────────────────────────────────
    if not closed_all.empty:
        v   = closed_all["ret_pct"].dropna()
        win = (v > 0).mean() * 100 if len(v) else 0
        lines += [
            "🏆 累計戰績（已平倉）",
            f"  {len(v)} 筆｜勝率 {win:.0f}%｜平均 {v.mean():+.2f}%",
            f"  最佳 {v.max():+.1f}%｜最差 {v.min():+.1f}%",
            "",
        ]

    # ── 大盤環境 ─────────────────────────────────────────────────────────
    try:
        from data.macro_fetcher import fetch_market_regime
        regime = fetch_market_regime()
        if regime:
            lines.append(regime["desc"])
    except Exception:
        pass

    lines.append("⚠️ 僅供參考，非投資建議")
    msg = "\n".join(lines)
    print(msg)
    line_bot.send(msg)


if __name__ == "__main__":
    run()
