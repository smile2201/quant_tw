"""
scripts/monthly_review.py
每月自動健檢（每月 1 日由 GitHub Actions 觸發）：
  1. 跑 verify_performance.py（選股成效 vs 0050）
  2. 跑 analyze_signals.py（逐訊號有效性）
  3. 彙整成 LINE 摘要推播——最強/最弱訊號、勝率趨勢、是否需要調參
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from pathlib import Path
from datetime import datetime

from config.settings import RESULTS_DIR
from notify import line_bot

MIN_SAMPLES = 30


def run():
    # 1+2. 重新產出兩份報告
    import verify_performance, analyze_signals
    verify_performance.run()
    analyze_signals.run()

    results_dir = Path(RESULTS_DIR)
    perf = pd.read_csv(results_dir / "performance_report.csv")
    sig  = pd.read_csv(results_dir / "signal_effectiveness.csv")

    lines = [f"🔬 月度健檢 {datetime.now().strftime('%Y/%m')}",
             "━━━━━━━━━━━━━━"]

    # ── 選股成效 ─────────────────────────────────────────────────────────
    for tier in ["強力候選", "觀察股"]:
        v = perf[perf["tier"] == tier]["ret_now"].dropna()
        if len(v):
            lines.append(f"{tier}：{len(v)} 筆｜均 {v.mean():+.2f}%｜勝率 {(v>0).mean()*100:.0f}%")

    corr_df = perf.dropna(subset=["ret_20d", "final_score"])
    if len(corr_df) > 10:
        corr = corr_df["final_score"].corr(corr_df["ret_20d"])
        lines.append(f"評分預測力（20日相關）：{corr:+.3f}")
    lines.append("")

    # ── 訊號紅黑榜（樣本足夠者）─────────────────────────────────────────
    valid = sig[(sig["count"] >= MIN_SAMPLES) & sig["mean_5d"].notna()]
    if not valid.empty:
        top = valid.nlargest(3, "mean_5d")
        bot = valid.nsmallest(3, "mean_5d")
        lines.append("✅ 最強訊號（5日均）")
        for _, r in top.iterrows():
            lines.append(f"  {r['signal']} {r['mean_5d']:+.1f}%（{int(r['count'])}筆）")
        lines.append("❌ 最弱訊號")
        for _, r in bot.iterrows():
            lines.append(f"  {r['signal']} {r['mean_5d']:+.1f}%（{int(r['count'])}筆）")
        lines.append("")

        # 弱訊號若仍在給分 → 提示調參
        if (bot["mean_5d"] < -1.5).any():
            lines.append("💡 有訊號 5日均 < -1.5%，建議檢視評分權重")
            lines.append("")

    lines += ["完整報告見 repo results/", "⚠️ 僅供參考，非投資建議"]
    msg = "\n".join(lines)
    print(msg)
    line_bot.send(msg)


if __name__ == "__main__":
    run()
