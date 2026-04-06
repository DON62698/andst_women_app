import os
from datetime import datetime
from typing import List, Dict, Any, Optional

# Streamlit is optional here (only used to read st.secrets if available)
try:
    import streamlit as st  # type: ignore
except Exception:  # pragma: no cover
    st = None  # type: ignore

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ====== Configuration ======
# Prefer reading from Streamlit secrets
SHEET_URL_DEFAULT = "https://docs.google.com/spreadsheets/d/1dRMaH6G1bLzv-Bt1q5wEnZPC4ZylMCE7Dzcj1KAwURE/edit?usp=sharing"

def _get_creds_dict() -> dict:
    """
    Load Google Service Account JSON credentials.
    Priority:
      1) st.secrets["gcp_service_account"] (Streamlit Cloud recommended)
      2) JSON string in env GOOGLE_SERVICE_ACCOUNT_JSON
      3) JSON file path in env GOOGLE_APPLICATION_CREDENTIALS
    """
    # 1) Streamlit secrets
    if st is not None:
        try:
            return dict(st.secrets["gcp_service_account"])  # type: ignore
        except Exception:
            pass

    # 2) Env JSON string
    js = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if js:
        import json
        return json.loads(js)

    # 3) Env file path
    path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if path and os.path.exists(path):
        import json
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    raise RuntimeError("Google Service Account credentials not found. Set st.secrets['gcp_service_account'] or env GOOGLE_SERVICE_ACCOUNT_JSON / GOOGLE_APPLICATION_CREDENTIALS.")

def _get_sheet_url() -> str:
    if st is not None:
        try:
            return st.secrets.get("sheet_url", SHEET_URL_DEFAULT)  # type: ignore
        except Exception:
            pass
    return os.getenv("SHEET_URL", SHEET_URL_DEFAULT)

def _get_client() -> gspread.Client:
    creds_dict = _get_creds_dict()
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def _open_workbook():
    client = _get_client()
    return client.open_by_url(_get_sheet_url())

def _ensure_worksheet(sh, title: str, header: list) -> gspread.Worksheet:
    try:
        ws = sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows="1000", cols=str(max(10, len(header))))
        ws.append_row(header)
    # If first row is empty or not header, ensure header exists
    first_row = ws.row_values(1)
    if not first_row:
        ws.update("A1", [header])
    return ws

# ====== Public API (drop-in replacement for db.py) ======

def init_db():
    """Ensure worksheets exist with headers. Mirrors sqlite init."""
    sh = _open_workbook()
    _ensure_worksheet(sh, "records", ["date", "week", "name", "type", "count"])
    _ensure_worksheet(sh, "targets", ["month", "type", "target"])

def init_target_table():
    """Kept for compatibility; targets sheet is created in init_db."""
    init_db()

def _week_str(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{dt.isocalendar().week}w"

def load_all_records() -> List[Dict[str, Any]]:
    sh = _open_workbook()
    ws = _ensure_worksheet(sh, "records", ["date", "week", "name", "type", "count"])
    rows = ws.get_all_records()
    out: List[Dict[str, Any]] = []
    for r in rows:
        if not r.get("date"):
            continue
        item = {
            "date": r.get("date"),
            "week": r.get("week") or _week_str(r.get("date")),
            "name": r.get("name", ""),
            "type": r.get("type", ""),
            "count": int(r.get("count") or 0),
        }
        out.append(item)
    return out

def _find_row(ws: gspread.Worksheet, date_str: str, name: str, category: str) -> Optional[int]:
    """Return row index (1-based) for first match below header, else None."""
    # naive scan
    all_values = ws.get_all_values()
    if not all_values:
        return None
    for idx, row in enumerate(all_values[1:], start=2):
        d, w, n, t, c = (row + ["", "", "", "", ""])[:5]
        if d == date_str and n == name and t == category:
            return idx
    return None

def insert_or_update_record(date_str: str, name: str, category: str, count: int):
    sh = _open_workbook()
    ws = _ensure_worksheet(sh, "records", ["date", "week", "name", "type", "count"])
    row_idx = _find_row(ws, date_str, name, category)
    week = _week_str(date_str)
    if row_idx:
        ws.update(f"A{row_idx}:E{row_idx}", [[date_str, week, name, category, int(count)]])
    else:
        ws.append_row([date_str, week, name, category, int(count)])

def delete_record(date_str: str, name: str, category: str) -> bool:
    sh = _open_workbook()
    ws = _ensure_worksheet(sh, "records", ["date", "week", "name", "type", "count"])
    row_idx = _find_row(ws, date_str, name, category)
    if row_idx:
        ws.delete_rows(row_idx)
        return True
    return False

def set_target(month: str, category: str, value: int):
    """
    Upsert into targets sheet.
    month: "2025-08" (YYYY-MM)
    category: "app" or "survey"
    """
    sh = _open_workbook()
    ws = _ensure_worksheet(sh, "targets", ["month", "type", "target"])
    # scan for existing
    all_values = ws.get_all_values()
    found = None
    for idx, row in enumerate(all_values[1:], start=2):
        m, t, v = (row + ["", "", ""])[:3]
        if m == month and t == category:
            found = idx
            break
    if found:
        ws.update(f"A{found}:C{found}", [[month, category, int(value)]])
    else:
        ws.append_row([month, category, int(value)])

def get_target(month: str, category: str) -> int:
    sh = _open_workbook()
    ws = _ensure_worksheet(sh, "targets", ["month", "type", "target"])
    rows = ws.get_all_records()
    for r in rows:
        if r.get("month") == month and r.get("type") == category:
            try:
                return int(r.get("target") or 0)
            except Exception:
                return 0
    return 0


# ==== Cached Google Sheets client & workbook (added by assistant) ====

def _get_sheet_url():
    """Resolve sheet URL from Streamlit secrets, env var, or fallback default."""
    if st is not None:
        try:
            return st.secrets["sheets"]["url"]
        except Exception:
            pass
    return os.environ.get("SHEET_URL", SHEET_URL_DEFAULT)

# Guard decorator for non-Streamlit contexts
if st is not None:
    @st.cache_resource
    def _client_and_book():
        import json
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        if st is not None:
            creds_dict = dict(st.secrets["gcp_service_account"])  # type: ignore
        else:
            creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
            if not creds_json:
                raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON env var for service account credentials.")
            creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sh = client.open_by_url(_get_sheet_url())
        return client, sh
else:
    def _client_and_book():
        import json
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if not creds_json:
            raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON env var for service account credentials.")
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sh = client.open_by_url(_get_sheet_url())
        return client, sh

def _open_workbook():
    """Return cached Spreadsheet handle (overrides any previous definition)."""
    return _client_and_book()[1]
# ==== End cached block ====


# ==== Safe override for _ensure_worksheet (added by assistant) ====
from gspread.exceptions import WorksheetNotFound, APIError as _GSpreadAPIError

def _ensure_worksheet(sh, name: str, header):
    """Return a worksheet with the given header ensured.
    - Creates the sheet if missing.
    - If reading header fails due to APIError, proceeds to set header.
    """
    try:
        try:
            ws = sh.worksheet(name)
        except WorksheetNotFound:
            ws = sh.add_worksheet(title=name, rows=1000, cols=max(26, len(header)))

        # Try to read the first row; if it fails, treat as empty
        try:
            first_row = ws.row_values(1)
        except _GSpreadAPIError:
            first_row = []

        # Normalize and check header
        normalized = [str(c).strip() for c in (first_row or [])]
        if normalized != header:
            # Compute end column (A..Z); header size in this app <= 5, so this is fine
            end_col = chr(64 + len(header))  # 1->A, 2->B, ...
            ws.update(f"A1:{end_col}1", [header])
        return ws
    except Exception as e:
        raise RuntimeError(f"_ensure_worksheet('{name}') failed: {e}")
# ==== End safe override ====
# ==== Cached Google Sheets client & workbook (assistant patch) ====
def _get_sheet_url():
    """Resolve sheet URL from Streamlit secrets, env var, or fallback default."""
    if st is not None:
        try:
            return st.secrets["sheets"]["url"]
        except Exception:
            pass
    return os.environ.get("SHEET_URL", SHEET_URL_DEFAULT)

if st is not None:
    @st.cache_resource
    def _client_and_book():
        import json
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sh = client.open_by_url(_get_sheet_url())
        return client, sh
else:
    def _client_and_book():
        import json
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if not creds_json:
            raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON env var for service account credentials.")
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sh = client.open_by_url(_get_sheet_url())
        return client, sh

def _open_workbook():
    """Return cached Spreadsheet handle (overrides any previous definition)."""
    return _client_and_book()[1]
# ==== End cached block ====


# ==== Safe override for _ensure_worksheet (assistant patch) ====
from gspread.exceptions import WorksheetNotFound, APIError as _GSpreadAPIError

def _ensure_worksheet(sh, name: str, header):
    """Return a worksheet with the given header ensured.
    - Creates the sheet if missing.
    - If reading header fails due to APIError, proceeds to set header.
    """
    try:
        try:
            ws = sh.worksheet(name)
        except WorksheetNotFound:
            ws = sh.add_worksheet(title=name, rows=1000, cols=max(26, len(header)))

        # Try to read the first row; if it fails, treat as empty
        try:
            first_row = ws.row_values(1)
        except _GSpreadAPIError:
            first_row = []

        normalized = [str(c).strip() for c in (first_row or [])]
        if normalized != header:
            end_col = chr(64 + len(header))  # 1->A, 2->B, ...
            ws.update(f"A1:{end_col}1", [header])
        return ws
    except Exception as e:
        raise RuntimeError(f"_ensure_worksheet('{name}') failed: {e}")
# ==== End safe override ====


# ==== Robust get_target (assistant patch) ====
def get_target(month: str, category: str) -> int:
    """
    Robustly read a single target value.
    - Prefer small-range reads over get_all_records() to reduce API load.
    - Fallbacks gracefully and returns 0 on non-critical errors.
    """
    sh = _open_workbook()
    ws = _ensure_worksheet(sh, "targets", ["month", "type", "target"])
    # Fast path
    try:
        rows = ws.get_all_records()
        for r in rows:
            if r.get("month") == month and r.get("type") == category:
                try:
                    return int(r.get("target") or 0)
                except Exception:
                    return 0
    except Exception:
        pass

    # Fallback: bounded range
    try:
        data = ws.get("A1:C1000") or []
    except Exception:
        return 0

    if not data:
        return 0

    header = [str(x).strip().lower() for x in (data[0] if data else [])]
    def _idx(name, default):
        return header.index(name) if name in header else default
    im, it, iv = _idx("month", 0), _idx("type", 1), _idx("target", 2)

    for row in data[1:]:
        if len(row) <= max(im, it, iv):
            continue
        if str(row[im]) == month and str(row[it]) == category:
            try:
                return int(row[iv])
            except Exception:
                return 0
    return 0
# ==== End robust get_target ====


