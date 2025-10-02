# -*- coding: utf-8 -*-
import os
from datetime import date
import uuid

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

# -----------------------------
# Page config & title
# -----------------------------
try:
    st.set_page_config(page_title="and st 統計Team W’s", page_icon="icon.png", layout="centered")
except Exception:
    pass

st.title("Team W’s")

# -----------------------------
# Japanese font (best-effort; 防止日文亂碼)
# -----------------------------
from matplotlib import font_manager, rcParams

JP_FONT_READY = False
try_candidates = [
    os.path.join(os.path.dirname(__file__), "fonts", "NotoSansJP-Regular.otf"),
    os.path.join(os.path.dirname(__file__), "NotoSansJP-Regular.otf"),
    "/mnt/data/NotoSansJP-Regular.otf",
]
try:
    for fp in try_candidates:
        if os.path.exists(fp):
            font_manager.fontManager.addfont(fp)
            _prop = font_manager.FontProperties(fname=fp)
            rcParams["font.family"] = _prop.get_name()
            JP_FONT_READY = True
            break
    if not JP_FONT_READY:
        _JP_FONT_CANDIDATES = [
            "Noto Sans CJK JP", "Noto Sans JP", "IPAGothic", "IPAexGothic",
            "TakaoGothic", "Yu Gothic", "Hiragino Sans", "Meiryo", "MS Gothic",
        ]
        available = {f.name for f in font_manager.fontManager.ttflist}
        for _name in _JP_FONT_CANDIDATES:
            if _name in available:
                rcParams["font.family"] = _name
                JP_FONT_READY = True
                break
except Exception:
    JP_FONT_READY = False

rcParams["axes.unicode_minus"] = False

# -----------------------------
# Backend（沿用你的模組）
# -----------------------------
from db_gsheets import (
    init_db,
    init_target_table,
    load_all_records,
    insert_or_update_record,
    get_target,
    set_target,
)
from data_management import show_data_management

# -----------------------------
# Cache / Init
# -----------------------------
@st.cache_resource
def _init_once():
    init_db()
    init_target_table()
    return True

@st.cache_data(ttl=60)
def load_all_records_cached():
    return load_all_records()

@st.cache_data(ttl=60)
def get_target_safe(month: str, category: str) -> int:
    try:
        return get_target(month, category)
    except Exception:
        return 0

# -----------------------------
# Utils
# -----------------------------
def ymd(d: date) -> str:
    return d.strftime("%Y-%m-%d")

def current_year_month() -> str:
    return date.today().strftime("%Y-%m")

def ensure_dataframe(records) -> pd.DataFrame:
    df = pd.DataFrame(records or [])
    for col in ["date", "name", "type", "count"]:
        if col not in df.columns:
            df[col] = None
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)
    return df

def month_filter(df: pd.DataFrame, ym: str) -> pd.DataFrame:
    if "date" not in df.columns:
        return df.iloc[0:0]
    return df[(df["date"].dt.strftime("%Y-%m") == ym)]

def names_from_records(records) -> list:
    return sorted({(r.get("name") or "").strip() for r in (records or []) if r.get("name")})

# ---- Year / Week helpers ----
def year_options(df: pd.DataFrame) -> list:
    if "date" not in df.columns or df["date"].isna().all():
        return [date.today().year]
    years = sorted(set(df["date"].dropna().dt.year.astype(int).tolist()))
    return years or [date.today().year]

def _week_label(week_number: int) -> str:
    """直接用 ISO 週：例如 40 -> 'w40'"""
    return f"w{int(week_number)}"

# ---- 期間選項 / 過濾（供分析頁用，維持你既有操作手感）----
def _period_options(df: pd.DataFrame, mode: str, selected_year: int):
    if "date" not in df.columns or df["date"].isna().all():
        today = date.today()
        if mode == "週（単週）":
            ww = today.isocalendar().week
            return [f"w{ww}"], f"w{ww}"
        elif mode == "月（単月）":
            dft = today.strftime("%Y-%m"); return [dft], dft
        else:
            return [today.year], today.year

    dfx = df.dropna(subset=["date"]).copy()
    if mode == "週（単週）":
        dyear = dfx[dfx["date"].dt.year == int(selected_year)]
        weeks = sorted(set(dyear["date"].dt.isocalendar().week.astype(int).tolist()))
        labels = [f"w{w}" for w in weeks] or [f"w{date.today().isocalendar().week}"]
        default = f"w{date.today().isocalendar().week}"
        if default not in labels: default = labels[0]
        return labels, default
    elif mode == "月（単月）":
        dyear = dfx[dfx["date"].dt.year == int(selected_year)]
        months = sorted(set(dyear["date"].dt.strftime("%Y-%m").tolist()))
        if not months: months = [f"{selected_year}-01"]
        default = date.today().strftime("%Y-%m") if date.today().year == int(selected_year) else months[-1]
        if default not in months: default = months[0]
        return months, default
    else:  # 年
        ys = year_options(dfx)
        default = date.today().year if date.today().year in ys else ys[-1]
        return ys, default

def _filter_by_period(df: pd.DataFrame, mode: str, value, selected_year: int) -> pd.DataFrame:
    if "date" not in df.columns or df["date"].isna().all():
        return df.iloc[0:0]
    dfx = df.dropna(subset=["date"]).copy()
    if mode == "週（単週）":
        dyear = dfx[dfx["date"].dt.year == int(selected_year)]
        try:
            want = int(str(value).lower().lstrip("w"))
        except Exception:
            return dyear.iloc[0:0]
        return dyear[dyear["date"].dt.isocalendar().week.astype(int).isin([want])]
    elif mode == "月（単月）":
        dyear = dfx[dfx["date"].dt.year == int(selected_year)]
        return dyear[dyear["date"].dt.strftime("%Y-%m") == str(value)]
    else:
        return dfx[dfx["date"].dt.year == int(selected_year)]

# -----------------------------
# Session init
# -----------------------------
def init_session():
    if "data" not in st.session_state:
        st.session_state.data = load_all_records_cached()
    if "names" not in st.session_state:
        st.session_state.names = names_from_records(st.session_state.data)

_init_once()
init_session()

def render_refresh_button(btn_key: str = "refresh_btn"):
    spacer, right = st.columns([12, 1])
    with right:
        if st.button("↻", key=btn_key, help="重新整理資料"):
            load_all_records_cached.clear()
            st.session_state.data = load_all_records_cached()
            st.rerun()

# -----------------------------
# 能量條達成率（第一頁用）
# -----------------------------
def render_rate_block(category: str, label: str, current_total: int, target: int, ym: str):
    """
    以能量條呈現達成率，右側可設定月目標。
    category: "app" 或 "survey"
    """
    pct = 0 if target <= 0 else min(100.0, round(current_total * 100.0 / max(1, target), 1))
    bar_id = f"meter_{category}_{uuid.uuid4().hex[:6]}"

    st.markdown(
        f"""
<div style="font-size:14px;opacity:.85;">
  {ym} の累計：<b>{current_total}</b> 件 ／ 目標：<b>{target}</b> 件
</div>
<div id="{bar_id}" style="
  margin-top:8px;height:18px;border-radius:9px;
  background:rgba(0,0,0,.10);overflow:hidden;">
  <div style="height:100%;width:{pct}%;
    background:linear-gradient(90deg,#16a34a,#22c55e,#4ade80);
    box-shadow:0 0 12px rgba(34,197,94,.45) inset;"></div>
</div>
<div style="margin-top:6px;font-size:13px;opacity:.8;">
  達成率：<b>{pct:.1f}%</b>
</div>
""",
        unsafe_allow_html=True,
    )

    with st.popover(f"🎯 目標を設定/更新（{label}）", use_container_width=True):
        new_target = st.number_input("月目標", min_value=0, step=1, value=int(target), key=f"target_input_{category}")
        if st.button("保存", key=f"target_save_{category}"):
            try:
                set_target(ym, "app" if category == "app" else "survey", int(new_target))
                try:
                    get_target_safe.clear()  # 若不存在可忽略
                except Exception:
                    pass
                st.success("保存しました。")
            except Exception as e:
                st.error(f"保存失敗: {e}")

# -----------------------------
# 分析（沿用你熟悉的樣式）
# -----------------------------
def show_statistics(category: str, label: str):
    df_all = ensure_dataframe(st.session_state.data)
    ym = current_year_month()

    # --- 週別合計（ISO 週 w40 樣式）---
    st.subheader("週別合計")
    yearsW = year_options(df_all)
    default_yearW = date.today().year if date.today().year in yearsW else yearsW[-1]
    colY, colM = st.columns(2)
    with colY:
        yearW = st.selectbox("年（週集計）", options=yearsW, index=yearsW.index(default_yearW), key=f"weekly_year_{category}")
    months_in_year = sorted(set(
        df_all[df_all["date"].dt.year == int(yearW)]["date"].dt.strftime("%Y-%m").dropna().tolist()
    )) or [f"{yearW}-{str(date.today().month).zfill(2)}"]
    default_monthW = (
        date.today().strftime("%Y-%m")
        if (date.today().year == int(yearW) and date.today().strftime("%Y-%m") in months_in_year)
        else months_in_year[-1]
    )
    with colM:
        monthW = st.selectbox("月", options=months_in_year, index=months_in_year.index(default_monthW), key=f"weekly_month_{category}")

    df_monthW = df_all[df_all["date"].dt.strftime("%Y-%m") == monthW].copy()
    if category == "app":
        df_monthW = df_monthW[df_monthW["type"].isin(["new", "exist", "line"])]
    else:
        df_monthW = df_monthW[df_monthW["type"] == "survey"]

    if df_monthW.empty:
        st.info("この月のデータがありません。")
    else:
        df_monthW["iso_week"] = df_monthW["date"].dt.isocalendar().week.astype(int)
        weekly = df_monthW.groupby("iso_week")["count"].sum().reset_index().sort_values("iso_week")
        weekly["w"] = weekly["iso_week"].map(_week_label)
        st.caption(f"表示中：{yearW}年・{monthW}")
        st.dataframe(weekly[["w", "count"]].rename(columns={"count": "合計"}), use_container_width=True)

    # --- 構成比（新規・既存・LINE）— App only；標籤用英文避免亂碼 ---
    if category == "app":
        st.subheader("構成比（新規・既存・LINE）")
        colYc, colp1, colp2 = st.columns([1, 1, 2])
        years = year_options(df_all)
        default_year = date.today().year if date.today().year in years else years[-1]
        with colYc:
            year_sel = st.selectbox("年", options=years, index=years.index(default_year), key=f"comp_year_{category}")
        with colp1:
            ptype = st.selectbox("対象期間", ["週（単週）", "月（単月）", "年（単年）"], key=f"comp_period_type_{category}")
        with colp2:
            opts, default = _period_options(df_all, ptype, year_sel)
            idx = opts.index(default) if default in opts else 0
            sel = st.selectbox("表示する期間", options=opts, index=idx if len(opts) > 0 else 0, key=f"comp_period_value_{category}")

        df_comp_base = df_all[df_all["type"].isin(["new", "exist", "line"])].copy()
        df_comp = _filter_by_period(df_comp_base, ptype, sel, year_sel)
        new_sum  = int(df_comp[df_comp["type"] == "new"]["count"].sum())
        exist_sum= int(df_comp[df_comp["type"] == "exist"]["count"].sum())
        line_sum = int(df_comp[df_comp["type"] == "line"]["count"].sum())
        total = new_sum + exist_sum + line_sum

        if total > 0:
            st.caption(f"表示中：{year_sel}年" if ptype=="年（単年）" else f"表示中：{year_sel}年・{sel}")
            plt.figure()
            labels = ["new", "exist", "LINE"]  # 英文標籤，避免亂碼
            plt.pie([new_sum, exist_sum, line_sum], labels=labels, autopct="%1.1f%%", startangle=90)
            st.pyplot(plt.gcf())
        else:
            st.info("対象データがありません。")

    # --- スタッフ別 合計（表格；頭名加👑）---
    st.subheader("スタッフ別 合計")
    colYs, cpt1, cpt2 = st.columns([1, 1, 2])
    years2 = year_options(df_all)
    default_year2 = date.today().year if date.today().year in years2 else years2[-1]
    with colYs:
        year_sel2 = st.selectbox("年", options=years2, index=years2.index(default_year2), key=f"staff_year_{category}")
    with cpt1:
        ptype2 = st.selectbox("対象期間", ["週（単週）", "月（単月）", "年（単年）"], key=f"staff_period_type_{category}", index=0)
    with cpt2:
        opts2, default2 = _period_options(df_all, ptype2, year_sel2)
        idx2 = opts2.index(default2) if default2 in opts2 else 0
        sel2 = st.selectbox("表示する期間", options=opts2, index=idx2 if len(opts2) > 0 else 0, key=f"staff_period_value_{category}")
    st.caption(f"（{year_sel2}年・{sel2 if ptype2!='年（単年）' else '年合計'}）")

    if category == "app":
        df_staff_base = df_all[df_all["type"].isin(["new", "exist", "line"])].copy()
    else:
        df_staff_base = df_all[df_all["type"] == "survey"].copy()

    df_staff = _filter_by_period(df_staff_base, ptype2, sel2, year_sel2)
    if df_staff.empty:
        st.info("対象データがありません。")
    else:
        staff_sum = (
            df_staff.groupby("name")["count"].sum()
            .reset_index()
            .sort_values("count", ascending=False)
            .reset_index(drop=True)
        )
        staff_sum.insert(0, "順位", staff_sum.index + 1)
        if len(staff_sum) > 0:
            staff_sum.loc[0, "順位"] = f"{staff_sum.loc[0, '順位']} 👑"
        staff_sum = staff_sum.rename(columns={"name": "スタッフ", "count": "合計"})
        st.dataframe(staff_sum[["順位", "スタッフ", "合計"]], use_container_width=True)

    # --- 月別累計（年次）---
    st.subheader("月別累計（年次）")
    years3 = year_options(df_all)
    default_year3 = date.today().year if date.today().year in years3 else years3[-1]
    year_sel3 = st.selectbox("年を選択", options=years3, index=years3.index(default_year3), key=f"monthly_year_{category}")

    if category == "app":
        df_year = df_all[(df_all["date"].dt.year == int(year_sel3)) & (df_all["type"].isin(["new", "exist", "line"]))]
        title_label = "and st"
    else:
        df_year = df_all[(df_all["date"].dt.year == int(year_sel3)) & (df_all["type"] == "survey")]
        title_label = "Survey"

    if df_year.empty:
        st.info("対象データがありません。")
    else:
        import calendar
        monthly = (
            df_year.groupby(df_year["date"].dt.strftime("%Y-%m"))["count"]
            .sum()
            .reindex([f"{year_sel3}-{str(m).zfill(2)}" for m in range(1, 13)], fill_value=0)
        )
        labels = [calendar.month_abbr[int(s.split("-")[1])] for s in monthly.index.tolist()]
        values = monthly.values.tolist()

        plt.figure()
        bars = plt.bar(labels, values)
        plt.grid(True, axis="y", linestyle="--", linewidth=0.5)
        plt.xticks(rotation=0, ha="center")
        plt.title(f"{title_label} Monthly totals ({int(year_sel3)})")
        ymax = max(values) if values else 0
        if ymax > 0:
            plt.ylim(0, ymax * 1.15)
        for bar, val in zip(bars, values):
            plt.text(bar.get_x() + bar.get_width()/2, bar.get_height(), f"{int(val)}", ha="center", va="bottom", fontsize=9)
        st.pyplot(plt.gcf())

# -----------------------------
# Tabs（第一頁 = 合併的 件数登録；其他分頁不動）
# -----------------------------
tab_reg, tab3, tab4, tab5 = st.tabs(["件数登録", "and st 分析", "アンケート分析", "データ管理"])

# -----------------------------
# 件数登録（and st + アンケート 合併頁）
# -----------------------------
with tab_reg:
    st.subheader("件数登録")
    with st.form("reg_form"):
        c1, c2 = st.columns([2, 2])
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

        st.markdown("#### and st（新規 / 既存 / LINE）")
        coln1, coln2, coln3 = st.columns(3)
        with coln1: new_cnt = st.number_input("新規（件）", min_value=0, step=1, value=0, key="reg_new")
        with coln2: exist_cnt = st.number_input("既存（件）", min_value=0, step=1, value=0, key="reg_exist")
        with coln3: line_cnt = st.number_input("LINE（件）", min_value=0, step=1, value=0, key="reg_line")

        st.markdown("#### アンケート")
        survey_cnt = st.number_input("アンケート（件）", min_value=0, step=1, value=0, key="reg_survey")

        submitted = st.form_submit_button("保存")
        if submitted:
            if not name:
                st.warning("名前を入力してください。")
            else:
                try:
                    # and st
                    if int(new_cnt) > 0:   insert_or_update_record(ymd(d), name, "new",   int(new_cnt))
                    if int(exist_cnt) > 0: insert_or_update_record(ymd(d), name, "exist", int(exist_cnt))
                    if int(line_cnt)  > 0: insert_or_update_record(ymd(d), name, "line",  int(line_cnt))
                    # アンケート
                    if int(survey_cnt) > 0: insert_or_update_record(ymd(d), name, "survey", int(survey_cnt))

                    # 若全 0，僅註冊姓名
                    if sum([int(new_cnt), int(exist_cnt), int(line_cnt), int(survey_cnt)]) == 0:
                        st.session_state.names = sorted(set(st.session_state.names) | {name})
                        st.success("名前を登録しました。（データは追加していません）")
                    else:
                        load_all_records_cached.clear()
                        st.session_state.data = load_all_records_cached()
                        st.session_state.names = names_from_records(st.session_state.data)
                        st.success("保存しました。")
                except Exception as e:
                    st.error(f"保存失敗: {e}")

    # === 達成率（能量條；and st / アンケート）===
    df_all = ensure_dataframe(st.session_state.data)
    ym = current_year_month()
    df_m = month_filter(df_all, ym)
    app_total = int(df_m[df_m["type"].isin(["new", "exist", "line"])]["count"].sum())
    survey_total = int(df_m[df_m["type"] == "survey"]["count"].sum())
    try:
        app_target = get_target(ym, "app")
    except Exception:
        app_target = 0
    try:
        survey_target = get_target(ym, "survey")
    except Exception:
        survey_target = 0

    st.markdown("### 達成率")
    _c1, _c2 = st.columns(2)
    with _c1:
        st.caption("and st")
        render_rate_block("app", "and st", app_total, app_target, ym)
    with _c2:
        st.caption("アンケート")
        render_rate_block("survey", "アンケート", survey_total, survey_target, ym)

    render_refresh_button("refresh_reg_tab")

# -----------------------------
# and st 分析（保持原樣式）
# -----------------------------
with tab3:
    show_statistics("app", "and st")

# -----------------------------
# アンケート分析（保持原樣式）
# -----------------------------
with tab4:
    show_statistics("survey", "アンケート")

# -----------------------------
# データ管理（保持原樣式）
# -----------------------------
with tab5:
    try:
        show_data_management()
    except Exception as e:
        st.error(f"データ管理画面の読み込みに失敗しました: {e}")

