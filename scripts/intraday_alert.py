"""
scripts/intraday_alert.py
盤中突破通知（每 30~60 分鐘由 GitHub Actions 觸發）
監控最新選股名單中「強力候選」及「觀察股」：
  - 突破 N 日高點
  - 成交量爆量（>= 均量 N 倍）
  - 跌破 MA20 支撐
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import requests
import pandas as pd
from pathlib import Path
from datetime import datetime

from config.settings import SCREENER, RESULTS_DIR, CACHE_ROOT
from notify import line_bot

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}.TW"
HEADERS   = {"User-Agent": "Mozilla/5.0 (compatible; quant_tw/1.0)"}


def _get_realtime(stock_id: str) -> dict:
    try:
        resp = requests.get(YAHOO_URL.format(stock_id), headers=HEADERS, timeout=10)
        meta = resp.json()["chart"]["result"][0]["meta"]
        return {
            "price":  meta.get("regularMarketPrice", 0),
            "volume": meta.get("regularMarketVolume", 0),
        }
    except Exception:
        return {}


def _load_cache(stock_id: str) -> pd.DataFrame:
    for dataset in ("price_adj", "price"):
        p = Path(CACHE_ROOT) / dataset / f"{stock_id}.parquet"
        if p.exists():
            return pd.read_parquet(p)
    return pd.DataFrame()


def _high_n(df: pd.DataFrame, n: int) -> float:
    """過去 n 日收盤最高（不含今日）"""
    if df.empty or "close" not in df.columns:
        return 0.0
    return float(df["close"].iloc[-(n + 1):-1].max()) if len(df) > n else 0.0


def _avg_volume(df: pd.DataFrame, n: int = 20) -> float:
    vol_col = next((c for c in df.columns if "volume" in c.lower()), None)
    if not vol_col or df.empty:
        return 0.0
    return float(df[vol_col].iloc[-(n + 1):-1].mean()) if len(df) > n else 0.0


def _ma20(df: pd.DataFrame) -> float:
    if df.empty or "close" not in df.columns or len(df) < 20:
        return 0.0
    return float(df["close"].iloc[-20:].mean())


def run():
    results_dir = Path(RESULTS_DIR)
    csvs = sorted(results_dir.glob("*_screener.csv"), reverse=True)
    if not csvs:
        print("無選股結果可監控")
        return

    screener = pd.read_csv(csvs[0])
    watch_df = screener[screener["tier"].isin(["強力候選", "觀察股"])]
    if watch_df.empty:
        print("選股名單為空")
        return

    now_str    = datetime.now().strftime("%H:%M")
    n_break    = SCREENER["intraday_breakout_days"]
    vol_thresh = SCREENER["intraday_volume_ratio"]
    alerts     = []

    for _, row in watch_df.iterrows():
        sid  = str(row["stock_id"])
        rt   = _get_realtime(sid)
        if not rt or not rt["price"]:
            continue

        price  = rt["price"]
        volume = rt["volume"]
        hist   = _load_cache(sid)

        sigs = []

        # 突破 N 日高點
        high = _high_n(hist, n_break)
        if high > 0 and price > high:
            pct = (price - high) / high * 100
            sigs.append(f"🚀 突破{n_break}日高 +{pct:.1f}%")

        # 爆量
        avg_vol = _avg_volume(hist)
        if avg_vol > 0 and volume > 0:
            vr = volume / avg_vol
            if vr >= vol_thresh:
                sigs.append(f"📢 爆量 {vr:.1f}x")

        # 跌破 MA20
        ma = _ma20(hist)
        if ma > 0 and price < ma * 0.99:
            sigs.append(f"⚠️ 跌破MA20（{ma:.1f}）")

        if sigs:
            tier_icon = "💎" if row["tier"] == "強力候選" else "👀"
            alerts.append(f"{tier_icon} {line_bot.stock_label(sid)}  {price}\n  "
                          + "\n  ".join(sigs))

    if not alerts:
        print(f"[{now_str}] 無觸發訊號（監控 {len(watch_df)} 檔）")
        return

    msg = (
        f"⚡ 盤中通知 {now_str}\n"
        f"{'─' * 16}\n"
        + "\n\n".join(alerts)
        + f"\n\n監控 {len(watch_df)} 檔，觸發 {len(alerts)} 檔\n⚠️ 僅供參考"
    )
    line_bot.send(msg)
    print(f"[{now_str}] 已推播 {len(alerts)} 個訊號")


if __name__ == "__main__":
    run()
