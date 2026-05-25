#!/bin/bash
# ============================================================
# setup_github.sh
# 一鍵設定 GitHub 遠端 repo
# 執行前：先在 GitHub 網站建立一個 private repo
# 執行：bash scripts/setup_github.sh
# ============================================================

echo "=== GitHub 設定指引 ==="
echo ""
echo "步驟 1：到 github.com 建立一個新的 Private repo"
echo "  ✓ 名稱建議：quant_tw"
echo "  ✓ 設為 Private（重要！）"
echo "  ✓ 不要勾選 Initialize this repository"
echo ""
read -p "建好後，請輸入你的 GitHub repo URL（例如 https://github.com/yourname/quant_tw）：" REPO_URL

if [ -z "$REPO_URL" ]; then
    echo "錯誤：URL 不能為空"
    exit 1
fi

cd "$HOME/Desktop/股票系統/quant_tw"

echo ""
echo "步驟 2：設定遠端 repo..."
git remote remove origin 2>/dev/null || true
git remote add origin "$REPO_URL"
echo "✅ 遠端 repo 設定完成"

echo ""
echo "步驟 3：推送程式碼..."
git push -u origin main
echo "✅ 程式碼已推送"

echo ""
echo "=== 下一步：設定 GitHub Secrets ==="
echo ""
echo "到 GitHub repo → Settings → Secrets and variables → Actions"
echo "點「New repository secret」，加入："
echo ""
echo "  名稱：FINMIND_TOKEN"
echo "  值：你的 FinMind token（JWT 長串）"
echo ""
echo "=== 下一步：設定 Streamlit Cloud ==="
echo ""
echo "1. 到 share.streamlit.io 用 GitHub 帳號登入"
echo "2. 點「New app」"
echo "3. 選擇你的 repo：quant_tw"
echo "4. Main file path：dashboard.py"
echo "5. 在 Advanced settings → Secrets 加入："
echo "   DASHBOARD_PASSWORD = 你想設的密碼"
echo "6. 點 Deploy"
echo ""
echo "部署完成後會得到一個固定網址，例如："
echo "  https://yourname-quant-tw-dashboard-xxxxx.streamlit.app"
echo ""
echo "這個網址隨時可以開，手機電腦都能用。"
