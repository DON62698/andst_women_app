
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import date
import calendar
import os, json

st.set_page_config(page_title="and st 統計（women）", page_icon="icon.png", layout="wide")

# -----------------------------
# 日本語フォント（任意・ある場合のみ反映）
# -----------------------------
from matplotlib import font_manager, rcParams
JP_FONT_READY = False
try:
    font_path = os.path.join(os.path.dirname(__file__), "fonts", "NotoSansJP-Regular.otf")
    font_manager.fontManager.addfont(font_path)
    _prop = font_manager.FontProperties(fname=font_path)
    rcParams["font.family"] = _prop.get_name()
    JP_FONT_READY = True
except Exception:
    JP_FONT_READY = False
if not JP_FONT_READY:
    _CAND = ["Noto Sans CJK JP","Noto Sans JP","IPAGothic","IPAexGothic","TakaoGothic","Yu Gothic","Hiragino Sans","Meiryo","MS Gothic"]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for nm in _CAND:
        if nm in available:
            rcParams["font.family"] = nm
            JP_FONT_READY = True
            break
rcParams["axes.unicode_minus"] = False

# -----------------------------
# Google Sheets backend (存在すれば使用)
# -----------------------------
BACKEND_OK = False
try:
    from db_gsheets import (
        init_db, init_target_table, load_all_records,
        insert_or_update_record, set_target, get_target
    )
    try:
        init_db()
        init_target_table()
        BACKEND_OK = True
    except Exception:
        BACKEND_OK = False
except Exception:
    BACKEND_OK = False

# -----------------------------
# データ管理（安全ロード）
# -----------------------------
try:
    from data_management import show_data_management
except Exception:
    def show_data_management():
        st.info("データ管理モジュールが読み込めません（data_management.py を確認してください）。")

# -----------------------------
# ローカル永続化（バックエンド不在時）
# -----------------------------
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

# -----------------------------
# Cache & Utils
# -----------------------------
@st.cache_data(show_spinner=False)
def load_all_records_cached():
    if BACKEND_OK:
        try:
            return load_all_records() or []
        except Exception:
            pass
    return local_load_records()

def ymd(d: date) -> str:
    return d.strftime("%Y-%m-%d")

def current_year_month() -> str:
    return date.today().strftime("%Y-%m")

def ensure_dataframe(records) -> pd.DataFrame:
    df = pd.DataFrame(records or [])
    for col in ["date","name","type","count"]:
        if col not in df.columns:
            df[col] = None
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)
    return df[["date","name","type","count"]]

def month_filter(df: pd.DataFrame, ym: str) -> pd.DataFrame:
    if "date" not in df.columns:
        return df.iloc[0:0]
    return df[(df["date"].dt.strftime("%Y-%m") == ym)]

def names_from_records(records) -> list[str]:
    return sorted({(r.get("name") or "").strip() for r in (records or []) if r.get("name")})

def get_target_safe(ym: str, t: str) -> int:
    if BACKEND_OK:
        try:
            val = get_target(ym, t)
            return int(val) if val not in (None, "") else 0
        except Exception:
            pass
    return local_get_target(ym, t)

def year_options(df: pd.DataFrame) -> list[int]:
    if "date" not in df.columns or df["date"].isna().all():
        return [date.today().year]
    years = sorted(set(df["date"].dropna().dt.year.astype(int).tolist()))
    return years or [date.today().year]

def _week_num_to_label(w: int) -> str:
    w = int(w); w_display = ((w - 1) % 52) + 1
    return f"w{w_display}"

def _labels_for_weeks(weeks: list[int]) -> list[str]:
    return sorted({_week_num_to_label(w) for w in weeks}, key=lambda s: int(s[1:]))

def _actual_weeks_for_label(df_year: pd.DataFrame, label: str) -> list[int]:
    if "date" not in df_year.columns or df_year.empty:
        return []
    iso_weeks = sorted(set(df_year["date"].dt.isocalendar().week.astype(int).tolist()))
    want = int(label.lower().lstrip("w"))
    return [w for w in iso_weeks if int(_week_num_to_label(w)[1:]) == want]

def _period_options(df: pd.DataFrame, mode: str, selected_year: int):
    if "date" not in df.columns or df["date"].isna().all():
        today = date.today()
        if mode == "週（単週）":
            w = today.isocalendar().week if today.isocalendar().week <= 52 else 1
            return [f"w{w}"], f"w{w}"
        elif mode == "月（単月）":
            dft = today.strftime("%Y-%m"); return [dft], dft
        else:
            return [today.year], today.year
    dfx = df.dropna(subset=["date"]).copy()
    if mode == "週（単週）":
        dyear = dfx[dfx["date"].dt.year == int(selected_year)]
        weeks = sorted(set(dyear["date"].dt.isocalendar().week.astype(int).tolist()))
        labels = _labels_for_weeks(weeks) or ["w1"]
        today_w = date.today().isocalendar().week
        default = f"w{today_w if today_w <= 52 else 1}"
        if default not in labels: default = labels[0]
        return labels, default
    elif mode == "月（単月）":
        dyear = dfx[dfx["date"].dt.year == int(selected_year)]
        months = sorted(set(dyear["date"].dt.strftime("%Y-%m").tolist()))
        if not months: months = [f"{selected_year}-01"]
        default = date.today().strftime("%Y-%m") if date.today().year == int(selected_year) else months[-1]
        if default not in months: default = months[0]
        return months, default
    else:
        ys = year_options(dfx)
        default = date.today().year if date.today().year in ys else ys[-1]
        return ys, default

def _filter_by_period(df: pd.DataFrame, mode: str, value, selected_year: int) -> pd.DataFrame:
    if "date" not in df.columns or df["date"].isna().all():
        return df.iloc[0:0]
    dfx = df.dropna(subset=["date"]).copy()
    if mode == "週（単週）":
        dyear = dfx[dfx["date"].dt.year == int(selected_year)]
        weeks = _actual_weeks_for_label(dyear, str(value))
        if not weeks: return dyear.iloc[0:0]
        return dyear[dyear["date"].dt.isocalendar().week.isin(weeks)]
    elif mode == "月（単月）":
        dyear = dfx[dfx["date"].dt.year == int(selected_year)]
        return dyear[dyear["date"].dt.strftime("%Y-%m") == str(value)]
    else:
        return dfx[dfx["date"].dt.year == int(selected_year)]

# -----------------------------
# 初期化
# -----------------------------
if "data" not in st.session_state:
    st.session_state.data = load_all_records_cached()
if "names" not in st.session_state:
    st.session_state.names = names_from_records(st.session_state.data)

st.title("and st 統計（women）")
if not BACKEND_OK:
    st.caption("Google Sheets バックエンドが読み込めませんでした。ローカル機能のみ有効です。")

tab_reg, tab_app_ana, tab_survey_ana, tab_manage = st.tabs(["件数登録", "and st 分析", "アンケート分析", "データ管理"])

# -----------------------------
# 件数登録（and st + アンケート 統合フォーム）
# -----------------------------
with tab_reg:
    st.subheader("件数登録")
    with st.form("unified_form"):
        c1, c2 = st.columns([1, 2])
        with c1:
            d = st.date_input("日付", value=date.today())
            name = st.text_input("スタッフ名", placeholder="氏名を入力").strip()
            if not name and st.session_state.names:
                st.caption("候補：" + " / ".join(st.session_state.names[:10]))
        with c2:
            st.markdown("#### 件数（and st）")
            colA, colB, colC = st.columns(3)
            with colA: new_cnt = st.number_input("新規", min_value=0, step=1, value=0)
            with colB: exist_cnt = st.number_input("既存", min_value=0, step=1, value=0)
            with colC: line_cnt = st.number_input("LINE", min_value=0, step=1, value=0)
            st.markdown("#### 件数（アンケート）")
            survey_cnt = st.number_input("アンケート", min_value=0, step=1, value=0)

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
                    # backend reload
                    reloaded = []
                    if backend_ok:
                        load_all_records_cached.clear()
                        reloaded = load_all_records_cached() or []
                    # merge to session
                    df_current = ensure_dataframe(st.session_state.get("data", []))
                    df_merge = pd.concat([df_current, pd.DataFrame(reloaded), pd.DataFrame(_new_rows)], ignore_index=True)
                    st.session_state.data = df_merge.to_dict("records")
                    # local persist if backend fail
                    if not backend_ok:
                        local_save_records(st.session_state.data)
                    # refresh names
                    st.session_state.names = names_from_records(st.session_state.data)
                    st.success("保存しました。")
                except Exception:
                    df_current = ensure_dataframe(st.session_state.get("data", []))
                    df_merge = pd.concat([df_current, pd.DataFrame(_new_rows)], ignore_index=True)
                    st.session_state.data = df_merge.to_dict("records")
                    local_save_records(st.session_state.data)
                    st.session_state.names = names_from_records(st.session_state.data)
                    st.warning("バックエンド保存に失敗しましたが、ローカルには反映しました。")

    st.divider()
    # 月目標 & 達成率（今月）
    st.subheader("月目標 & 達成率")
    df_all = ensure_dataframe(st.session_state.get("data", []))
    ym = current_year_month()
    df_m = month_filter(df_all, ym)
    month_app = int(df_m[df_m["type"].isin(["new","exist","line"])]["count"].sum())
    month_survey = int(df_m[df_m["type"]=="survey"]["count"].sum())
    t_app_m = get_target_safe(ym, "app")
    t_sur_m = get_target_safe(ym, "survey")

    with st.popover("🎯 月目標を設定 / 更新", use_container_width=True):
        cm1, cm2 = st.columns(2)
        with cm1: t_app_m_new = st.number_input("and st（月）", min_value=0, step=1, value=int(t_app_m), key=f"mon_app_{ym}")
        with cm2: t_sur_m_new = st.number_input("アンケート（月）", min_value=0, step=1, value=int(t_sur_m), key=f"mon_survey_{ym}")
        if st.button("月目標を保存", key=f"save_mon_{ym}"):
            try:
                if BACKEND_OK:
                    set_target(ym, "app", int(t_app_m_new)); set_target(ym, "survey", int(t_sur_m_new))
                else:
                    local_set_target(ym, "app", int(t_app_m_new)); local_set_target(ym, "survey", int(t_sur_m_new))
                st.success("月目標を保存しました。"); st.rerun()
            except Exception:
                local_set_target(ym, "app", int(t_app_m_new)); local_set_target(ym, "survey", int(t_sur_m_new))
                st.success("月目標を保存しました。（ローカルに保存）"); st.rerun()

    def pct(a,b): return (a/b*100.0) if b and b>0 else 0.0
    m1, m2, m3 = st.columns(3)
    with m1: st.metric("and st（月）実績", f"{month_app} 件")
    with m2: st.metric("and st（月）目標", f"{t_app_m} 件")
    with m3: st.metric("and st（月）達成率", f"{pct(month_app, t_app_m):.1f}%")
    k1, k2, k3 = st.columns(3)
    with k1: st.metric("アンケート（月）実績", f"{month_survey} 件")
    with k2: st.metric("アンケート（月）目標", f"{t_sur_m} 件")
    with k3: st.metric("アンケート（月）達成率", f"{pct(month_survey, t_sur_m):.1f}%")

# -----------------------------
# 統計表示（男生版に合わせる）
# -----------------------------
def show_statistics(category: str, label: str):
    df_all = ensure_dataframe(st.session_state.get("data", []))
    st.subheader(label)
    if df_all.empty:
        st.info("データがありません。"); return

    # カテゴリ分岐
    if category == "app":
        df_cat = df_all[df_all["type"].isin(["new","exist","line"])].copy()
    else:
        df_cat = df_all[df_all["type"]=="survey"].copy()
    if df_cat.empty:
        st.info("対象データがありません。"); return

    # ===== 週別合計（年→月 下拉選單）=====
    st.subheader("週別合計")
    yearsW = year_options(df_cat)
    defaultY = date.today().year if date.today().year in yearsW else yearsW[-1]
    cY, cM = st.columns(2)
    with cY:
        y_sel = st.selectbox("年（週集計）", options=yearsW, index=yearsW.index(defaultY), key=f"weekly_year_{label}")
    with cM:
        months = sorted(set(df_cat[df_cat["date"].dt.year==int(y_sel)]["date"].dt.strftime("%Y-%m").dropna().tolist()))
        if not months: months = [f"{y_sel}-01"]
        defaultM = date.today().strftime("%Y-%m") if date.today().year==int(y_sel) and date.today().strftime("%Y-%m") in months else months[-1]
        m_sel = st.selectbox("月", options=months, index=months.index(defaultM), key=f"weekly_month_{label}")
    dfm = df_cat[df_cat["date"].dt.strftime("%Y-%m")==m_sel].copy()
    if dfm.empty:
        st.info("この月のデータがありません。")
    else:
        dfm["week_iso"] = dfm["date"].dt.isocalendar().week.astype(int)
        uniq = sorted(dfm["week_iso"].unique().tolist())
        wmap = {wk:i+1 for i, wk in enumerate(uniq)}
        dfm["w_num"] = dfm["week_iso"].map(wmap)
        weekly = dfm.groupby("w_num")["count"].sum().reset_index().sort_values("w_num")
        weekly["w"] = weekly["w_num"].apply(lambda x: f"w{x}")
        st.caption(f"表示中：{y_sel}年・{m_sel}")
        st.dataframe(weekly[["w","count"]].rename(columns={"count":"合計"}), use_container_width=True)

    # ===== 構成比（新規・既存・LINE）=====
    if category == "app":
        st.subheader("構成比（新規・既存・LINE）")
        cY2, cT, cSel = st.columns([1,1,2])
        years2 = year_options(df_cat)
        defaultY2 = date.today().year if date.today().year in years2 else years2[-1]
        with cY2:
            y2 = st.selectbox("年", options=years2, index=years2.index(defaultY2), key=f"comp_year_{label}")
        with cT:
            mode = st.selectbox("対象期間", ["週（単週）","月（単月）","年（単年）"], key=f"comp_mode_{label}")
        with cSel:
            opts, default = _period_options(df_cat, mode, y2)
            idx = opts.index(default) if default in opts else 0
            sel = st.selectbox("表示する期間", options=opts, index=idx, key=f"comp_value_{label}")
        base = df_cat.copy()
        filt = _filter_by_period(base, mode, sel, y2)
        new_sum  = int(filt[filt["type"]=="new"]["count"].sum())
        exist_sum= int(filt[filt["type"]=="exist"]["count"].sum())
        line_sum = int(filt[filt["type"]=="line"]["count"].sum())
        total = new_sum + exist_sum + line_sum
        if total>0:
            st.caption(f"表示中：{y2}年" if mode=="年（単年）" else f"表示中：{y2}年・{sel}")
            fig = plt.figure()
            # 英文ラベル固定（乱碼回避）
            labels = ["new","exist","LINE"]
            plt.pie([new_sum, exist_sum, line_sum], labels=labels, autopct="%1.1f%%", startangle=90)
            st.pyplot(fig)
        else:
            st.info("対象データがありません。")

    # ===== スタッフ別 合計（順位／スタッフ／合計 の表）=====
    st.subheader("スタッフ別 合計")
    cY3, cT3, cSel3 = st.columns([1,1,2])
    years3 = year_options(df_cat)
    defaultY3 = date.today().year if date.today().year in years3 else years3[-1]
    with cY3:
        y3 = st.selectbox("年", options=years3, index=years3.index(defaultY3), key=f"staff_year_{label}")
    with cT3:
        mode3 = st.selectbox("対象期間", ["週（単週）","月（単月）","年（単年）"], key=f"staff_mode_{label}")
    with cSel3:
        opts3, def3 = _period_options(df_cat, mode3, y3)
        idx3 = opts3.index(def3) if def3 in opts3 else 0
        sel3 = st.selectbox("表示する期間", options=opts3, index=idx3, key=f"staff_value_{label}")
    st.caption(f"（{y3}年・{sel3 if mode3!='年（単年）' else '年合計'}）")
    filt3 = _filter_by_period(df_cat.copy(), mode3, sel3, y3)
    if filt3.empty:
        st.info("対象データがありません。")
    else:
        staff_sum = (
            filt3.groupby("name")["count"].sum()
            .reset_index()
            .sort_values("count", ascending=False)
            .reset_index(drop=True)
        )
        staff_sum.insert(0, "順位", staff_sum.index + 1)
        if len(staff_sum) > 0:
            staff_sum.loc[0, "順位"] = f"{staff_sum.loc[0, '順位']} 👑"
        staff_sum = staff_sum.rename(columns={"name":"スタッフ","count":"合計"})
        st.dataframe(staff_sum[["順位","スタッフ","合計"]], use_container_width=True)

    # ===== 月別累計（年次）— 棒グラフ（各月の獲得数）=====
    st.subheader("月別累計（年次）")
    years4 = year_options(df_cat)
    defaultY4 = date.today().year if date.today().year in years4 else years4[-1]
    y4 = st.selectbox("年を選択", options=years4, index=years4.index(defaultY4), key=f"monthly_year_{label}")
    df_year = df_cat[df_cat["date"].dt.year == int(y4)]
    if df_year.empty:
        st.info("対象データがありません。")
    else:
        monthly = (
            df_year.groupby(df_year["date"].dt.strftime("%Y-%m"))["count"]
            .sum()
            .reindex([f"{y4}-{str(m).zfill(2)}" for m in range(1,13)], fill_value=0)
        )
        labels = [calendar.month_abbr[int(s.split('-')[1])] for s in monthly.index.tolist()]  # Jan, Feb, ...
        values = monthly.values.tolist()
        fig2 = plt.figure()
        bars = plt.bar(labels, values)
        plt.grid(True, axis="y", linestyle="--", linewidth=0.5)
        plt.xticks(rotation=0, ha="center")
        plt.title(f"{'and st' if category=='app' else 'Survey'} Monthly totals ({int(y4)})")
        ymax = max(values) if values else 0
        if ymax>0:
            plt.ylim(0, ymax*1.15)
        for b, v in zip(bars, values):
            plt.text(b.get_x()+b.get_width()/2, b.get_height(), f"{int(v)}", ha="center", va="bottom", fontsize=9)
        st.pyplot(fig2)

# -----------------------------
# and st 分析
# -----------------------------
with tab_app_ana:
    show_statistics("app", "and st 分析")

# -----------------------------
# アンケート分析
# -----------------------------
with tab_survey_ana:
    show_statistics("survey", "アンケート分析")

# -----------------------------
# データ管理
# -----------------------------
with tab_manage:
    try:
        show_data_management()
    except Exception as e:
        st.error(f"データ管理画面の読み込みに失敗しました: {e}")
