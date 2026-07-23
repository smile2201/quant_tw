"""
scripts/analyze_signals.py
逐訊號有效性分析：把每天選股結果中的個別訊號拆開，
統計每個訊號出現後 5/20 日與至今的實際報酬
執行：python scripts/analyze_signals.py（需先跑過 verify_performance.py）
輸出：results/signal_effectiveness.csv + 終端摘要
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from pathlib import Path

from config.settings import RESULTS_DIR

MIN_SAMPLES = 30   # 樣本低於此數的訊號不下結論


def normalize_signal(sig: str) -> str:
    """把帶數字的訊號歸一化：外資連買4日→外資連買、RSI=69→RSI>60 等"""
    sig = sig.strip()
    if not sig:
        return ""
    m = re.match(r"RSI=(\d+)", sig)
    if m:
        v = int(m.group(1))
        if v >= 70:  return "RSI超買(≥70)"
        if v >= 60:  return "RSI偏高(60-70)"
        if v <= 30:  return "RSI超賣(≤30)"
        if v <= 40:  return "RSI偏低(30-40)"
        return "RSI中性(40-60)"
    sig = re.sub(r"連買\d+日", "連買", sig)
    sig = re.sub(r"券資比[\d.]+↓低", "券資比低", sig)
    sig = re.sub(r"券資比[\d.]+↑高", "券資比高", sig)
    sig = re.sub(r"券資比[\d.]+$", "券資比中性", sig)
    sig = re.sub(r"融資\+[\d.]+%$", "融資健康增", sig)
    sig = re.sub(r"融資暴增\+[\d.]+%⚠️", "融資暴增", sig)
    sig = re.sub(r"融資-[\d.]+%↓", "融資減", sig)
    sig = re.sub(r"使用率\d+%↓", "融資使用率低", sig)
    sig = re.sub(r"使用率\d+%↑高", "融資使用率高", sig)
    return sig


def run():
    results_dir = Path(RESULTS_DIR)
    perf_path = results_dir / "performance_report.csv"
    if not perf_path.exists():
        print("請先執行 python scripts/verify_performance.py")
        return

    perf = pd.read_csv(perf_path)
    perf["stock_id"] = perf["stock_id"].astype(str)

    # 從各日 screener CSV 撈出訊號文字
    rows = []
    for f in sorted(results_dir.glob("*_screener.csv")):
        d = f.stem.split("_")[0]
        date_iso = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        df = pd.read_csv(f)
        if "tier" not in df.columns:
            continue
        for _, r in df.iterrows():
            for col, prefix in [("tech_signals", "技術"), ("chip_signals", "籌碼"),
                                ("fund_signals", "基本")]:
                raw = str(r.get(col, "") or "")
                if raw in ("", "nan", "無"):
                    continue
                for s in raw.split("|"):
                    ns = normalize_signal(s)
                    if ns:
                        rows.append({"date": date_iso, "stock_id": str(r["stock_id"]),
                                     "signal": f"[{prefix}] {ns}"})

    sig_df = pd.DataFrame(rows)
    merged = sig_df.merge(perf, on=["date", "stock_id"], how="inner")
    if merged.empty:
        print("訊號與報酬資料對不上")
        return

    # 每個訊號的統計
    stats = []
    for sig, g in merged.groupby("signal"):
        row = {"signal": sig, "count": len(g)}
        for col, label in [("ret_5d", "5d"), ("ret_20d", "20d"), ("ret_now", "now")]:
            v = g[col].dropna()
            row[f"mean_{label}"] = round(v.mean(), 2) if len(v) else None
            row[f"win_{label}"]  = round((v > 0).mean() * 100, 1) if len(v) else None
        stats.append(row)

    out = pd.DataFrame(stats).sort_values("mean_5d", ascending=False)
    out_path = results_dir / "signal_effectiveness.csv"
    out.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"已存：{out_path}\n")

    # 全體基準（所有入選股的平均，作為訊號好壞的比較基準）
    base_5d  = perf["ret_5d"].dropna().mean()
    base_now = perf["ret_now"].dropna().mean()
    print(f"基準（全部入選股平均）：5日 {base_5d:+.2f}% | 至今 {base_now:+.2f}%\n")

    print(f"{'訊號':<28} {'樣本':>5} {'5日均':>7} {'5日勝率':>7} {'至今均':>7}")
    print("─" * 62)
    for _, r in out.iterrows():
        mark = "" if r["count"] >= MIN_SAMPLES else "（樣本少）"
        m5   = f"{r['mean_5d']:+.2f}%" if pd.notna(r["mean_5d"]) else "  -"
        w5   = f"{r['win_5d']:.0f}%"   if pd.notna(r["win_5d"])  else "  -"
        mn   = f"{r['mean_now']:+.2f}%" if pd.notna(r["mean_now"]) else "  -"
        print(f"{r['signal']:<28} {r['count']:>5} {m5:>7} {w5:>7} {mn:>7} {mark}")

    # 文獻建議的黃金組合：投信連買 + 營收動能
    print("\n── 組合訊號（FinLab 文獻：投信+營收成長 十年年化 30%）──")
    combos = [
        ("投信買超×營收動能", ["[籌碼] 投信", "[基本] 營收動能"]),
        ("外資連買×營收動能", ["[籌碼] 外資連買", "[基本] 營收動能"]),
    ]
    pair = merged.groupby(["date", "stock_id"])["signal"].apply(set).reset_index()
    pair = pair.merge(perf, on=["date", "stock_id"], how="inner")
    for name, needs in combos:
        mask = pair["signal"].apply(
            lambda ss: all(any(n in s for s in ss) for n in needs))
        g = pair[mask]
        v5, vn = g["ret_5d"].dropna(), g["ret_now"].dropna()
        if len(v5) >= 5:
            print(f"{name}: {len(g)} 筆 | 5日 {v5.mean():+.2f}%（勝率 {(v5>0).mean()*100:.0f}%）"
                  f" | 至今 {vn.mean():+.2f}%")
        else:
            print(f"{name}: 樣本不足（{len(g)} 筆）")


if __name__ == "__main__":
    run()
