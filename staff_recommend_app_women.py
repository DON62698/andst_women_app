
import streamlit as st
import pandas as pd
from datetime import date, datetime
import calendar

# ---- External backends ----
# These functions exist in your bundled modules.
try:
    from db_gsheets import (
        init_db,
        init_target_table,
        load_all_records,
        insert_or_update_record,
        set_target,
        get_target,
        set_weekly_target,
        get_weekly_target,
    )
    from data_management import show_data_management
    GSHEETS_AVAILABLE = True
except Exception:
    GSHEETS_AVAILABLE = False

# ---- Weekly target fallbacks (always defined) ----
def _wkstore():
    st.session_state.setdefault("_weekly_targets", {})  # key: (year, week, category) -> int
    return st.session_state["_weekly_targets"]

if "get_weekly_target" not in globals():
    def get_weekly_target(year: int, week: int, category: str) -> int:
        store = _wkstore()
        return int(store.get((int(year), int(week), str(category)), 0))

if "set_weekly_target" not in globals():
    def set_weekly_target(year: int, week: int, category: str, value: int):
        store = _wkstore()
        store[(int(year), int(week), str(category))] = int(value)
        return True

# ---- Page config ----
st.set_page_config(page_title="and st 女生組", page_icon="icon.png", layout="wide")

# ---- Utilities ----
def ymd(d: date) -> str:
    if isinstance(d, str):
        return d
    return d.strftime("%Y-%m-%d")

def current_year_month(d: date | None = None) -> str:
    d = d or date.today()
    return d.strftime("%Y-%m")

def ensure_dataframe(records) -> pd.DataFrame:
    """Ensure records (list[dict]) -> DataFrame with typed columns."""
    if not records:
        return pd.DataFrame(columns=["date", "name", "type", "count"])
    df = pd.DataFrame(records).copy()
    # normalize columns
    for col in ["date", "name", "type", "count"]:
        if col not in df.columns:
            df[col] = None
    # parse date
    try:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    except Exception:
        pass
    # enforce dtypes
    df["name"] = df["name"].astype(str)
    df["type"] = df["type"].astype(str)
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)
    return df

def month_filter(df: pd.DataFrame, ym: str) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    return df[(pd.to_datetime(df["date"]).dt.strftime("%Y-%m") == ym)].copy()

def week_of(d: date) -> tuple[int, int]:
    y, w, _ = d.isocalendar()
    return int(y), int(w)

def get_target_safe(ym: str, t: str) -> int:
    """Wrap db get_target -> int, default 0 if missing or backend not ready."""
    if not GSHEETS_AVAILABLE:
        return 0
    try:
        val = get_target(ym, t)
        return int(val) if val is not None and str(val).strip() != "" else 0
    except Exception:
        return 0

# ---- Cached data loader ----
@st.cache_data(show_spinner=False)
def load_all_records_cached():
    if not GSHEETS_AVAILABLE:
        return []
    try:
        return load_all_records()
    except Exception:
        return []

# ---- Init backend (graceful) ----
@st.cache_resource
def _init_once():
    """Init Google Sheets tables if secrets are configured; otherwise local-only mode."""
    if not GSHEETS_AVAILABLE:
        st.warning("Google Sheets バックエンドが読み込めませんでした。ローカル機能のみ有効です。")
        return False
    try:
        # If secrets are set, this will succeed.
        init_db()
        init_target_table()
        return True
    except Exception:
        st.warning("Google Sheets の設定が見つからないため、ローカル機能のみ有効です。")
        return False

BACKEND_OK = _init_once()

# ---- Sidebar status ----
with st.sidebar:
    st.markdown("### 接続状態")
    st.write("Google Sheets:", "✅" if BACKEND_OK else "❌")
    if BACKEND_OK:
        st.caption("目標（月）の保存・データ読込が有効")
    else:
        st.caption("登錄は動作しますが、月目標や記録の永続化は無効の場合があります。")

# ---- Load initial data and names ----
if "data" not in st.session_state:
    st.session_state.data = load_all_records_cached()

if "names" not in st.session_state:
    # 現有資料中的姓名清單
    df0 = ensure_dataframe(st.session_state.data)
    st.session_state.names = sorted(df0["name"].dropna().unique().tolist())

# ---- Tabs ----
tab_reg, tab_app_ana, tab_survey_ana, tab_manage = st.tabs(["件数登録", "and st 分析", "アンケート分析", "データ管理"])

# =============================
# 件数登録（統合フォーム + 達成率）
# =============================
with tab_reg:
    st.subheader("件数登録（and st / アンケート）")
    with st.form("unified_form"):
        c1, c2 = st.columns([2, 1])
        with c1:
            existing_names = st.session_state.names
            if existing_names:
                name_select = st.selectbox("スタッフ名（選択）", options=existing_names, index=0, key="reg_name_select")
                st.caption("未登録の場合は下で新規入力")
            else:
                name_select = ""
                st.info("登録済みの名前がありません。下で新規入力してください。")
            name_new = st.text_input("スタッフ名（新規入力）", key="reg_name_text").strip()
            name = name_new or name_select
        with c2:
            d = st.date_input("日付", value=date.today(), key="reg_date")

        st.markdown("#### 件数（and st）")
        colA, colB, colC = st.columns(3)
        with colA:
            new_cnt   = st.number_input("新規", min_value=0, step=1, value=0, key="reg_new")
        with colB:
            exist_cnt = st.number_input("既存", min_value=0, step=1, value=0, key="reg_exist")
        with colC:
            line_cnt  = st.number_input("LINE",  min_value=0, step=1, value=0, key="reg_line")

        st.markdown("#### 件数（アンケート）")
        survey_cnt = st.number_input("アンケート", min_value=0, step=1, value=0, key="reg_survey")

        submitted = st.form_submit_button("保存")
        if submitted:
            if not name:
                st.warning("名前を入力してください。")
            else:
                total = int(new_cnt) + int(exist_cnt) + int(line_cnt) + int(survey_cnt)
                try:
                    if total == 0:
                        # 名前だけ登録
                        if name and name not in st.session_state.names:
                            st.session_state.names.append(name)
                            st.session_state.names.sort()
                        st.info("名前を登録しました。（件数は 0 ）")
                    else:
                        if new_cnt   > 0: insert_or_update_record(ymd(d), name, "new",    int(new_cnt))
                        if exist_cnt > 0: insert_or_update_record(ymd(d), name, "exist",  int(exist_cnt))
                        if line_cnt  > 0: insert_or_update_record(ymd(d), name, "line",   int(line_cnt))
                        if survey_cnt> 0: insert_or_update_record(ymd(d), name, "survey", int(survey_cnt))

                        st.session_state.data = load_all_records_cached()
                        # refresh names
                        df0 = ensure_dataframe(st.session_state.data)
                        st.session_state.names = sorted(df0["name"].dropna().unique().tolist())
                        st.success("保存しました。")
                except Exception as e:
                    st.error(f"保存に失敗しました: {e}")

    st.divider()
    
    
    st.subheader("月目標 & 達成率")
    df_all = ensure_dataframe(st.session_state.get("data", []))
    ym = current_year_month()

    # 実績（今月）
    month_app = month_survey = 0
    if not df_all.empty:
        df_m = month_filter(df_all, ym)
        month_app = int(df_m[df_m["type"].isin(["new", "exist", "line"])]["count"].sum())
        month_survey = int(df_m[df_m["type"] == "survey"]["count"].sum())

    # 目標（今月）
    t_app_m = get_target_safe(ym, "app")
    t_sur_m = get_target_safe(ym, "survey")

    # 設定 UI（簡潔）：Popover で 2 欄（and st / アンケート）
    with st.popover("🎯 月目標を設定 / 更新", use_container_width=True):
        cm1, cm2 = st.columns(2)
        with cm1:
            t_app_m_new = st.number_input("and st（月）", min_value=0, step=1, value=int(t_app_m), key=f"mon_app_{ym}")
        with cm2:
            t_sur_m_new = st.number_input("アンケート（月）", min_value=0, step=1, value=int(t_sur_m), key=f"mon_survey_{ym}")
        if st.button("月目標を保存", key=f"save_mon_{ym}"):
            try:
                set_target(ym, "app", int(t_app_m_new))
                set_target(ym, "survey", int(t_sur_m_new))
                st.success("月目標を保存しました。")
            except Exception as e:
                st.error(f"月目標の保存に失敗しました: {e}")

    # Metrics（今月：実績/目標/達成率）
    def pct(a, b): return (a / b * 100.0) if b and b > 0 else 0.0
    m1, m2, m3 = st.columns(3)
    with m1: st.metric("and st（月）実績", f"{month_app} 件")
    with m2: st.metric("and st（月）目標", f"{t_app_m} 件")
    with m3: st.metric("and st（月）達成率", f"{pct(month_app, t_app_m):.1f}%")

    m4, m5, m6 = st.columns(3)
    with m4: st.metric("アンケート（月）実績", f"{month_survey} 件")
    with m5: st.metric("アンケート（月）目標", f"{t_sur_m} 件")
    with m6: st.metric("アンケート（月）達成率", f"{pct(month_survey, t_sur_m):.1f}%")
        
# =============================
# 分析共通関数
# =============================


def show_statistics(category: str, label: str):
    """
    男生版風格：
     - 週別合計: 表格（選択した年・月）
     - 構成比（and stのみ）: 円グラフ
     - スタッフ別 合計: 棒グラフ＋数値
     - 月別累計（年次）: 折れ線
    """
    import matplotlib.pyplot as plt

    st.subheader(label)
    df_all = ensure_dataframe(st.session_state.get("data", []))
    if df_all.empty:
        st.info("データがありません。")
        return

    # 年・月選択（安全化）
    years = sorted(pd.to_datetime(df_all["date"]).dt.year.unique().tolist())
    if not years:
        st.info("年データがありません。")
        return
    colY, colM = st.columns([1, 2])
    with colY:
        yearW = st.selectbox("年", options=years, index=len(years)-1, key=f"{label}_year")
    with colM:
        maskY = pd.to_datetime(df_all["date"]).dt.year == yearW
        months = sorted(pd.to_datetime(df_all[maskY]["date"]).dt.month.unique().tolist())
        if not months:
            st.info(f"{yearW} 年のデータがありません。")
            return
        monthW = st.select_slider("月", options=months, value=months[-1], key=f"{label}_month")

    # === 週別合計 ===
    st.subheader("週別合計")
    mask_m = (pd.to_datetime(df_all["date"]).dt.year == yearW) & (pd.to_datetime(df_all["date"]).dt.month == monthW)
    df_monthW = df_all[mask_m].copy()
    if category == "app":
        df_monthW = df_monthW[df_monthW["type"].isin(["new", "exist", "line"])]
    else:
        df_monthW = df_monthW[df_monthW["type"] == "survey"]
    if df_monthW.empty:
        st.info("この月のデータがありません。")
    else:
        df_monthW["date"] = pd.to_datetime(df_monthW["date"])
        df_monthW["week_iso"] = df_monthW["date"].dt.isocalendar().week.astype(int)
        uniq_weeks = sorted(df_monthW["week_iso"].unique().tolist())
        mapping = {wk: i+1 for i, wk in enumerate(uniq_weeks)}
        df_monthW["w_num"] = df_monthW["week_iso"].map(mapping)
        weekly = df_monthW.groupby("w_num")["count"].sum().reset_index().sort_values("w_num")
        weekly["w"] = weekly["w_num"].apply(lambda x: f"w{x}")
        st.caption(f"表示中：{yearW}年・{monthW}月")
        st.dataframe(weekly[["w", "count"]].rename(columns={"count": "合計"}), use_container_width=True)

    # === 構成比（and stのみ） ===
    if category == "app":
        st.subheader("構成比（新規・既存・LINE）")
        df_c = df_all[pd.to_datetime(df_all["date"]).dt.year == yearW].copy()
        df_c = df_c[df_c["type"].isin(["new", "exist", "line"])]
        comp = df_c.groupby("type")["count"].sum().reindex(["new", "exist", "line"]).fillna(0)
        total = comp.sum()
        if total <= 0:
            st.caption("データが不足しています。")
        else:
            labels = ["新規", "既存", "LINE"]
            fig = plt.figure()
            plt.pie(comp.values, labels=labels, autopct="%1.1f%%", startangle=90)
            plt.axis("equal")
            st.pyplot(fig)

    # === スタッフ別 合計 ===
    st.subheader("スタッフ別 合計")
    df_s = df_all[pd.to_datetime(df_all["date"]).dt.year == yearW].copy()
    if category == "app":
        df_s = df_s[df_s["type"].isin(["new", "exist", "line"])]
    else:
        df_s = df_s[df_s["type"] == "survey"]
    if df_s.empty:
        st.caption("データがありません。")
    else:
        by_staff = df_s.groupby("name")["count"].sum().sort_values(ascending=False)
        fig2 = plt.figure()
        bars = plt.bar(by_staff.index.tolist(), by_staff.values.tolist())
        plt.xticks(rotation=45, ha="right")
        ymax = max(by_staff.values.tolist() + [1])
        plt.ylim(0, ymax * 1.15)
        for bar, val in zip(bars, by_staff.values.tolist()):
            plt.text(bar.get_x() + bar.get_width()/2, bar.get_height(), f"{int(val)}", ha="center", va="bottom", fontsize=9)
        st.pyplot(fig2)

    # === 月別累計（年次） ===
    st.subheader("月別累計（年次）")
    df_y = df_all[pd.to_datetime(df_all["date"]).dt.year == yearW].copy()
    if category == "app":
        df_y = df_y[df_y["type"].isin(["new", "exist", "line"])]
    else:
        df_y = df_y[df_y["type"] == "survey"]
    if df_y.empty:
        st.caption("データがありません。")
    else:
        df_y["ym"] = pd.to_datetime(df_y["date"]).dt.strftime("%Y-%m")
        mg = df_y.groupby("ym")["count"].sum().reset_index()
        st.line_chart(mg.set_index("ym"))
