#!/bin/bash
# ============================================================
# setup_crontab.sh
# 一鍵設定每日自動執行
# 執行：bash scripts/setup_crontab.sh
# ============================================================

PROJECT_DIR="$HOME/Desktop/股票系統/quant_tw"
SCRIPT="$PROJECT_DIR/scripts/run_daily.sh"

echo "=== 台股量化系統 crontab 設定 ==="
echo ""
echo "將設定：每週一到週五 下午 15:05 自動執行"
echo "（台股收盤 13:30，15:05 確保盤後資料已更新）"
echo ""

# 確認腳本存在
if [ ! -f "$SCRIPT" ]; then
    echo "錯誤：找不到 $SCRIPT"
    exit 1
fi

chmod +x "$SCRIPT"

# 讀取現有 crontab
CURRENT=$(crontab -l 2>/dev/null || echo "")

# 檢查是否已設定
if echo "$CURRENT" | grep -q "run_daily.sh"; then
    echo "⚠️  已有設定，先移除舊的..."
    CURRENT=$(echo "$CURRENT" | grep -v "run_daily.sh")
fi

# 加入新設定
NEW_JOB="5 15 * * 1-5 $SCRIPT"
if [ -z "$CURRENT" ]; then
    echo "$NEW_JOB" | crontab -
else
    (echo "$CURRENT"; echo "$NEW_JOB") | crontab -
fi

echo "✅ 設定完成！"
echo ""
echo "目前的 crontab："
crontab -l
echo ""
echo "Log 檔位置：$PROJECT_DIR/logs/YYYYMMDD_daily.log"
echo ""
echo "手動測試（現在跑一次）："
echo "  bash $SCRIPT"
