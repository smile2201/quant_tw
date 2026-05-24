#!/bin/bash
# 每日盤後一鍵執行
set -e
cd "$(dirname "$0")/.."
echo "=== $(date) 盤後更新開始 ==="
python scripts/update_cache.py
echo "=== 完成 ==="
