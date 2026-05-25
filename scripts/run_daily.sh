#!/bin/bash
# ============================================================
# run_daily.sh
# 台股量化系統 — 每日盤後自動執行
# crontab 設定：0 15 * * 1-5 (週一~五 下午3點執行)
# ============================================================

set -e

# ── 路徑設定 ─────────────────────────────────────────────────
PROJECT_DIR="$HOME/Desktop/股票系統/quant_tw"
LOG_DIR="$PROJECT_DIR/logs"
TODAY=$(date +%Y%m%d)
LOG_FILE="$LOG_DIR/${TODAY}_daily.log"

mkdir -p "$LOG_DIR"

# ── 所有輸出寫入 log ─────────────────────────────────────────
exec >> "$LOG_FILE" 2>&1

echo "========================================"
echo "開始時間：$(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"

cd "$PROJECT_DIR"

# ── 載入環境變數（含 FINMIND_TOKEN）────────────────────────
source "$HOME/.zshrc" 2>/dev/null || true

PYTHON=$(which python3)
echo "Python：$PYTHON"

# ── Step 1：更新資料 ─────────────────────────────────────────
echo ""
echo "── Step 1：更新 TWSE + FinMind cache ──"
$PYTHON scripts/update_cache.py
echo "Step 1 完成"

# ── Step 2：執行選股評分 ─────────────────────────────────────
echo ""
echo "── Step 2：選股評分 ──"
$PYTHON scripts/run_screener.py
echo "Step 2 完成"

# ── Step 3：結果摘要 ─────────────────────────────────────────
echo ""
echo "── Step 3：結果摘要 ──"
LATEST_CSV=$(ls -t "$PROJECT_DIR/results/"*screener*.csv 2>/dev/null | head -1)
if [ -n "$LATEST_CSV" ]; then
    $PYTHON - << 'PYEOF'
import pandas as pd, sys, os
csv = sorted([f for f in os.listdir(os.path.expanduser("~/Desktop/股票系統/quant_tw/results")) if "screener" in f], reverse=True)
if not csv: sys.exit(0)
df = pd.read_csv(f"{os.path.expanduser('~')}/Desktop/股票系統/quant_tw/results/{csv[0]}")
strong = df[df['tier']=='強力候選']
watch  = df[df['tier']=='觀察股']
print(f"強力候選（{len(strong)}檔）：{' '.join(strong['stock_id'].tolist())}")
print(f"觀察股  （{len(watch)}檔）：{' '.join(watch['stock_id'].tolist()[:10])}")
PYEOF
fi

echo ""
echo "========================================"
echo "完成時間：$(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"
