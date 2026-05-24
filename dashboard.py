"""
dashboard.py
台股量化系統操作面板
執行：streamlit run dashboard.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
from pathlib import Path
import re

# ─── 頁面設定 ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="台股量化系統",
    page_icon="📈",
    layout="wide",
)

SETTINGS_PATH = Path(__file__).parent / "config" / "settings.py"

# ─── 讀取目前設定 ──────────────────────────────────────────────────────────────
def read_settings():
    text = SETTINGS_PATH.read_text(encoding="utf-8")
    plan    = re.search(r'^FINMIND_PLAN\s*=\s*"(\w+)"', text, re.M)
    dataset = re.search(r'^FINMIND_PRICE_DATASET\s*=\s*"(\w+)"', text, re.M)
    rate    = re.search(r'^FINMIND_RATE_LIMIT\s*=\s*(\d+)', text, re.M)
    return {
        "plan":    plan.group(1)    if plan    else "register",
        "dataset": dataset.group(1) if dataset else "price",
        "rate":    int(rate.group(1)) if rate  else 600,
    }

def write_settings(plan: str):
    if plan == "sponsor":
        dataset, rate = "price_adj", 6000
    else:
        dataset, rate = "price", 600

    text = SETTINGS_PATH.read_text(encoding="utf-8")
    text = re.sub(r'^FINMIND_PLAN\s*=\s*"\w+"',
                  f'FINMIND_PLAN          = "{plan}"', text, flags=re.M)
    text = re.sub(r'^FINMIND_PRICE_DATASET\s*=\s*"\w+"',
                  f'FINMIND_PRICE_DATASET = "{dataset}"', text, flags=re.M)
    text = re.sub(r'^FINMIND_RATE_LIMIT\s*=\s*\d+',
                  f'FINMIND_RATE_LIMIT    = {rate}', text, flags=re.M)
    SETTINGS_PATH.write_text(text, encoding="utf-8")

# ─── 側邊欄 ────────────────────────────────────────────────────────────────────
st.sidebar.title("📈 台股量化系統")
page = st.sidebar.radio("選單", ["系統設定", "資料狀態"])

# ══════════════════════════════════════════════════════════════════════════════
# 頁面：系統設定
# ══════════════════════════════════════════════════════════════════════════════
if page == "系統設定":
    st.title("⚙️ 系統設定")

    cfg = read_settings()
    is_paid = cfg["plan"] == "sponsor"

    # ── FinMind 方案卡片 ────────────────────────────────────────────────────
    st.subheader("FinMind 帳號方案")

    col1, col2 = st.columns(2)

    with col1:
        free_border = "3px solid #1f77b4" if not is_paid else "1px solid #ccc"
        st.markdown(f"""
        <div style="border:{free_border}; border-radius:10px; padding:20px; text-align:center;">
            <h3>🆓 免費方案</h3>
            <p>資料集：<b>price</b>（一般股價）</p>
            <p>速率：<b>600 次 / 小時</b></p>
            <p style="color:gray;">帳號等級：register</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        paid_border = "3px solid #ff7f0e" if is_paid else "1px solid #ccc"
        st.markdown(f"""
        <div style="border:{paid_border}; border-radius:10px; padding:20px; text-align:center;">
            <h3>⭐ 付費方案</h3>
            <p>資料集：<b>price_adj</b>（還原股價）</p>
            <p>速率：<b>6,000 次 / 小時</b></p>
            <p style="color:gray;">帳號等級：sponsor</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ── 目前狀態 ────────────────────────────────────────────────────────────
    status_color = "#ff7f0e" if is_paid else "#1f77b4"
    status_label = "付費方案 ⭐" if is_paid else "免費方案 🆓"
    st.markdown(f"**目前使用：** <span style='color:{status_color}; font-size:1.1em;'>{status_label}</span>",
                unsafe_allow_html=True)
    st.caption(f"資料集：{cfg['dataset']}　　速率上限：{cfg['rate']:,} 次/小時")

    st.markdown("")

    # ── 切換按鈕 ────────────────────────────────────────────────────────────
    c1, c2, _ = st.columns([1, 1, 3])

    with c1:
        if st.button("切換為 🆓 免費方案", disabled=not is_paid, use_container_width=True):
            write_settings("register")
            st.success("已切換為免費方案，重新整理頁面生效。")
            st.rerun()

    with c2:
        if st.button("切換為 ⭐ 付費方案", disabled=is_paid, use_container_width=True):
            write_settings("sponsor")
            st.success("已切換為付費方案，重新整理頁面生效。")
            st.rerun()

    # ── Token 狀態 ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("FinMind Token")
    token = os.environ.get("FINMIND_TOKEN", "")
    if token:
        masked = token[:12] + "..." + token[-6:]
        st.success(f"已設定：`{masked}`")
    else:
        st.error("未偵測到 FINMIND_TOKEN，請確認 ~/.zshrc 已設定並重新開終端機。")

# ══════════════════════════════════════════════════════════════════════════════
# 頁面：資料狀態
# ══════════════════════════════════════════════════════════════════════════════
elif page == "資料狀態":
    st.title("🗄️ 資料狀態")

    cache_root   = Path(__file__).parent / "data" / "cache"
    twse_dir     = Path(__file__).parent / "data" / "twse"
    empty_dir    = Path(__file__).parent / "data" / "empty_markers"

    # ── Cache 統計 ──────────────────────────────────────────────────────────
    st.subheader("FinMind Cache")
    datasets = ["price", "price_adj", "financial", "dividend", "revenue"]
    rows = []
    for ds in datasets:
        folder = cache_root / ds
        files  = list(folder.glob("*.parquet")) if folder.exists() else []
        empty  = list((empty_dir / ds).glob("*.empty")) if (empty_dir / ds).exists() else []
        rows.append({"資料集": ds, "已快取檔數": len(files), "空標記數": len(empty)})

    import pandas as pd
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── TWSE 檔案 ───────────────────────────────────────────────────────────
    st.subheader("TWSE 每日資料")
    if twse_dir.exists():
        twse_files = sorted(twse_dir.glob("*.json"), reverse=True)[:10]
        if twse_files:
            names = [f.name for f in twse_files]
            st.dataframe(pd.DataFrame({"檔案": names}),
                         use_container_width=True, hide_index=True)
        else:
            st.info("尚無 TWSE 資料，請執行 update_cache.py")
    else:
        st.info("data/twse 目錄不存在")
