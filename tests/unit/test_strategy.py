"""
tests/unit/test_strategy.py
策略層單元測試 - 驗收 Playbook v2 用
全部使用 mock 資料，不打任何 API
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pandas as pd
import numpy as np
from strategy import technical_strategy as tech
from strategy import fundamental_strategy as fund
from strategy import event_strategy as event
from strategy import hybrid_screener as hybrid
from strategy import margin_strategy as margin
from strategy import news_strategy as news


# ─── Mock 資料工廠 ─────────────────────────────────────────────────────────────

def make_price_df(n=120, trend="up") -> pd.DataFrame:
    """產生模擬日K資料"""
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    base  = 100.0
    if trend == "up":
        closes = base + np.cumsum(np.random.uniform(0, 1, n))
    elif trend == "down":
        closes = base + np.cumsum(np.random.uniform(-1, 0, n))
    else:
        closes = base + np.random.uniform(-1, 1, n).cumsum()

    return pd.DataFrame({
        "date":           dates.strftime("%Y-%m-%d"),
        "open":           closes * 0.99,
        "high":           closes * 1.02,
        "low":            closes * 0.98,
        "close":          closes,
        "Trading_Volume": np.random.randint(5000, 20000, n),
    })


def make_financial_df() -> pd.DataFrame:
    """產生模擬財務比率資料（含EPS成長）"""
    return pd.DataFrame({
        "date": pd.date_range("2022-01-01", periods=8, freq="QS").strftime("%Y-%m-%d"),
        "EPS":  [1.0, 1.1, 1.2, 1.3, 1.25, 1.4, 1.5, 1.6],
    })


def make_dividend_df() -> pd.DataFrame:
    """產生模擬股利資料"""
    return pd.DataFrame({
        "date":                       ["2022-01-01", "2023-01-01", "2024-01-01"],
        "CashEarningsDistribution":   [2.5, 3.0, 3.5],
        "dividend_yield":             [4.5, 5.0, 5.5],
    })


def make_revenue_df() -> pd.DataFrame:
    """產生模擬月營收資料（連續成長）"""
    dates   = pd.date_range("2022-01-01", periods=14, freq="MS")
    revenue = [1000 * (1.01 ** i) for i in range(14)]
    return pd.DataFrame({
        "date":    dates.strftime("%Y-%m-%d"),
        "revenue": revenue,
    })


def make_news_df(stock_id: str, subject: str) -> pd.DataFrame:
    """產生模擬重大訊息"""
    return pd.DataFrame({
        "公司代號": [stock_id],
        "公司名稱": ["測試股"],
        "主旨":    [subject],
        "說明":    ["測試說明"],
    })


# ─── 技術面測試 ────────────────────────────────────────────────────────────────

def test_tech_score_range():
    """技術面評分應在 0~100"""
    df    = make_price_df(120, "up")
    score = tech.score_stock(df)
    assert 0 <= score <= 100, f"got {score}"


def test_tech_uptrend_higher_than_down():
    """上升趨勢評分應高於下降趨勢"""
    up_score   = tech.score_stock(make_price_df(120, "up"))
    down_score = tech.score_stock(make_price_df(120, "down"))
    assert up_score >= down_score, f"up={up_score}, down={down_score}"


def test_tech_short_data_returns_zero():
    """資料不足60筆應回傳0"""
    df = make_price_df(30, "up")
    assert tech.score_stock(df) == 0.0


def test_tech_run_output_format():
    """run() 應輸出含 stock_id, tech_score, signals 的 DataFrame"""
    price_data = {"2330": make_price_df(120, "up")}
    result = tech.run(price_data)
    assert "stock_id"   in result.columns
    assert "tech_score" in result.columns
    assert "signals"    in result.columns
    assert len(result) == 1


def test_tech_macd_indicators():
    """MACD 指標欄位應正確產生"""
    df  = tech.add_macd(make_price_df(120))
    assert "macd"        in df.columns
    assert "macd_signal" in df.columns
    assert "macd_hist"   in df.columns
    assert not df["macd"].iloc[-1:].isna().all()


# ─── 基本面測試 ────────────────────────────────────────────────────────────────

def test_fund_eps_growth():
    """EPS 成長股應有正分"""
    score = fund.score_eps(make_financial_df())
    assert score > 0, f"got {score}"


def test_fund_eps_no_loss():
    """虧損股 EPS 分數應低"""
    df = pd.DataFrame({
        "date": pd.date_range("2022-01-01", periods=8, freq="QS").strftime("%Y-%m-%d"),
        "EPS":  [-0.5, -0.3, 0.1, -0.2, -0.4, 0.2, -0.1, 0.3],
    })
    score = fund.score_eps(df)
    assert score < 15, f"虧損股不應有高分，got {score}"


def test_fund_dividend_continuous():
    """連續配息股應有分"""
    score = fund.score_dividend(make_dividend_df())
    assert score > 0, f"got {score}"


def test_fund_revenue_growth():
    """連續成長月營收應有分"""
    score = fund.score_revenue(make_revenue_df())
    assert score > 0, f"got {score}"


def test_fund_score_range():
    """基本面評分應在 0~100"""
    score = fund.score_stock(make_financial_df(), make_dividend_df(), make_revenue_df())
    assert 0 <= score <= 100, f"got {score}"


def test_fund_empty_data():
    """空資料應回傳0分"""
    assert fund.score_stock(pd.DataFrame(), pd.DataFrame(), pd.DataFrame()) == 0.0


def test_fund_run_output_format():
    """run() 應輸出含必要欄位的 DataFrame"""
    data = {"2330": {
        "financial": make_financial_df(),
        "dividend":  make_dividend_df(),
        "revenue":   make_revenue_df(),
    }}
    result = fund.run(data)
    for col in ["stock_id", "fund_score", "eps_score", "div_score", "rev_score"]:
        assert col in result.columns, f"缺少欄位: {col}"


# ─── 事件驅動測試 ──────────────────────────────────────────────────────────────

def test_event_positive_keyword():
    """正面關鍵字應有正面分數"""
    etype, score = event.classify_event("取得重大合約")
    assert etype == "positive", f"got {etype}"
    assert score > 0, f"got {score}"


def test_event_negative_keyword():
    """負面關鍵字應有負面分數"""
    etype, score = event.classify_event("發生財務困難")
    assert etype == "negative", f"got {etype}"
    assert score < 0, f"got {score}"


def test_event_neutral():
    """無關鍵字應為中性"""
    etype, score = event.classify_event("召開股東常會")
    assert etype == "neutral"
    assert score == 0


def test_event_run_no_news():
    """無重大訊息時，事件評分應為50（中性）"""
    result = event.run(pd.DataFrame(), ["2330"])
    assert result.iloc[0]["event_score"] == 50.0


def test_event_run_positive_news():
    """正面新聞股事件分應高於50"""
    news = make_news_df("2330", "取得重大合約 簽約金額達新台幣10億元")
    result = event.run(news, ["2330"])
    assert result.iloc[0]["event_score"] > 50, f"got {result.iloc[0]['event_score']}"


def test_event_run_negative_news():
    """負面新聞股事件分應低於50"""
    news = make_news_df("2330", "發生財務困難 向法院聲請重整")
    result = event.run(news, ["2330"])
    assert result.iloc[0]["event_score"] < 50, f"got {result.iloc[0]['event_score']}"


# ─── 混合評分器測試 ────────────────────────────────────────────────────────────

def test_hybrid_score_range():
    """混合評分應在 0~100"""
    price_data = {"2330": make_price_df(120, "up")}
    fund_data  = {"2330": {"financial": make_financial_df(),
                           "dividend":  make_dividend_df(),
                           "revenue":   make_revenue_df()}}
    news_df    = make_news_df("2330", "取得重大合約")
    result = hybrid.run(price_data, fund_data, news_df)
    score = result.iloc[0]["final_score"]
    assert 0 <= score <= 100, f"got {score}"


def test_hybrid_tier_labels():
    """tier 欄位應只有三種值"""
    price_data = {"2330": make_price_df(120, "up"),
                  "2317": make_price_df(120, "down")}
    fund_data  = {sid: {"financial": pd.DataFrame(),
                        "dividend":  pd.DataFrame(),
                        "revenue":   pd.DataFrame()} for sid in price_data}
    result = hybrid.run(price_data, fund_data, pd.DataFrame())
    valid_tiers = {"強力候選", "觀察股", "普通"}
    assert set(result["tier"]).issubset(valid_tiers)


def test_hybrid_ablation_tech_only():
    """只開技術面時，final_score 應等於 tech_score"""
    price_data = {"2330": make_price_df(120, "up")}
    fund_data  = {"2330": {"financial": make_financial_df(),
                           "dividend":  make_dividend_df(),
                           "revenue":   make_revenue_df()}}
    # 明確關掉其他模組（含 chip），避免 neutral=50 混入
    r_tech_only = hybrid.run(price_data, fund_data, pd.DataFrame(),
                              use_tech=True, use_fund=False,
                              use_event=False, use_chip=False)
    t = r_tech_only.iloc[0]
    assert abs(t["final_score"] - t["tech_score"]) < 0.2, \
        f"tech only: final={t['final_score']}, tech={t['tech_score']}"


def test_hybrid_old_strategies_unaffected():
    """新增事件模組後，技術和基本面評分結果不應改變"""
    price_data = {"2330": make_price_df(120, "up")}
    fund_data  = {"2330": {"financial": make_financial_df(),
                           "dividend":  make_dividend_df(),
                           "revenue":   make_revenue_df()}}
    tech_result1 = tech.run(price_data)
    fund_result1 = fund.run(fund_data)
    # 跑完 hybrid 後再跑，結果應一致
    hybrid.run(price_data, fund_data, pd.DataFrame())
    tech_result2 = tech.run(price_data)
    fund_result2 = fund.run(fund_data)
    assert tech_result1.iloc[0]["tech_score"] == tech_result2.iloc[0]["tech_score"]
    assert fund_result1.iloc[0]["fund_score"] == fund_result2.iloc[0]["fund_score"]


def make_margin_df(n=20, mp_today=500_000, ss_today=40_000,
                   mp_limit=2_000_000) -> pd.DataFrame:
    """產生模擬融資融券資料"""
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    base  = mp_today
    # 欄位名稱與 FinMind TaiwanStockMarginPurchaseShortSale 實際回傳一致
    return pd.DataFrame({
        "date":                       [d.strftime("%Y-%m-%d") for d in dates],
        "MarginPurchaseTodayBalance": [int(base * (1 + i * 0.01)) for i in range(n)],
        "ShortSaleTodayBalance":      [ss_today] * n,
        "MarginPurchaseLimit":        [mp_limit] * n,
    })


# ─── 融資融券測試 ──────────────────────────────────────────────────────────────

def test_margin_score_range():
    """融資融券評分應在 0~100"""
    df    = make_margin_df()
    score, _ = margin.score_margin(df)
    assert 0 <= score <= 100, f"got {score}"


def test_margin_low_short_ratio_bullish():
    """低券資比（< 0.10）應得高分"""
    df = make_margin_df(mp_today=1_000_000, ss_today=50_000)  # ratio=0.05
    score, sigs = margin.score_margin(df)
    assert score > 60, f"低券資比應高分，got {score}"
    assert any("↓低" in s for s in sigs), "應有低券資比訊號"


def test_margin_high_short_ratio_bearish():
    """高券資比（> 0.25）應得低分"""
    df = make_margin_df(mp_today=1_000_000, ss_today=300_000)  # ratio=0.30
    score, sigs = margin.score_margin(df)
    assert score < 50, f"高券資比應低分，got {score}"


def test_margin_empty_returns_neutral():
    """空資料應回傳 50（中性）"""
    score, sigs = margin.score_margin(pd.DataFrame())
    assert score == 50.0
    assert sigs == []


def test_margin_run_output_format():
    """run() 應輸出含必要欄位的 DataFrame"""
    margin_data = {"2330": make_margin_df(), "2317": pd.DataFrame()}
    result = margin.run(margin_data, ["2330", "2317"])
    assert "stock_id"       in result.columns
    assert "margin_score"   in result.columns
    assert "margin_signals" in result.columns
    assert len(result) == 2


def test_margin_integrated_into_chip():
    """hybrid.run 傳入 margin_data 後 chip_score 應有所改變"""
    price_data  = {"2330": make_price_df(120, "up")}
    fund_data   = {"2330": {"financial": pd.DataFrame(),
                            "dividend":  pd.DataFrame(),
                            "revenue":   pd.DataFrame()}}
    margin_data = {"2330": make_margin_df(mp_today=1_000_000, ss_today=50_000)}

    r_no_margin = hybrid.run(price_data, fund_data, pd.DataFrame())
    r_w_margin  = hybrid.run(price_data, fund_data, pd.DataFrame(),
                             margin_data=margin_data)

    chip_no = r_no_margin.iloc[0]["chip_score"]
    chip_w  = r_w_margin.iloc[0]["chip_score"]
    # 加了低券資比的融資資料後，籌碼分應提高
    assert chip_w >= chip_no, f"有融資資料({chip_w}) 應 >= 無融資資料({chip_no})"


# ─── 新聞情緒測試 ──────────────────────────────────────────────────────────────

def test_news_positive_keywords():
    """正面關鍵字新聞應得高分"""
    news_list = [{"title": "台積電取得重大合約，目標價上調", "publishTime": 0}]
    score, sig = news.score_news(news_list)
    assert score > 50, f"正面新聞應高分，got {score}"


def test_news_negative_keywords():
    """負面關鍵字新聞應得低分"""
    news_list = [{"title": "公司發生財務困難，財報虧損", "publishTime": 0}]
    score, sig = news.score_news(news_list)
    assert score < 50, f"負面新聞應低分，got {score}"


def test_news_empty_returns_neutral():
    """無新聞應回傳 50（中性）且無訊號"""
    score, sig = news.score_news([])
    assert score == 50.0
    assert sig == ""


def test_news_neutral_no_signal():
    """無關鍵字新聞應為中性，不顯示訊號"""
    news_list = [{"title": "公司召開股東常會", "publishTime": 0}]
    score, sig = news.score_news(news_list)
    assert sig == "", f"無關鍵字不應顯示訊號，got '{sig}'"


def test_news_run_output_format():
    """run() 應輸出含必要欄位的 DataFrame"""
    news_data = {
        "2330": [{"title": "取得重大合約", "publishTime": 0}],
        "2317": [],
    }
    result = news.run(news_data, ["2330", "2317"])
    assert "stock_id"    in result.columns
    assert "news_score"  in result.columns
    assert "news_signal" in result.columns
    assert len(result) == 2


def test_hybrid_new_columns_present():
    """hybrid.run() 結果應含新增欄位"""
    price_data = {"2330": make_price_df(120, "up")}
    fund_data  = {"2330": {"financial": pd.DataFrame(),
                           "dividend":  pd.DataFrame(),
                           "revenue":   pd.DataFrame()}}
    result = hybrid.run(price_data, fund_data, pd.DataFrame(),
                        macro_context="🌐 VIX 18.5 低波動")
    assert "macro_context"  in result.columns
    assert "margin_score"   in result.columns
    assert "insider_signal" in result.columns
    assert result.iloc[0]["macro_context"] == "🌐 VIX 18.5 低波動"


# ─── 執行 ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_tech_score_range,
        test_tech_uptrend_higher_than_down,
        test_tech_short_data_returns_zero,
        test_tech_run_output_format,
        test_tech_macd_indicators,
        test_fund_eps_growth,
        test_fund_eps_no_loss,
        test_fund_dividend_continuous,
        test_fund_revenue_growth,
        test_fund_score_range,
        test_fund_empty_data,
        test_fund_run_output_format,
        test_event_positive_keyword,
        test_event_negative_keyword,
        test_event_neutral,
        test_event_run_no_news,
        test_event_run_positive_news,
        test_event_run_negative_news,
        test_hybrid_score_range,
        test_hybrid_tier_labels,
        test_hybrid_ablation_tech_only,
        test_hybrid_old_strategies_unaffected,
        # 新模組
        test_margin_score_range,
        test_margin_low_short_ratio_bullish,
        test_margin_high_short_ratio_bearish,
        test_margin_empty_returns_neutral,
        test_margin_run_output_format,
        test_margin_integrated_into_chip,
        test_news_positive_keywords,
        test_news_negative_keywords,
        test_news_empty_returns_neutral,
        test_news_neutral_no_signal,
        test_news_run_output_format,
        test_hybrid_new_columns_present,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  ✅ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
