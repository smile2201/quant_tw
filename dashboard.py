"""
dashboard.py
台股量化系統操作面板
執行：streamlit run dashboard.py
"""
import sys, os, json, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
from pathlib import Path
from datetime import datetime

# ─── 頁面設定 ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="台股量化系統",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── 路徑常數 ─────────────────────────────────────────────────────────────────
PROJECT_ROOT  = Path(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.py"
CACHE_DIR     = PROJECT_ROOT / "data" / "cache"
TWSE_DIR      = PROJECT_ROOT / "data" / "twse"
RESULTS_DIR   = PROJECT_ROOT / "results"
EMPTY_DIR     = PROJECT_ROOT / "data" / "empty_markers"

# ─── 讀/寫 settings.py 中的付費設定區 ────────────────────────────────────────

def read_current_plan() -> dict:
    """從 settings.py 讀取目前方案設定"""
    text = SETTINGS_PATH.read_text()
    plan     = "register"
    dataset  = "price"
    rate     = 600
    for line in text.splitlines():
        if line.startswith("FINMIND_PLAN"):
            plan = line.split("=")[1].split("#")[0].strip().strip('"').strip("'")
        elif line.startswith("FINMIND_PRICE_DATASET"):
            dataset = line.split("=")[1].split("#")[0].strip().strip('"').strip("'")
        elif line.startswith("FINMIND_RATE_LIMIT"):
            try:
                rate = int(line.split("=")[1].split("#")[0].strip())
            except Exception:
                pass
    return {"plan": plan, "dataset": dataset, "rate_limit": rate}


def write_plan(plan: str):
    """把 settings.py 中的三行改成對應方案"""
    if plan == "sponsor":
        new_vals = {
            "FINMIND_PLAN":          '"sponsor"',
            "FINMIND_PRICE_DATASET": '"price_adj"',
            "FINMIND_RATE_LIMIT":    "6000",
        }
    else:
        new_vals = {
            "FINMIND_PLAN":          '"register"',
            "FINMIND_PRICE_DATASET": '"price"',
            "FINMIND_RATE_LIMIT":    "600",
        }

    text  = SETTINGS_PATH.read_text()
    lines = text.splitlines()
    new_lines = []
    for line in lines:
        replaced = False
        for key, val in new_vals.items():
            if line.startswith(key):
                comment = ""
                if "#" in line:
                    comment = "  " + line[line.index("#"):]
                new_lines.append(f"{key:<24} = {val}{comment}")
                replaced = True
                break
        if not replaced:
            new_lines.append(line)
    SETTINGS_PATH.write_text("\n".join(new_lines))


# ─── 快取統計 ─────────────────────────────────────────────────────────────────

def get_cache_stats() -> dict:
    """統計各 dataset 已快取的股票數量"""
    stats = {}
    if not CACHE_DIR.exists():
        return stats
    for d in sorted(CACHE_DIR.iterdir()):
        if d.is_dir():
            count = len(list(d.glob("*.parquet")))
            stats[d.name] = count
    return stats


def get_empty_stats() -> dict:
    stats = {}
    if not EMPTY_DIR.exists():
        return stats
    for d in sorted(EMPTY_DIR.iterdir()):
        if d.is_dir():
            count = len(list(d.glob("*.empty")))
            stats[d.name] = count
    return stats


def get_twse_files() -> list:
    if not TWSE_DIR.exists():
        return []
    files = sorted(TWSE_DIR.glob("*.json"), reverse=True)
    result = []
    for f in files[:10]:
        size = f.stat().st_size / 1024
        result.append({"檔案": f.name, "大小": f"{size:.1f} KB"})
    return result


def get_results() -> list:
    if not RESULTS_DIR.exists():
        return []
    files = sorted(RESULTS_DIR.glob("*.csv"), reverse=True)
    result = []
    for f in files[:10]:
        result.append({"檔案": f.name, "時間": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")})
    return result


# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📈 台股量化系統")
    st.markdown("---")
    page = st.radio(
        "導航",
        ["🏠 系統狀態", "⚙️ 方案設定", "📁 資料狀態", "📊 回測結果", "▶️ 執行腳本"],
        label_visibility="collapsed",
    )
    st.markdown("---")

    cfg = read_current_plan()
    if cfg["plan"] == "sponsor":
        st.success("💎 付費方案")
    else:
        st.info("🆓 免費方案")
    st.caption(f"資料集：`{cfg['dataset']}`")
    st.caption(f"速率上限：{cfg['rate_limit']} 次/hr")


# ═══════════════════════════════════════════════════════════════════════════════
# 頁面：系統狀態
# ═══════════════════════════════════════════════════════════════════════════════
if page == "🏠 系統狀態":
    st.title("🏠 系統狀態")

    cfg = read_current_plan()
    cache_stats  = get_cache_stats()
    empty_stats  = get_empty_stats()
    total_cached = sum(cache_stats.values())
    results      = get_results()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        plan_label = "💎 付費" if cfg["plan"] == "sponsor" else "🆓 免費"
        st.metric("方案", plan_label)
    with c2:
        st.metric("資料集", cfg["dataset"])
    with c3:
        st.metric("Cache 股票數", f"{total_cached} 檔")
    with c4:
        st.metric("回測結果", f"{len(results)} 份")

    st.markdown("---")

    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("📦 Cache 狀態")
        if cache_stats:
            for ds, cnt in cache_stats.items():
                bar_pct = min(cnt / 50, 1.0)
                st.progress(bar_pct, text=f"{ds}：{cnt} 檔")
        else:
            st.info("尚無 cache，請先執行「更新資料」")

    with col_r:
        st.subheader("📅 最近結果")
        if results:
            import pandas as pd
            st.dataframe(pd.DataFrame(results), hide_index=True, use_container_width=True)
        else:
            st.info("尚無回測結果")

    st.markdown("---")
    st.subheader("⚡ 快速執行")
    qc1, qc2, qc3 = st.columns(3)
    with qc1:
        if st.button("🔄 更新 TWSE 資料", use_container_width=True):
            with st.spinner("抓取中..."):
                r = subprocess.run(
                    ["python3", "scripts/update_cache.py"],
                    cwd=PROJECT_ROOT, capture_output=True, text=True
                )
                if r.returncode == 0:
                    st.success("完成！")
                else:
                    st.error(r.stderr[:300])
    with qc2:
        if st.button("🔍 執行選股評分", use_container_width=True):
            st.info("請到「執行腳本」頁面查看詳細輸出")
    with qc3:
        if st.button("📊 執行回測", use_container_width=True):
            st.info("請到「執行腳本」頁面查看詳細輸出")


# ═══════════════════════════════════════════════════════════════════════════════
# 頁面：方案設定
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "⚙️ 方案設定":
    st.title("⚙️ FinMind 方案設定")

    cfg = read_current_plan()

    st.markdown("### 目前設定")
    c1, c2, c3 = st.columns(3)
    c1.metric("帳號方案", cfg["plan"])
    c2.metric("股價資料集", cfg["dataset"])
    c3.metric("速率上限", f"{cfg['rate_limit']} 次/hr")

    st.markdown("---")
    st.markdown("### 切換方案")

    tab_free, tab_paid = st.tabs(["🆓 免費方案（register）", "💎 付費方案（sponsor）"])

    with tab_free:
        st.markdown("""
        **適用對象**：剛開始開發、驗證策略邏輯階段

        | 項目 | 說明 |
        |------|------|
        | 股價資料集 | `price`（未還原，含除息日會有跳空） |
        | 速率上限 | 600 次/小時 |
        | 回測準確度 | 略低估（約低 2~4%/年） |
        | 費用 | 免費 |
        """)
        if cfg["plan"] != "register":
            if st.button("⬇️ 切換到免費方案", type="secondary", use_container_width=True):
                write_plan("register")
                st.success("已切換到免費方案，重新整理頁面生效")
                st.rerun()
        else:
            st.success("✅ 目前使用中")

    with tab_paid:
        st.markdown("""
        **適用對象**：策略驗證完成、準備正式上線

        | 項目 | 說明 |
        |------|------|
        | 股價資料集 | `price_adj`（還原股價，除權息已調整） |
        | 速率上限 | 6000 次/小時（10倍） |
        | 回測準確度 | 精確 |
        | 費用 | 需贊助 FinMind（見官網） |
        """)
        st.info("升級後到 [finmindtrade.com](https://finmindtrade.com/analysis/#/Sponsor/sponsor) 贊助，token 不變")
        if cfg["plan"] != "sponsor":
            if st.button("⬆️ 切換到付費方案", type="primary", use_container_width=True):
                write_plan("sponsor")
                st.success("已切換到付費方案，重新整理頁面生效")
                st.rerun()
        else:
            st.success("✅ 目前使用中")

    st.markdown("---")
    st.markdown("### Token 設定")
    token_val = os.environ.get("FINMIND_TOKEN", "")
    if token_val:
        st.success(f"✅ FINMIND_TOKEN 已設定（{token_val[:8]}...）")
    else:
        st.error("❌ FINMIND_TOKEN 未設定")
        st.code('echo \'export FINMIND_TOKEN="你的token"\' >> ~/.zshrc && source ~/.zshrc', language="bash")

    st.markdown("---")
    st.markdown("### 除權息還原說明")
    st.info("""
    **為什麼 price 和 price_adj 有差異？**

    台積電股價 600 元 → 除息 10 元 → 除息日變 590 元。

    - `price`（免費）：看到股價從 600 跌到 590，**帳面虧 -1.67%**，但你其實拿到股利，真實報酬是 0%
    - `price_adj`（付費）：除息前股價已向下調整，除息當天看起來沒跌，**正確顯示 0%**

    開發階段用 `price` 完全夠用，策略邏輯和排名的**相對關係不受影響**。
    上線前再換 `price_adj` 確認真實數字。
    """)


# ═══════════════════════════════════════════════════════════════════════════════
# 頁面：資料狀態
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "📁 資料狀態":
    st.title("📁 資料狀態")

    import pandas as pd

    cache_stats = get_cache_stats()
    empty_stats = get_empty_stats()

    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("📦 FinMind Cache")
        if cache_stats:
            df = pd.DataFrame([
                {"資料集": k, "已快取": v, "進度": f"{min(v/50*100, 100):.0f}%"}
                for k, v in cache_stats.items()
            ])
            st.dataframe(df, hide_index=True, use_container_width=True)
            for ds, cnt in cache_stats.items():
                st.progress(min(cnt / 50, 1.0), text=f"{ds}")
        else:
            st.warning("尚無 cache\n\n請先執行：`python scripts/update_cache.py`")

        st.markdown("---")
        st.subheader("🚫 Empty Markers")
        if empty_stats:
            df2 = pd.DataFrame([{"資料集": k, "無資料檔數": v} for k, v in empty_stats.items()])
            st.dataframe(df2, hide_index=True, use_container_width=True)
            st.caption("Empty marker = 確認無資料的股票，不會重複打 API")
        else:
            st.info("尚無 empty markers")

    with col_r:
        st.subheader("📰 TWSE 資料檔")
        twse_files = get_twse_files()
        if twse_files:
            st.dataframe(pd.DataFrame(twse_files), hide_index=True, use_container_width=True)
        else:
            st.info("尚無 TWSE 資料\n\n請先執行：`python data/twse_fetcher.py`")

        st.markdown("---")
        st.subheader("🧹 Cache 管理")
        st.warning("以下操作不可逆，確認後才執行")
        dataset_to_clear = st.selectbox(
            "選擇要清除的資料集",
            options=list(cache_stats.keys()) if cache_stats else ["（無）"],
        )
        if st.button("🗑️ 清除選定資料集的 cache", type="secondary"):
            target = CACHE_DIR / dataset_to_clear
            if target.exists():
                import shutil
                shutil.rmtree(target)
                target.mkdir()
                st.success(f"已清除 {dataset_to_clear} 的 cache")
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# 頁面：回測結果
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "📊 回測結果":
    st.title("📊 回測結果")
    import pandas as pd

    results = get_results()
    if not results:
        st.info("尚無回測結果\n\n請先執行：`python scripts/run_backtest.py`")
    else:
        csv_files = sorted(RESULTS_DIR.glob("*comparison*.csv"), reverse=True)
        if csv_files:
            selected = st.selectbox("選擇結果", [f.name for f in csv_files])
            df = pd.read_csv(RESULTS_DIR / selected)

            st.markdown("### 三模式比較")
            c1, c2, c3 = st.columns(3)
            for i, (_, row) in enumerate(df.iterrows()):
                col = [c1, c2, c3][i]
                with col:
                    mode_label = {"ideal": "🟢 Ideal", "realistic": "🔵 Realistic", "pessimistic": "🔴 Pessimistic"}.get(row.get("mode",""), row.get("mode",""))
                    st.markdown(f"**{mode_label}**")
                    st.metric("年化報酬", f"{row.get('annual_return', 0):.2f}%")
                    st.metric("Sharpe", f"{row.get('sharpe', 0):.3f}")
                    st.metric("MDD", f"{row.get('mdd', 0):.2f}%")
                    st.metric("勝率", f"{row.get('win_rate', 0):.1f}%")

            st.markdown("---")
            st.markdown("### 完整數據")
            st.dataframe(df, hide_index=True, use_container_width=True)

        equity_files = sorted(RESULTS_DIR.glob("*equity_realistic*.csv"), reverse=True)
        if equity_files:
            st.markdown("### Realistic Equity Curve")
            eq_df = pd.read_csv(equity_files[0], index_col=0)
            st.line_chart(eq_df)


# ═══════════════════════════════════════════════════════════════════════════════
# 頁面：執行腳本
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "▶️ 執行腳本":
    st.title("▶️ 執行腳本")

    st.info("腳本在背景執行，輸出顯示在下方。長時間腳本請在終端機執行以免 Streamlit timeout。")

    scripts = {
        "更新 TWSE + FinMind cache": ("scripts/update_cache.py", "🔄"),
        "執行選股評分":              ("scripts/run_screener.py", "🔍"),
        "執行三模式回測":            ("scripts/run_backtest.py", "📊"),
    }

    selected_script = st.selectbox(
        "選擇腳本",
        list(scripts.keys()),
    )

    script_path, icon = scripts[selected_script]
    st.code(f"python3 {script_path}", language="bash")

    if st.button(f"{icon} 執行 {selected_script}", type="primary", use_container_width=True):
        with st.spinner(f"執行中：{script_path}..."):
            r = subprocess.run(
                ["python3", script_path],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=300,
            )
        if r.returncode == 0:
            st.success("執行完成")
            st.text_area("輸出", r.stdout, height=300)
        else:
            st.error("執行失敗")
            st.text_area("錯誤訊息", r.stderr, height=200)
            if r.stdout:
                st.text_area("標準輸出", r.stdout, height=150)

    st.markdown("---")
    st.markdown("### 手動執行指令（終端機）")
    st.code("""cd ~/Desktop/股票系統/quant_tw
python3 scripts/update_cache.py   # 更新資料
python3 scripts/run_screener.py   # 選股評分
python3 scripts/run_backtest.py   # 三模式回測
streamlit run dashboard.py        # 開啟面板""", language="bash")
