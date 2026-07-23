"""
scripts/verify_performance.py
選股成效驗證：統計歷史選股（強力候選/觀察股）在入選後 5/10/20 個交易日的實際報酬
執行：python scripts/verify_performance.py
輸出：results/performance_report.csv + 終端摘要
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

from config.settings import RESULTS_DIR, CACHE_ROOT, FINMIND_PRICE_DATASET
from data.finmind_fetcher import fetch_stock

HORIZONS = [5, 10, 20]           # 入選後 N 個交易日
TIERS    = ["強力候選", "觀察股"]


def _load_price(stock_id: str) -> pd.DataFrame:
    """讀價格資料，cache 過舊（> 5 天）自動重抓"""
    df = fetch_stock(stock_id, FINMIND_PRICE_DATASET)
    if not df.empty and "date" in df.columns:
        max_date = pd.to_datetime(df["date"]).max()
        if (datetime.now() - max_date).days > 5:
            df = fetch_stock(stock_id, FINMIND_PRICE_DATASET, force_refresh=True)
    return df


def forward_returns(price_df: pd.DataFrame, base_date: str) -> dict:
    """
    以 base_date 收盤價為基準，計算 +N 交易日報酬（%）
    回傳 {horizon: return_pct or None}
    """
    out = {h: None for h in HORIZONS}
    if price_df.empty or "close" not in price_df.columns:
        return out

    df = price_df.sort_values("date").reset_index(drop=True)
    dates = df["date"].astype(str).tolist()

    # 找 base_date 當天（或之前最近一個交易日）的位置
    idx = None
    for i in range(len(dates) - 1, -1, -1):
        if dates[i] <= base_date:
            idx = i
            break
    if idx is None:
        return out

    base_close = float(df["close"].iloc[idx])
    if base_close <= 0:
        return out

    for h in HORIZONS:
        j = idx + h
        if j < len(df):
            out[h] = (float(df["close"].iloc[j]) - base_close) / base_close * 100
    return out


def run():
    results_dir = Path(RESULTS_DIR)
    csvs = sorted(results_dir.glob("*_screener.csv"))
    if not csvs:
        print("找不到選股結果")
        return

    print(f"=== 選股成效驗證（{len(csvs)} 個交易日的記錄）===\n")

    price_cache: dict = {}
    records = []

    for f in csvs:
        date_raw = f.stem.split("_")[0]                       # YYYYMMDD
        date_iso = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:]}"
        df = pd.read_csv(f)
        if "tier" not in df.columns:
            continue

        picks = df[df["tier"].isin(TIERS)]
        for _, row in picks.iterrows():
            sid = str(row["stock_id"])
            if sid not in price_cache:
                price_cache[sid] = _load_price(sid)

            rets = forward_returns(price_cache[sid], date_iso)
            records.append({
                "date":        date_iso,
                "stock_id":    sid,
                "tier":        row["tier"],
                "final_score": row.get("final_score"),
                **{f"ret_{h}d": rets[h] for h in HORIZONS},
            })

    if not records:
        print("無可驗證的記錄")
        return

    report = pd.DataFrame(records)
    out_path = results_dir / "performance_report.csv"
    report.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"明細已存：{out_path}（{len(report)} 筆選股記錄）\n")

    # ── 摘要 ─────────────────────────────────────────────────────────────
    print(f"{'層級':<6} {'期間':<6} {'樣本':>5} {'平均報酬':>8} {'勝率':>7} {'最佳':>7} {'最差':>7}")
    print("─" * 55)
    for tier in TIERS:
        sub = report[report["tier"] == tier]
        for h in HORIZONS:
            col   = f"ret_{h}d"
            valid = sub[col].dropna()
            if valid.empty:
                continue
            win = (valid > 0).mean() * 100
            print(f"{tier:<6} {h:>3}日 {len(valid):>5} "
                  f"{valid.mean():>+7.2f}% {win:>6.1f}% "
                  f"{valid.max():>+6.1f}% {valid.min():>+6.1f}%")
        print()

    # 分數與報酬的相關性（分數越高報酬越好才代表評分有效）
    valid20 = report.dropna(subset=["ret_20d", "final_score"])
    if len(valid20) > 10:
        corr = valid20["final_score"].corr(valid20["ret_20d"])
        print(f"final_score 與 20日報酬相關係數：{corr:.3f}"
              f"（> 0 代表分數越高報酬越好）")


if __name__ == "__main__":
    run()
