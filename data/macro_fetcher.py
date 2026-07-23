"""
data/macro_fetcher.py
總體經濟指標（完全免費，無 API key）
- VIX 美股波動指數：Yahoo Finance
- Fed 聯邦基金利率：FRED 公開 CSV
- 外資台指期淨多單：FinMind TaiwanFuturesInstitutionalInvestors
"""
import requests
import pandas as pd
from datetime import datetime, timedelta

from config.settings import FINMIND_TOKEN

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; quant_tw/1.0)"}


def fetch_vix() -> dict:
    """Yahoo Finance 抓 VIX 最新報價"""
    try:
        url  = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        meta = resp.json()["chart"]["result"][0]["meta"]
        vix  = meta.get("regularMarketPrice", 0)
        prev = meta.get("chartPreviousClose", vix)

        if vix < 20:
            level = "低波動"
        elif vix < 30:
            level = "中波動"
        else:
            level = "⚠️高波動"

        return {"vix": round(vix, 2), "level": level, "change": round(vix - prev, 2)}
    except Exception as e:
        print(f"  [macro] VIX 失敗：{e}")
        return {}


def fetch_fed_rate() -> dict:
    """FRED 公開 CSV 抓聯邦基金利率；失敗時退回 Yahoo ^IRX（13週國庫券，近似值）"""
    try:
        url  = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS"
        resp = requests.get(url, headers=HEADERS, timeout=30)
        rows = [r.split(",") for r in resp.text.strip().split("\n")[1:] if r.strip()]
        if len(rows) >= 3:
            latest_rate = float(rows[-1][1])
            prev_rate   = float(rows[-2][1])

            if latest_rate > prev_rate:
                trend = "升息"
            elif latest_rate < prev_rate:
                trend = "降息"
            else:
                trend = "持平"

            return {"rate": latest_rate, "trend": trend, "date": rows[-1][0]}
    except Exception as e:
        print(f"  [macro] FRED 失敗，改用 Yahoo ^IRX：{e}")

    # fallback：^IRX 13週國庫券殖利率，與 Fed funds rate 高度連動
    try:
        url  = "https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        meta = resp.json()["chart"]["result"][0]["meta"]
        rate = meta.get("regularMarketPrice", 0)
        prev = meta.get("chartPreviousClose", rate)
        trend = "升" if rate > prev else ("降" if rate < prev else "持平")
        return {"rate": round(rate, 2), "trend": f"短率{trend}", "date": ""}
    except Exception as e:
        print(f"  [macro] Fed 利率失敗：{e}")
        return {}


def fetch_tw_futures_foreign() -> dict:
    """
    FinMind 抓外資台指期（TX）淨未平倉口數
    dataset: TaiwanFuturesInstitutionalInvestors，data_id: TX
    """
    try:
        end   = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

        params  = {
            "dataset":    "TaiwanFuturesInstitutionalInvestors",
            "data_id":    "TX",
            "start_date": start,
            "end_date":   end,
        }
        hdrs = dict(HEADERS)
        if FINMIND_TOKEN:
            hdrs["Authorization"] = f"Bearer {FINMIND_TOKEN}"

        resp = requests.get(
            "https://api.finmindtrade.com/api/v4/data",
            headers=hdrs, params=params, timeout=15,
        )
        data = resp.json()
        if data.get("status") != 200 or not data.get("data"):
            return {}

        df      = pd.DataFrame(data["data"])
        inv_col = "institutional_investors" if "institutional_investors" in df.columns else "name"
        foreign = df[df[inv_col].str.contains("外資|Foreign", na=False)]
        if foreign.empty:
            return {}

        latest   = foreign.sort_values("date").iloc[-1]
        long_oi  = pd.to_numeric(latest.get("long_open_interest_balance_volume", 0),
                                 errors="coerce") or 0
        short_oi = pd.to_numeric(latest.get("short_open_interest_balance_volume", 0),
                                 errors="coerce") or 0
        net_oi   = int(long_oi - short_oi)

        threshold = 5000
        if net_oi > threshold:
            signal = "🟢 偏多"
        elif net_oi > 0:
            signal = "↗ 略多"
        elif net_oi > -threshold:
            signal = "↘ 略空"
        else:
            signal = "🔴 偏空"

        return {"net_oi": net_oi, "signal": signal, "date": str(latest.get("date", ""))}
    except Exception as e:
        print(f"  [macro] 期貨籌碼失敗：{e}")
        return {}


def build_context(vix: dict, fed: dict, futures: dict) -> str:
    """組合成 LINE 通知用的一行大盤摘要"""
    parts = []

    if futures:
        net = futures.get("net_oi", 0)
        sig = futures.get("signal", "")
        parts.append(f"外資期貨{net:+,}口 {sig}")

    if vix:
        parts.append(f"VIX {vix.get('vix','')} {vix.get('level','')}")

    if fed:
        parts.append(f"Fed {fed.get('rate','')}% {fed.get('trend','')}")

    return ("🌐 " + " | ".join(parts)) if parts else ""
