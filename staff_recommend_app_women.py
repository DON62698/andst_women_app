
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import date, datetime
import calendar
import json, os

st.set_page_config(page_title="and st 統計（women）", page_icon="icon.png", layout="wide")

# =============================
# 背景や全体スタイル（最低限）
# =============================
st.markdown(
    """
    <style>
    .metric-row { margin-top: .5rem; margin-bottom: .5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# =============================
# ローカル永続化（バックエンド不在時に使用）
# =============================
LOCAL_RECORDS_PATH = "/mnt/data/local_records.json"
LOCAL_TARGETS_PATH = "/mnt/data/local_targets.json"


def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _save_json(path, obj):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def local_load_records():
    return _load_json(LOCAL_RECORDS_PATH, [])


def local_save_records(records):
    _save_json(LOCAL_RECORDS_PATH, records or [])


def local_get_target(ym: str, t: str) -> int:
    targets = _load_json(LOCAL_TARGETS_PATH, {})
    try:
        return int(targets.get(ym, {}).get(t, 0))
    except Exception:
        return 0


def local_set_target(ym: str, t: str, value: int):
    targets = _load_json(LOCAL_TARGETS_PATH, {})
    targets.setdefault(ym, {})[t] = int(value)
    _save_json(LOCAL_TARGETS_PATH, targets)


# =============================
# 外部バックエンド（Google Sheets）
# =============================
BACKEND_OK = False
try:
    from db_gsheets import (
        init_db,
        init_target_table,
        load_all_records,
        insert_or_update_record,
        set_target,
        get_target,
    )
    # 軽く初期化（失敗しても続行）
    try:
        init_db()
        init_target_table()
        BACKEND_OK = True
    except Exception:
        BACKEND_OK = False
except Exception:
    BACKEND_OK = False

# データ管理の安全なインポート
try:
    from data_management import show_data_management
except Exception:
    def show_data_management():
        st.info("データ管理モジュールが読み込めません（data_management.py を確認してください）。")


# =============================
# ユーティリティ
# =============================
def ymd(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def current_year_month() -> str:
    today = date.today()
    return today.strftime("%Y-%m")


def ensure_dataframe(records) -> pd.DataFrame:
    if isinstance(records, pd.DataFrame):
        df = records.copy()
    else:
        df = pd.DataFrame(records or [])
    for col, default in [("date", ""), ("name", ""), ("type", ""), ("count", 0)]:
        if col not in df.columns:
            df[col] = default
    # to proper dtypes
    try:
        df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)
    except Exception:
        pass
    return df[["date", "name", "type", "count"]]


@st.cache_data(show_spinner=False)
def load_all_records_cached():
    if BACKEND_OK:
        try:
            return load_all_records() or []
        except Exception:
            pass
    # fallback local
    return local_load_records()


def month_filter(df: pd.DataFrame, ym: str) -> pd.DataFrame:
    if df.empty:
        return df
    ym_col = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m")
    return df[ym_col == ym]


def get_target_safe(ym: str, t: str) -> int:
    if BACKEND_OK:
        try:
            val = get_target(ym, t)
            return int(val) if val not in (None, "") else 0
        except Exception:
            pass
    return local_get_target(ym, t)


# =============================
# 画面構成
# =============================
st.title("and st 統計（women）")
if not BACKEND_OK:
    st.caption("Google Sheets バックエンドが読み込めませんでした。ローカル機能のみ有効です。")

tab_reg, tab_app_ana, tab_survey_ana, tab_manage = st.tabs(
    ["件数登録", "and st 分析", "アンケート分析", "データ管理"]
)

# ---- 初期データ & 名前リスト ----
if "data" not in st.session_state:
    st.session_state.data = load_all_records_cached()
if "names" not in st.session_state:
    df0 = ensure_dataframe(st.session_state.data)
    st.session_state.names = sorted(df0["name"].dropna().unique().tolist())


# =============================
# 件数登録
# =============================
with tab_reg:
    st.subheader("件数登録")
    df_all = ensure_dataframe(st.session_state.get("data", []))

    with st.form("unified_form"):
        c1, c2 = st.columns([1, 2])
        with c1:
            d = st.date_input("日付", value=date.today())
            # 名前は手入力（既存候補はサジェストとして表示）
            name = st.text_input("名前", placeholder="氏名を入力", autocomplete="name")
            if not name and st.session_state.names:
                st.caption("候補：" + " / ".join(st.session_state.names[:10]))
        with c2:
            st.markdown("#### 件数（and st）")
            colA, colB, colC = st.columns(3)
            with colA:
                new_cnt = st.number_input("新規", min_value=0, step=1, value=0, key="reg_new")
            with colB:
                exist_cnt = st.number_input("既存", min_value=0, step=1, value=0, key="reg_exist")
            with colC:
                line_cnt = st.number_input("LINE", min_value=0, step=1, value=0, key="reg_line")

        st.markdown("#### 件数（アンケート）")
        survey_cnt = st.number_input("アンケート", min_value=0, step=1, value=0, key="reg_survey")

        submitted = st.form_submit_button("保存")
        if submitted:
            if not name:
                st.warning("名前を入力してください。")
            else:
                total = int(new_cnt) + int(exist_cnt) + int(line_cnt) + int(survey_cnt)
                _new_rows = []
                if int(new_cnt)   > 0: _new_rows.append({"date": ymd(d), "name": name, "type": "new",    "count": int(new_cnt)})
                if int(exist_cnt) > 0: _new_rows.append({"date": ymd(d), "name": name, "type": "exist",  "count": int(exist_cnt)})
                if int(line_cnt)  > 0: _new_rows.append({"date": ymd(d), "name": name, "type": "line",   "count": int(line_cnt)})
                if int(survey_cnt)> 0: _new_rows.append({"date": ymd(d), "name": name, "type": "survey", "count": int(survey_cnt)})
                try:
                    backend_ok = False
                    if total > 0 and BACKEND_OK:
                        try:
                            if new_cnt   > 0: insert_or_update_record(ymd(d), name, "new",    int(new_cnt))
                            if exist_cnt > 0: insert_or_update_record(ymd(d), name, "exist",  int(exist_cnt))
                            if line_cnt  > 0: insert_or_update_record(ymd(d), name, "line",   int(line_cnt))
                            if survey_cnt> 0: insert_or_update_record(ymd(d), name, "survey", int(survey_cnt))
                            backend_ok = True
                        except Exception:
                            backend_ok = False

                    # 可能ならバックエンドから再読込
                    reloaded = []
                    if backend_ok:
                        load_all_records_cached.clear()
                        reloaded = load_all_records_cached() or []

                    # ローカルに統合して UI を即時更新
                    df_current = ensure_dataframe(st.session_state.get("data", []))
                    df_merge = pd.concat([df_current, pd.DataFrame(reloaded), pd.DataFrame(_new_rows)], ignore_index=True)
                    st.session_state.data = df_merge.to_dict("records")

                    # バックエンドがダメなときはローカル保存
                    if not backend_ok:
                        local_save_records(st.session_state.data)

                    # 名前一覧更新
                    st.session_state.names = sorted(ensure_dataframe(st.session_state.data)["name"].dropna().unique().tolist())
                    st.success("保存しました。")
                except Exception as e:
                    # ローカルだけでも反映
                    df_current = ensure_dataframe(st.session_state.get("data", []))
                    df_merge = pd.concat([df_current, pd.DataFrame(_new_rows)], ignore_index=True)
                    st.session_state.data = df_merge.to_dict("records")
                    local_save_records(st.session_state.data)
                    if name and name not in st.session_state.names:
                        st.session_state.names.append(name)
                        st.session_state.names.sort()
                    st.warning("バックエンド保存に失敗しましたが、ローカルには反映しました。")

    st.divider()

    # ---- 月目標 & 達成率 ----
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

    with st.popover("🎯 月目標を設定 / 更新", use_container_width=True):
        cm1, cm2 = st.columns(2)
        with cm1:
            t_app_m_new = st.number_input("and st（月）", min_value=0, step=1, value=int(t_app_m), key=f"mon_app_{ym}")
        with cm2:
            t_sur_m_new = st.number_input("アンケート（月）", min_value=0, step=1, value=int(t_sur_m), key=f"mon_survey_{ym}")
        if st.button("月目標を保存", key=f"save_mon_{ym}"):
            try:
                if BACKEND_OK:
                    set_target(ym, "app", int(t_app_m_new))
                    set_target(ym, "survey", int(t_sur_m_new))
                else:
                    local_set_target(ym, "app", int(t_app_m_new))
                    local_set_target(ym, "survey", int(t_sur_m_new))
                st.success("月目標を保存しました。")
                st.rerun()
            except Exception:
                local_set_target(ym, "app", int(t_app_m_new))
                local_set_target(ym, "survey", int(t_sur_m_new))
                st.success("月目標を保存しました。（ローカルに保存）")
                st.rerun()

    def pct(a, b):
        return (a / b * 100.0) if b and b > 0 else 0.0

    m1, m2, m3 = st.columns(3)
    with m1: st.metric("and st（月）実績", f"{month_app} 件")
    with m2: st.metric("and st（月）目標", f"{t_app_m} 件")
    with m3: st.metric("and st（月）達成率", f"{pct(month_app, t_app_m):.1f}%")
    m4, m5, m6 = st.columns(3)
    with m4: st.metric("アンケート（月）実績", f"{month_survey} 件")
    with m5: st.metric("アンケート（月）目標", f"{t_sur_m} 件")
    with m6: st.metric("アンケート（月）達成率", f"{pct(month_survey, t_sur_m):.1f}%")


# =============================
# 共通：統計表示（男生版スタイル）
# =============================
def show_statistics(category: str, label: str):
    """
    男生版の操作感：
      - 期間選択：年（単年）/ 月（年内）
      - 月（年内）選択時のみ「週別合計」テーブル
      - 構成比（and st のみ）：円グラフ（期間に応じて年 or 月）
      - スタッフ別 合計：棒グラフ（期間に応じて年 or 月、数値付き）
      - 月別累計（年次）：選んだ年の各月合計テーブル
    """
    df_all = ensure_dataframe(st.session_state.get("data", []))
    # カテゴリでフィルタ
    if category == "app":
        df_cat = df_all[df_all["type"].isin(["new", "exist", "line"])].copy()
    else:
        df_cat = df_all[df_all["type"] == "survey"].copy()

    st.subheader(label)

    if df_cat.empty:
        st.info("データがありません。")
        return

    df_cat["date"] = pd.to_datetime(df_cat["date"], errors="coerce")
    years = sorted(df_cat["date"].dt.year.dropna().unique().astype(int).tolist())
    if not years:
        st.info("データがありません。")
        return

    colP, colY, colM = st.columns([1.2, 1, 2])
    with colP:
        ptype = st.selectbox("期間", options=["年（単年）", "月（年内）"], key=f"{label}_ptype")
    with colY:
        default_year = years[-1]
        year_sel = st.selectbox("年を選択", options=years, index=len(years)-1, key=f"{label}_year")
    with colM:
        if ptype == "月（年内）":
            months = sorted(df_cat[df_cat["date"].dt.year == year_sel]["date"].dt.month.dropna().unique().astype(int).tolist())
            if not months:
                st.info(f"{year_sel} 年のデータがありません。")
                return
            month_sel = st.select_slider("月を選択", options=months, value=months[-1], key=f"{label}_month")
        else:
            month_sel = None

    # 週別合計（月の時のみ）
    if ptype == "月（年内）":
        st.subheader("週別合計")
        df_m = df_cat[(df_cat["date"].dt.year == year_sel) & (df_cat["date"].dt.month == month_sel)].copy()
        if df_m.empty:
            st.info("この月のデータがありません。")
        else:
            weeks = df_m["date"].dt.isocalendar().week.astype(int)
            uniq_weeks = sorted(weeks.unique().tolist())
            wmap = {wk: i + 1 for i, wk in enumerate(uniq_weeks)}
            df_m["w_num"] = weeks.map(wmap)
            weekly = df_m.groupby("w_num")["count"].sum().reset_index().sort_values("w_num")
            weekly["w"] = weekly["w_num"].apply(lambda x: f"w{x}")
            st.caption(f"表示中：{year_sel}年・{month_sel}月")
            st.dataframe(weekly[["w", "count"]].rename(columns={"count": "合計"}), use_container_width=True)

    # 構成比（and st のみ）
    if category == "app":
        st.subheader("構成比（新規・既存・LINE）")
        if ptype == "年（単年）":
            df_comp = df_cat[df_cat["date"].dt.year == year_sel].copy()
            caption = f"表示中：{year_sel}年"
        else:
            df_comp = df_cat[(df_cat["date"].dt.year == year_sel) & (df_cat["date"].dt.month == month_sel)].copy()
            caption = f"表示中：{year_sel}年・{month_sel}月"
        new_sum = int(df_comp[df_comp["type"] == "new"]["count"].sum())
        exist_sum = int(df_comp[df_comp["type"] == "exist"]["count"].sum())
        line_sum = int(df_comp[df_comp["type"] == "line"]["count"].sum())
        total = new_sum + exist_sum + line_sum
        if total > 0:
            st.caption(caption)
            labels = ["新規", "既存", "LINE"]
            fig = plt.figure()
            plt.pie([new_sum, exist_sum, line_sum], labels=labels, autopct="%1.1f%%", startangle=90)
            st.pyplot(fig)
        else:
            st.caption("対象データがありません。")

    # スタッフ別 合計
    st.subheader("スタッフ別 合計")
    if ptype == "年（単年）":
        df_staff = df_cat[df_cat["date"].dt.year == year_sel].copy()
    else:
        df_staff = df_cat[(df_cat["date"].dt.year == year_sel) & (df_cat["date"].dt.month == month_sel)].copy()
    if df_staff.empty:
        st.caption("対象データがありません。")
    else:
        ser = df_staff.groupby("name")["count"].sum().sort_values(ascending=False)
        fig2 = plt.figure()
        bars = plt.bar(ser.index.tolist(), ser.values.tolist())
        plt.xticks(rotation=45, ha="right")
        ymax = max(ser.values.tolist() + [1])
        plt.ylim(0, ymax * 1.15)
        for b, v in zip(bars, ser.values.tolist()):
            plt.text(b.get_x() + b.get_width()/2, b.get_height(), f"{int(v)}", ha="center", va="bottom", fontsize=9)
        st.pyplot(fig2)

    # 月別累計（年次）：テーブル
    st.subheader("月別累計（年次）")
    df_y = df_cat[df_cat["date"].dt.year == year_sel].copy()
    if df_y.empty:
        st.caption("対象データがありません。")
    else:
        monthly = (
            df_y.groupby(df_y["date"].dt.strftime("%Y-%m"))["count"].sum().reset_index()
            .rename(columns={"date": "年月", "count": "合計"})
        )
        monthly = monthly.sort_values("年月")
        st.caption(f"表示中：{year_sel}年")
        st.dataframe(monthly.rename(columns={monthly.columns[0]: "年月"}), use_container_width=True)


# =============================
# and st 分析
# =============================
with tab_app_ana:
    show_statistics("app", "and st 分析")

# =============================
# アンケート分析
# =============================
with tab_survey_ana:
    show_statistics("survey", "アンケート分析")

# =============================
# データ管理
# =============================
with tab_manage:
    try:
        show_data_management()
    except Exception as e:
        st.error(f"データ管理画面の読み込みに失敗しました: {e}")
