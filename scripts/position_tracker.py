"""
scripts/position_tracker.py
虛擬持倉追蹤：把每天的強力候選視為「推薦日收盤買進」的虛擬部位，
每日盤後檢查，觸發出場條件就推播 LINE——補上系統一直缺的「出場」。

三段式出場紀律（見 config.settings SCREENER）：
  第一段：跌破進場價 -7% → 🛑 停損出場（status=stopped）
  第二段：峰值曾達 +10% → 停損上移到成本價（賺錢的單不許變賠錢）
  第三段：峰值曾達 +15% → 移動停損 = 峰值 -8%（讓獲利奔跑，鎖住大部分漲幅）
  到期：持有滿 20 個交易日 → 結算報告（status=expired）

狀態檔：results/positions.csv（含 peak_price 峰值欄，由 workflow commit 保存）
執行：python scripts/position_tracker.py（在 run_screener 之後跑）
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import requests
import pandas as pd
from pathlib import Path
from datetime import datetime

from config.settings import RESULTS_DIR, SCREENER
from notify import line_bot

POSITIONS_PATH = Path(RESULTS_DIR) / "positions.csv"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}.TW"
HEADERS   = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/126.0.0.0 Safari/537.36")}

COLUMNS = ["stock_id", "entry_date", "entry_price", "peak_price", "status",
           "exit_date", "exit_price", "ret_pct", "days_held"]


def _last_close(stock_id: str) -> float:
    """最新收盤價：Yahoo 優先，被限流時退回 FinMind（含當日資料）"""
    try:
        resp = requests.get(YAHOO_URL.format(stock_id), headers=HEADERS, timeout=10)
        meta = resp.json()["chart"]["result"][0]["meta"]
        price = float(meta.get("regularMarketPrice") or 0)
        if price > 0:
            return price
    except Exception:
        pass

    try:
        from data.finmind_fetcher import fetch_stock
        df = fetch_stock(stock_id, "price", force_refresh=True)
        if not df.empty:
            return float(df.sort_values("date")["close"].iloc[-1])
    except Exception as e:
        print(f"  [tracker] {stock_id} 取價失敗（Yahoo+FinMind）：{e}")
    return 0.0


def dividends_since(stock_id: str, entry_date: str, refresh: bool = True) -> float:
    """
    進場日之後至今的累計現金股利（除權息旺季防誤觸停損：
    除息日股價機械性下跌不是虧損，計算報酬時把股利加回現價）
    entry_date: YYYYMMDD
    """
    try:
        from data.finmind_fetcher import fetch_stock
        df = fetch_stock(stock_id, "dividend", force_refresh=refresh)
        if df.empty or "CashExDividendTradingDate" not in df.columns:
            return 0.0
        entry_iso = f"{entry_date[:4]}-{entry_date[4:6]}-{entry_date[6:]}"
        today_iso = datetime.now().strftime("%Y-%m-%d")
        mask = (df["CashExDividendTradingDate"].astype(str) > entry_iso) & \
               (df["CashExDividendTradingDate"].astype(str) <= today_iso)
        return float(pd.to_numeric(
            df.loc[mask, "CashEarningsDistribution"], errors="coerce").fillna(0).sum())
    except Exception as e:
        print(f"  [tracker] {stock_id} 股利查詢失敗：{e}")
        return 0.0


def load_positions() -> pd.DataFrame:
    if POSITIONS_PATH.exists():
        df = pd.read_csv(POSITIONS_PATH)
        df["stock_id"] = df["stock_id"].astype(str)
        if "peak_price" not in df.columns:   # 舊格式自動升級
            df["peak_price"] = df["entry_price"]
        return df
    return pd.DataFrame(columns=COLUMNS)


def run():
    today = datetime.now().strftime("%Y%m%d")
    pos   = load_positions()

    # 靜音時段（GitHub 延遲跑到凌晨）：不處理出場判斷，留到下一個正常時段
    # 才觸發，避免半夜推播；只有部位新增照常執行
    quiet = os.environ.get("SEND_LINE", "true").lower() == "false"

    # ── 1. 今日強力候選 → 開新虛擬部位（同檔已有 open/target 部位則跳過）──
    screener_path = Path(RESULTS_DIR) / f"{today}_screener.csv"
    if screener_path.exists():
        df = pd.read_csv(screener_path)
        strong = df[df["tier"] == "強力候選"]
        held   = set(pos[pos["status"].isin(["open", "target"])]["stock_id"])
        for _, r in strong.iterrows():
            sid = str(r["stock_id"])
            if sid in held:
                continue
            price = _last_close(sid)
            if price <= 0:
                continue
            pos = pd.concat([pos, pd.DataFrame([{
                "stock_id": sid, "entry_date": today, "entry_price": price,
                "peak_price": price, "status": "open",
                "exit_date": "", "exit_price": "",
                "ret_pct": "", "days_held": 0,
            }])], ignore_index=True)
            print(f"  [tracker] 新部位 {sid} @ {price}")

    # ── 2. 檢查所有未平倉部位（三段式出場）────────────────────────────────
    stop_pct   = SCREENER["position_stop_loss"]          # -0.07
    be_trig    = SCREENER["position_breakeven_trigger"]  # +0.10 → 保本
    trail_trig = SCREENER["position_trail_trigger"]      # +0.15 → 移動停損
    trail_pct  = SCREENER["position_trail_pct"]          # 峰值 -8%
    max_days   = SCREENER["position_max_days"]           # 20

    alerts = []
    for i, r in pos.iterrows():
        if quiet:
            break
        if r["status"] not in ("open", "target"):
            continue
        sid   = str(r["stock_id"])
        entry = float(r["entry_price"])
        now   = _last_close(sid)
        if now <= 0 or entry <= 0:
            continue

        # 除權息調整：持有期間配發的現金股利加回現價（含息報酬），
        # 除息缺口不會誤觸停損
        div = dividends_since(sid, str(r["entry_date"]))
        eff = now + div

        peak = max(float(r.get("peak_price") or entry), eff)
        pos.at[i, "peak_price"] = peak
        peak_ret = (peak - entry) / entry
        ret      = (eff - entry) / entry
        days     = int(r.get("days_held") or 0) + 1
        pos.at[i, "days_held"] = days
        label = line_bot.stock_label(sid)
        if div > 0:
            label += f"（+息{div:.1f}）"

        # 依峰值決定當前停損線（只上移不下移）
        if peak_ret >= trail_trig:
            stop_line, stage = peak * (1 - trail_pct), f"移動停損（峰值-{trail_pct*100:.0f}%）"
        elif peak_ret >= be_trig:
            stop_line, stage = entry, "保本停損（成本價）"
        else:
            stop_line, stage = entry * (1 + stop_pct), "固定停損（-7%）"

        if eff <= stop_line:
            pos.at[i, "status"]     = "stopped"
            pos.at[i, "exit_date"]  = today
            pos.at[i, "exit_price"] = now
            pos.at[i, "ret_pct"]    = round(ret * 100, 2)
            icon = "🛑" if ret < 0 else "💰"   # 移動停損出場多半是獲利了結
            alerts.append(f"{icon} {label}\n  {ret*100:+.1f}%（{r['entry_date']} 進場 {entry}）\n"
                          f"  觸發{stage}，建議出場")
        elif peak_ret >= trail_trig and r["status"] == "open":
            pos.at[i, "status"] = "target"   # 進入第三段，提醒一次
            watch_px = stop_line - div       # 換回市價基準的觀察價位
            alerts.append(f"🎯 {label}\n  {ret*100:+.1f}%（峰值 {peak_ret*100:+.1f}%）\n"
                          f"  已啟動移動停損：跌破 {watch_px:.1f} 出場，續抱讓獲利奔跑")
        elif days >= max_days:
            pos.at[i, "status"]     = "expired"
            pos.at[i, "exit_date"]  = today
            pos.at[i, "exit_price"] = now
            pos.at[i, "ret_pct"]    = round(ret * 100, 2)
            alerts.append(f"⏳ {label}\n  持有滿 {max_days} 交易日結算：{ret*100:+.1f}%")

    # ── 3. 存檔 + 推播 ───────────────────────────────────────────────────
    POSITIONS_PATH.parent.mkdir(exist_ok=True)
    pos.to_csv(POSITIONS_PATH, index=False, encoding="utf-8-sig")

    n_open = len(pos[pos["status"].isin(["open", "target"])])
    closed = pos[pos["status"].isin(["stopped", "expired"])]
    print(f"  [tracker] 持倉 {n_open} 檔 | 已結算 {len(closed)} 筆")

    if alerts:
        msg = (f"📢 持倉追蹤 {today[:4]}/{today[4:6]}/{today[6:]}\n"
               f"━━━━━━━━━━━━━━\n"
               + "\n\n".join(alerts)
               + f"\n\n目前追蹤 {n_open} 檔\n⚠️ 僅供參考，非投資建議")
        line_bot.send(msg)
        print(f"  [tracker] 已推播 {len(alerts)} 個出場訊號")
    else:
        print("  [tracker] 無出場訊號")


if __name__ == "__main__":
    run()
