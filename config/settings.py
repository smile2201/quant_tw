"""
config/settings.py
所有參數集中管理，改一處不散到各檔
"""
import os

# ╔══════════════════════════════════════════════════════════════════╗
# ║  FinMind 付費設定區（升級後只改這裡，其他不用動）                ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  免費帳號（register）：                                          ║
# ║    FINMIND_PLAN          = "register"                            ║
# ║    FINMIND_PRICE_DATASET = "price"      ← 一般股價（無還原）     ║
# ║    FINMIND_RATE_LIMIT    = 600          ← 600次/小時             ║
# ║                                                                  ║
# ║  付費帳號（sponsor）：                                           ║
# ║    FINMIND_PLAN          = "sponsor"                             ║
# ║    FINMIND_PRICE_DATASET = "price_adj"  ← 還原股價（回測更準）   ║
# ║    FINMIND_RATE_LIMIT    = 6000         ← 6000次/小時            ║
# ╚══════════════════════════════════════════════════════════════════╝

FINMIND_PLAN          = "register"   # 升級後改成 "sponsor"
FINMIND_PRICE_DATASET = "price"      # 升級後改成 "price_adj"
FINMIND_RATE_LIMIT    = 600          # 升級後改成 6000

# ─── 環境偵測（自動判斷本機 or Colab）─────────────────────────────────────────
IS_COLAB = os.path.exists("/content/drive")

# ─── 路徑設定 ─────────────────────────────────────────────────────────────────
if IS_COLAB:
    PROJECT_ROOT = "/content/quant_tw"
    CACHE_ROOT   = "/content/drive/MyDrive/quant_cache"
else:
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    CACHE_ROOT   = os.path.join(PROJECT_ROOT, "data", "cache")

TWSE_DATA_DIR    = os.path.join(PROJECT_ROOT, "data", "twse")
EMPTY_MARKER_DIR = os.path.join(PROJECT_ROOT, "data", "empty_markers")
RESULTS_DIR      = os.path.join(PROJECT_ROOT, "results")

# ─── FinMind API ──────────────────────────────────────────────────────────────
# token 從環境變數讀取，不寫死在程式碼
# 設定方式：export FINMIND_TOKEN="你的token"
FINMIND_TOKEN   = os.environ.get("FINMIND_TOKEN", "")
FINMIND_BACKOFF = 65 * 60      # quota 用盡後退避秒數（65分鐘）
CACHE_YEARS     = 3            # 一次抓幾年資料存 cache

# ─── SCREENER 參數 ────────────────────────────────────────────────────────────
SCREENER = {
    # 混合評分權重（四者加總 = 1.0）
    # 2026-07-23 依 45 日成效驗證調整：chip 與報酬相關 +0.17（唯一有效），
    # fund/event 近零 → 加重籌碼、調降基本面。樣本仍少，每月重跑
    # verify_performance.py 檢視，勿再憑感覺調
    "weight_technical":    0.30,
    "weight_fundamental":  0.20,
    "weight_event":        0.15,
    "weight_chip":         0.35,  # 籌碼面（三大法人+融資融券）

    # 評分門檻（免費方案：financial 拿不到，分數普遍偏低）
    # 40 時觀察股高達 30+ 檔沒有篩選效果，2026-07 調高到 46
    # 升級付費後改回 60/75
    "threshold_watch":     46,    # 觀察股
    "threshold_strong":    55,    # 強力候選

    # 技術面指標參數
    "ma_short":            5,
    "ma_long":             20,
    "volume_ratio":        1.5,   # 成交量 > 均量 N 倍才算突破
    "breakout_days":       20,    # N日高點突破
    "rsi_oversold":        30,
    "rsi_overbought":      70,
    # KD 指標（隨機震盪指標）
    "kd_period":           9,     # KD 計算天期
    "kd_oversold":         20,    # K < 20 視為超賣
    "kd_overbought":       80,    # K > 80 視為超買
    # 布林通道
    "bb_period":           20,    # 布林通道天期
    "bb_std":              2.0,   # 標準差倍數

    # 基本面篩選門檻
    "eps_growth_min":      0.15,  # EPS 年增率 > 15%
    "dividend_yield_min":  0.04,  # 殖利率 > 4%
    "revenue_growth_min":  0.10,  # 月營收年增率 > 10%
    "pe_max":              15,    # 本益比上限

    # 籌碼面（三大法人）參數
    "chip_lookback_days":  5,     # 觀察近 N 日買賣超
    "chip_streak_min":     3,     # 連買 N 天以上才給滿分
    # 籌碼面整合融資融券後的混合權重
    "chip_weight_inst":    0.6,   # 三大法人佔籌碼分比重
    "chip_weight_margin":  0.4,   # 融資融券佔籌碼分比重

    # 融資融券參數
    "margin_short_ratio_low":      0.10,  # 券資比低點（低於此 = 偏多）
    "margin_short_ratio_high":     0.25,  # 券資比高點（高於此 = 偏空）
    "margin_change_healthy_min":   0.05,  # 融資健康增幅下限
    "margin_change_healthy_max":   0.20,  # 融資健康增幅上限
    "margin_usage_low":            0.25,  # 融資使用率低（籌碼乾淨）
    "margin_usage_high":           0.60,  # 融資使用率高（壓力大）

    # 盤中突破通知參數
    "intraday_breakout_days": 20,   # N 日高點突破
    "intraday_volume_ratio":  2.0,  # 爆量倍數門檻

    # 事件驅動關鍵字
    "positive_keywords":   ["重大合約", "法說會", "獲利", "轉盈", "創新高"],
    "negative_keywords":   ["財務困難", "裁罰", "虧損", "重大虧損", "下市"],
}

# ─── BACKTEST 參數 ────────────────────────────────────────────────────────────
BACKTEST = {
    "start_date":      "2022-01-01",
    "end_date":        "2024-12-31",
    "initial_capital": 1_000_000,   # 初始資金（新台幣）
    "risk_free_rate":  0.015,       # 無風險利率 1.5%（計算 Sharpe 用）

    # 股票池（預設用台灣50成分股，避免全市場跑太慢）
    "universe":        "tw50",      # 可改 "all"（全市場）或自訂 list
    "max_positions":   10,          # 最多同時持有幾檔
    "position_size":   0.1,         # 每檔佔總資金比例（10%）
}

# ─── EXECUTION 參數 ───────────────────────────────────────────────────────────
EXECUTION = {
    # 手續費
    "commission_buy":            0.001425,  # 買進手續費 0.1425%
    "commission_sell":           0.001425,  # 賣出手續費 0.1425%
    "tax_sell":                  0.003,     # 證交稅 0.3%（賣出時）

    # 滑價（不對稱）
    "slippage_buy":              0.002,     # 買進 0.2%
    "slippage_sell":             0.003,     # 賣出 0.3%

    # 部位上限（流動性保護）
    "max_volume_ratio":          0.005,     # 單筆部位 ≤ 當日成交量 0.5%

    # 三模式倍率
    "ideal_slippage_mult":       0.0,       # ideal = 無滑價
    "pessimistic_slippage_mult": 1.5,       # pessimistic = 滑價 × 1.5
}

# ─── RUNNER 參數 ──────────────────────────────────────────────────────────────
RUNNER = {
    # Mac 雙核心 → 保留1核給系統，用1核跑運算
    # Colab 環境自動切換為2核
    "workers": 1 if not IS_COLAB else 2,
}
