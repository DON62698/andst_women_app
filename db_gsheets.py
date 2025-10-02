# -*- coding: utf-8 -*-
"""
db_gsheets.py
與 Streamlit 主程式相容的 Google Sheets 後端。
- 若無金鑰/網路錯誤 => 自動啟用本機 fallback（session_state）
- 主要工作表：
  1) records: ["date","week","name","type","count"]
  2) targets: ["month","category","target"]
"""

from __future__ import annotations
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import streamlit as st

# 後端相依（允許缺少）
_GSPREAD_OK = True
try:
    import gspread
    from gspread.exceptions import WorksheetNotFound, APIError as _GSpreadAPIError
    from oauth2client.service_account import ServiceAccountCredentials
except Exception:
    _GSPREAD_OK = False


# =========================================================
# 常數
# =========================================================
RECORDS_SHEET = "records"
TARGETS_SHEET = "targets"

RECORDS_HEADER = ["date", "week", "name", "type", "count"]
TARGETS_HEADER = ["month", "category", "target"]

# gspread 權限範圍
_SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


# =========================================================
# 模組內部快取
# =========================================================
_client = None
_book = None
_backend_available = False  # True = 使用 GSheets；False = 使用本機 fallback


# =========================================================
# 工具：安全讀 secrets
# =========================================================
def _read_secrets() -> Tuple[Optional[dict], Optional[str]]:
    """從 st.secrets 取得金鑰與 spreadsheet URL；缺少則回傳 (None, None)。"""
    creds_dict = None
    sheet_url = None
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
        if "sheets" in st.secrets and "url" in st.secrets["sheets"]:
            sheet_url = str(st.secrets["sheets"]["url"]).strip()
    except Exception:
        pass
    return creds_dict, sheet_url


# =========================================================
# 工具：Client / Book
# =========================================================
def _client_and_book() -> Tuple[Optional[object], Optional[object]]:
    """建立 gspread client 並開啟 spreadsheet。失敗則回傳 (None, None)。"""
    global _client, _book
    if _client is not None and _book is not None:
        return _client, _book

    if not _GSPREAD_OK:
        return None, None

    creds_dict, sheet_url = _read_secrets()
    if not creds_dict or not sheet_url:
        return None, None

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, _SCOPE)
        _client = gspread.authorize(creds)
        _book = _client.open_by_url(sheet_url)
        return _client, _book
    except Exception:
        return None, None


# =========================================================
# 工具：安全的 ensure_worksheet
# =========================================================
def _ensure_worksheet(sh, name: str, header: List[str]):
    """
    回傳一個保證存在且 A1=header 的試算表分頁。
    - 缺就新建
    - 標題列不對就回填
    - 任何錯誤盡量吸收，避免讓前端掛掉
    """
    if sh is None:
        return None

    try:
        try:
            ws = sh.worksheet(name)
        except WorksheetNotFound:
            # 建立分頁（至少 26 欄，避免更新範圍不足）
            ws = sh.add_worksheet(title=name, rows=1000, cols=max(26, len(header)))
            try:
                ws.update("A1", [header])
            except Exception:
                pass
            return ws

        # 嘗試讀第一列；若 APIError 當空列處理
        try:
            first_row = ws.row_values(1)
        except Exception:
            first_row = []

        normalized = [str(c).strip() for c in (first_row or [])]
        if normalized[:len(header)] != header:
            # 確保欄數足夠
            try:
                if ws.col_count < len(header):
                    ws.resize(rows=max(ws.row_count, 1000), cols=max(26, len(header)))
            except Exception:
                pass
            # 計算 A..Z.. 的結尾欄（header 長度 <= 26）
            try:
                end_col = chr(64 + min(len(header), 26))  # 1->A, 2->B ... 26->Z
                ws.update(f"A1:{end_col}1", [header])
            except Exception:
                try:
                    ws.update("A1", [header])
                except Exception:
                    pass

        return ws

    except Exception:
        # 最保守 fallback：再試一次取舊的；不 raise，讓前端以本機模式續跑
        try:
            ws = sh.worksheet(name)
            return ws
        except Exception:
            try:
                ws = sh.add_worksheet(title=name, rows=1000, cols=max(26, len(header)))
                try:
                    ws.update("A1", [header])
                except Exception:
                    pass
                return ws
            except Exception:
                return None


# =========================================================
# 初始化 / 表頭建立
# =========================================================
def init_db() -> None:
    """初始化後端；若失敗則切換本機 fallback。"""
    global _backend_available
    cl, bk = _client_and_book()
    if cl and bk:
        # 先嘗試建立/修復兩張工作表
        _ensure_worksheet(bk, RECORDS_SHEET, RECORDS_HEADER)
        _ensure_worksheet(bk, TARGETS_SHEET, TARGETS_HEADER)
        _backend_available = True
        st.session_state["_backend_error"] = ""  # 清空舊錯
    else:
        _backend_available = False
        st.session_state.setdefault("_backend_error", "Sheets backend not available; local mode enabled.")

    # 初始化本機 fallback 結構
    st.session_state.setdefault("_local_records", [])   # list[dict]
    st.session_state.setdefault("_local_targets", {})   # {(month, category): target}


def init_target_table() -> None:
    """確保 targets 表存在（雖然 init_db 已處理，這裡保險再呼叫一次）。"""
    cl, bk = _client_and_book()
    if not (_backend_available and cl and bk):
        return
    _ensure_worksheet(bk, TARGETS_SHEET, TARGETS_HEADER)


# =========================================================
# 讀取 / 寫入：records
# =========================================================
def load_all_records() -> List[Dict]:
    """
    回傳所有紀錄為 list[dict]:
    { "date": "YYYY-MM-DD", "week": int, "name": str, "type": "new|exist|line|survey", "count": int }
    """
    if not _backend_available:
        # 本機 fallback
        return list(st.session_state.get("_local_records", []))

    cl, bk = _client_and_book()
    if not (cl and bk):
        # 失去連線時 fallback
        return list(st.session_state.get("_local_records", []))

    ws = _ensure_worksheet(bk, RECORDS_SHEET, RECORDS_HEADER)
    if ws is None:
        return list(st.session_state.get("_local_records", []))

    try:
        values = ws.get_all_values()
    except Exception as e:
        st.session_state["_backend_error"] = f"read records failed: {e}"
        return list(st.session_state.get("_local_records", []))

    if not values or len(values) <= 1:
        return []

    header = [c.strip() for c in values[0]]
    rows = values[1:]

    idx = {k: header.index(k) if k in header else -1 for k in RECORDS_HEADER}

    out: List[Dict] = []
    for r in rows:
        try:
            d = (r[idx["date"]].strip() if idx["date"] >= 0 and idx["date"] < len(r) else "")
            nm = (r[idx["name"]].strip() if idx["name"] >= 0 and idx["name"] < len(r) else "")
            tp = (r[idx["type"]].strip() if idx["type"] >= 0 and idx["type"] < len(r) else "")
            cnt_raw = (r[idx["count"]].strip() if idx["count"] >= 0 and idx["count"] < len(r) else "0")
            try:
                cnt = int(cnt_raw)
            except Exception:
                cnt = 0

            # week 欄位若不存在則即時計算
            if idx["week"] >= 0 and idx["week"] < len(r) and r[idx["week"]].strip():
                try:
                    wk = int(r[idx["week"]])
                except Exception:
                    wk = _iso_week_of(d)
            else:
                wk = _iso_week_of(d)

            if not d or not nm or not tp:
                continue

            out.append({
                "date": d, "week": wk, "name": nm, "type": tp, "count": cnt
            })
        except Exception:
            continue

    return out


def _iso_week_of(date_str: str) -> int:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        return int(dt.isocalendar().week)
    except Exception:
        return 0


def insert_or_update_record(date_str: str, name: str, typ: str, count: int) -> None:
    """
    以 (date, name, type) 為 key：
    - 若已存在 => 將 count「加總」到既有值
    - 若不存在 => 直接 append
    """
    # 先算 ISO 週
    week_num = _iso_week_of(date_str)

    if not _backend_available:
        # 本機 fallback：以 list 模擬
        recs = st.session_state.get("_local_records", [])
        # 尋找是否存在
        for row in recs:
            if row["date"] == date_str and row["name"] == name and row["type"] == typ:
                row["count"] = int(row.get("count", 0)) + int(count)
                st.session_state["_local_records"] = recs
                return
        # 新增
        recs.append({"date": date_str, "week": week_num, "name": name, "type": typ, "count": int(count)})
        st.session_state["_local_records"] = recs
        return

    cl, bk = _client_and_book()
    ws = _ensure_worksheet(bk, RECORDS_SHEET, RECORDS_HEADER)
    if ws is None:
        # 退回本機
        insert_or_update_record_local(date_str, name, typ, count, week_num)
        return

    try:
        values = ws.get_all_values()
        header = values[0] if values else RECORDS_HEADER
        # 建立欄位索引
        idx = {k: header.index(k) if k in header else -1 for k in RECORDS_HEADER}

        # 找現有列（簡單掃描）
        target_row_index = -1
        for i in range(1, len(values)):
            r = values[i]
            d_ok = (idx["date"] >= 0 and idx["date"] < len(r) and r[idx["date"]].strip() == date_str)
            n_ok = (idx["name"] >= 0 and idx["name"] < len(r) and r[idx["name"]].strip() == name)
            t_ok = (idx["type"] >= 0 and idx["type"] < len(r) and r[idx["type"]].strip() == typ)
            if d_ok and n_ok and t_ok:
                target_row_index = i + 1  # 1-based row number
                break

        if target_row_index > 0:
            # 讀舊 count
            old_val = 0
            try:
                old_val_str = values[target_row_index - 1][idx["count"]]
                old_val = int(old_val_str)
            except Exception:
                old_val = 0
            new_val = old_val + int(count)

            # 更新 count
            cnt_col = idx["count"] + 1  # 1-based col
            ws.update_cell(target_row_index, cnt_col, new_val)

            # week 也補上
            if idx["week"] >= 0:
                ws.update_cell(target_row_index, idx["week"] + 1, week_num)
            return
        else:
            # 直接 append：順序照 HEADER
            row = ["", "", "", "", ""]
            # date
            if idx["date"] >= 0:
                row[idx["date"]] = date_str
            # week
            if idx["week"] >= 0:
                row[idx["week"]] = week_num
            # name
            if idx["name"] >= 0:
                row[idx["name"]] = name
            # type
            if idx["type"] >= 0:
                row[idx["type"]] = typ
            # count
            if idx["count"] >= 0:
                row[idx["count"]] = int(count)

            # 若 header 有缺欄，仍用 A..E 寫入
            end_col = chr(64 + min(len(RECORDS_HEADER), 26))
            ws.append_row(row[:len(RECORDS_HEADER)], value_input_option="RAW", table_range=f"A1:{end_col}1")
            return

    except Exception:
        # 寫入失敗 -> 改寫入本機，避免整體流程中斷
        insert_or_update_record_local(date_str, name, typ, count, week_num)


def insert_or_update_record_local(date_str: str, name: str, typ: str, count: int, week_num: Optional[int] = None):
    """本機 fallback 的寫入。"""
    if week_num is None:
        week_num = _iso_week_of(date_str)
    recs = st.session_state.get("_local_records", [])
    for row in recs:
        if row["date"] == date_str and row["name"] == name and row["type"] == typ:
            row["count"] = int(row.get("count", 0)) + int(count)
            st.session_state["_local_records"] = recs
            return
    recs.append({"date": date_str, "week": week_num, "name": name, "type": typ, "count": int(count)})
    st.session_state["_local_records"] = recs


# =========================================================
# 讀取 / 寫入：targets
# =========================================================
def get_target(month: str, category: str) -> int:
    """
    取得月目標；無則回 0。
    month: "YYYY-MM"
    category: "app" or "survey"
    """
    if not _backend_available:
        key = (month, category)
        return int(st.session_state.get("_local_targets", {}).get(key, 0))

    cl, bk = _client_and_book()
    ws = _ensure_worksheet(bk, TARGETS_SHEET, TARGETS_HEADER)
    if ws is None:
        # fallback
        key = (month, category)
        return int(st.session_state.get("_local_targets", {}).get(key, 0))

    try:
        values = ws.get_all_values()
        if not values or len(values) <= 1:
            return 0

        header = [c.strip() for c in values[0]]
        idx_m = header.index("month") if "month" in header else -1
        idx_c = header.index("category") if "category" in header else -1
        idx_t = header.index("target") if "target" in header else -1

        for i in range(1, len(values)):
            r = values[i]
            m_ok = (idx_m >= 0 and idx_m < len(r) and r[idx_m].strip() == month)
            c_ok = (idx_c >= 0 and idx_c < len(r) and r[idx_c].strip() == category)
            if m_ok and c_ok:
                try:
                    return int(r[idx_t]) if (idx_t >= 0 and idx_t < len(r)) else 0
                except Exception:
                    return 0
        return 0

    except Exception:
        key = (month, category)
        return int(st.session_state.get("_local_targets", {}).get(key, 0))


def set_target(month: str, category: str, target: int) -> None:
    """
    設定/覆寫月目標（有則更新、無則新增）
    """
    if not _backend_available:
        local = st.session_state.get("_local_targets", {})
        local[(month, category)] = int(target)
        st.session_state["_local_targets"] = local
        return

    cl, bk = _client_and_book()
    ws = _ensure_worksheet(bk, TARGETS_SHEET, TARGETS_HEADER)
    if ws is None:
        local = st.session_state.get("_local_targets", {})
        local[(month, category)] = int(target)
        st.session_state["_local_targets"] = local
        return

    try:
        values = ws.get_all_values()
        header = values[0] if values else TARGETS_HEADER
        idx_m = header.index("month") if "month" in header else -1
        idx_c = header.index("category") if "category" in header else -1
        idx_t = header.index("target") if "target" in header else -1

        # 尋找既有列
        row_to_update = -1
        for i in range(1, len(values)):
            r = values[i]
            m_ok = (idx_m >= 0 and idx_m < len(r) and r[idx_m].strip() == month)
            c_ok = (idx_c >= 0 and idx_c < len(r) and r[idx_c].strip() == category)
            if m_ok and c_ok:
                row_to_update = i + 1
                break

        if row_to_update > 0:
            # 直接更新 target 欄
            ws.update_cell(row_to_update, idx_t + 1, int(target))
        else:
            # 新增一列
            row = ["", "", ""]
            if idx_m >= 0: row[idx_m] = month
            if idx_c >= 0: row[idx_c] = category
            if idx_t >= 0: row[idx_t] = int(target)
            end_col = chr(64 + min(len(TARGETS_HEADER), 26))
            ws.append_row(row[:len(TARGETS_HEADER)], value_input_option="RAW", table_range=f"A1:{end_col}1")

    except Exception:
        # 失敗則寫入本機
        local = st.session_state.get("_local_targets", {})
        local[(month, category)] = int(target)
        st.session_state["_local_targets"] = local


