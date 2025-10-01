
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
    
    st.subheader("達成率（週 / 月）")
    df_all = ensure_dataframe(st.session_state.get("data", []))
    ym = current_year_month()
    y, w = week_of(date.today())

    with st.popover("🎯 目標を設定 / 更新", use_container_width=True):
        colW, colM = st.columns(2)

        with colW:
            st.markdown("**週目標（今週）**")
            # Load existing (Sheets first, fallback to session_state)
            if BACKEND_OK:
                t_app_w = get_weekly_target(y, w, "app")
                t_sur_w = get_weekly_target(y, w, "survey")
            else:
                t_app_w = int(st.session_state.get("weekly_targets_app", {}).get((y, w), 0))
                t_sur_w = int(st.session_state.get("weekly_targets_survey", {}).get((y, w), 0))

            cw1, cw2 = st.columns(2)
            with cw1:
                t_app_w_new = st.number_input("and st（週）", min_value=0, step=1, value=int(t_app_w), key=f"wk_app_{y}_{w}")
            with cw2:
                t_sur_w_new = st.number_input("アンケート（週）", min_value=0, step=1, value=int(t_sur_w), key=f"wk_survey_{y}_{w}")

            if st.button("週目標を保存", key=f"save_wk_{y}_{w}"):
                if BACKEND_OK:
                    set_weekly_target(y, w, "app", int(t_app_w_new))
                    set_weekly_target(y, w, "survey", int(t_sur_w_new))
                else:
                    st.session_state.setdefault("weekly_targets_app", {})[(y, w)] = int(t_app_w_new)
                    st.session_state.setdefault("weekly_targets_survey", {})[(y, w)] = int(t_sur_w_new)
                st.success("今週の目標を保存しました。")

        with colM:
            st.markdown("**月目標（{ym}）**")
            t_app_m = get_target_safe(ym, "app")
            t_sur_m = get_target_safe(ym, "survey")
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

    # 実績集計（今週 / 今月、and st / アンケート）
    def is_this_week(d0: date) -> bool:
        yy, ww, _ = datetime(d0.year, d0.month, d0.day).isocalendar()
        return (yy, ww) == (y, w)

    week_app = week_survey = month_app = month_survey = 0
    if not df_all.empty:
        df_week = df_all[df_all["date"].apply(is_this_week)]
        week_app = int(df_week[df_week["type"].isin(["new", "exist", "line"])]["count"].sum())
        week_survey = int(df_week[df_week["type"] == "survey"]["count"].sum())

        df_m = month_filter(df_all, ym)
        month_app = int(df_m[df_m["type"].isin(["new", "exist", "line"])]["count"].sum())
        month_survey = int(df_m[df_m["type"] == "survey"]["count"].sum())

    if BACKEND_OK:
        tgt_app_w = get_weekly_target(y, w, "app")
        tgt_sur_w = get_weekly_target(y, w, "survey")
    else:
        tgt_app_w = int(st.session_state.get("weekly_targets_app", {}).get((y, w), 0))
        tgt_sur_w = int(st.session_state.get("weekly_targets_survey", {}).get((y, w), 0))

    tgt_app_m = get_target_safe(ym, "app")
    tgt_sur_m = get_target_safe(ym, "survey")

    def pct(a, b): return (a / b * 100.0) if b and b > 0 else 0.0

    m1, m2, m3, m4 = st.columns(4)
    with m1: st.metric("and st（週）実績", f"{week_app} 件")
    with m2: st.metric("and st（週）目標", f"{tgt_app_w} 件")
    with m3: st.metric("and st（月）実績", f"{month_app} 件")
    with m4: st.metric("and st（月）目標", f"{tgt_app_m} 件")

    m5, m6, m7, m8 = st.columns(4)
    with m5: st.metric("アンケート（週）実績", f"{week_survey} 件")
    with m6: st.metric("アンケート（週）目標", f"{tgt_sur_w} 件")
    with m7: st.metric("アンケート（月）実績", f"{month_survey} 件")
    with m8: st.metric("アンケート（月）目標", f"{tgt_sur_m} 件")

    st.caption(f"and st（週） 達成率：{pct(week_app, tgt_app_w):.1f}% ／ 月：{pct(month_app, tgt_app_m):.1f}%")
    st.caption(f"アンケート（週） 達成率：{pct(week_survey, tgt_sur_w):.1f}% ／ 月：{pct(month_survey, tgt_sur_m):.1f}%")
    
# =============================
# 分析共通関数
# =============================

def show_statistics(category: str, label: str):
    """
    Mirror male app display:
     - 週別合計: table (current selected 年・月)
     - 構成比（and stのみ）: pie
     - スタッフ別 合計: bar with values
     - 月別累計（年次）: line
    """
    import matplotlib.pyplot as plt

    st.subheader(label)
    df_all = ensure_dataframe(st.session_state.get("data", []))
    if df_all.empty:
        st.info("データがありません。")
        return

    # フィルタ選択：年・月
    year_opts = sorted(pd.to_datetime(df_all["date"]).dt.year.unique().tolist())
    colY, colM = st.columns([1, 2])
    with colY:
        yearW = st.selectbox("年", options=year_opts, index=len(year_opts)-1, key=f"{label}_year")
    with colM:
        # 該当年の月一覧
        months = sorted(pd.to_datetime(df_all[pd.to_datetime(df_all["date"]).dt.year == yearW]["date"]).dt.month.unique().tolist())
        monthW = st.select_slider("月", options=months, value=months[-1], key=f"{label}_month")

    # === 週別合計 ===
    st.subheader("週別合計")
    mask_y = pd.to_datetime(df_all["date"]).dt.year == yearW
    mask_m = pd.to_datetime(df_all["date"]).dt.month == monthW
    df_monthW = df_all[mask_y & mask_m].copy()
    if category == "app":
        df_monthW = df_monthW[df_monthW["type"].isin(["new", "exist", "line"])]
    else:
        df_monthW = df_monthW[df_monthW["type"] == "survey"]

    if df_monthW.empty:
        st.info("この月のデータがありません。")
    else:
        df_monthW["date"] = pd.to_datetime(df_monthW["date"])
        df_monthW["week_iso"] = df_monthW["date"].dt.isocalendar().week.astype(int)
        # w番号（1..5）へ正規化：その月の週番号を小さい順に並べて1,2,3...
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
        df_c = df_all.copy()
        df_c = df_c[pd.to_datetime(df_c["date"]).dt.year == yearW]
        df_c = df_c[df_c["type"].isin(["new", "exist", "line"])]
        comp = df_c.groupby("type")["count"].sum().reindex(["new", "exist", "line"]).fillna(0)
        labels = ["新規", "既存", "LINE"]
        plt.figure()
        plt.pie(comp.values, labels=labels, autopct="%1.1f%%", startangle=90)
        plt.axis("equal")
        st.pyplot(plt.gcf())

    # === スタッフ別 合計 ===
    st.subheader("スタッフ別 合計")
    df_s = df_all.copy()
    df_s = df_s[pd.to_datetime(df_s["date"]).dt.year == yearW]
    if category == "app":
        df_s = df_s[df_s["type"].isin(["new", "exist", "line"])]
    else:
        df_s = df_s[df_s["type"] == "survey"]
    by_staff = df_s.groupby("name")["count"].sum().sort_values(ascending=False)
    plt.figure()
    bars = plt.bar(by_staff.index.tolist(), by_staff.values.tolist())
    plt.xticks(rotation=45, ha="right")
    ymax = max(by_staff.values.tolist() + [1])
    plt.ylim(0, ymax * 1.15)
    for bar, val in zip(bars, by_staff.values.tolist()):
        plt.text(bar.get_x() + bar.get_width()/2, bar.get_height(), f"{int(val)}", ha="center", va="bottom", fontsize=9)
    st.pyplot(plt.gcf())

    # === 月別累計（年次） ===
    st.subheader("月別累計（年次）")
    df_y = df_all.copy()
    df_y = df_y[pd.to_datetime(df_y["date"]).dt.year == yearW]
    if category == "app":
        df_y = df_y[df_y["type"].isin(["new", "exist", "line"])]
    else:
        df_y = df_y[df_y["type"] == "survey"]
    df_y["ym"] = pd.to_datetime(df_y["date"]).dt.strftime("%Y-%m")
    mg = df_y.groupby("ym")["count"].sum().reset_index()
    st.line_chart(mg.set_index("ym"))
