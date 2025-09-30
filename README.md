# andst_women_app

- エントリーファイル: `staff_recommend_app_women.py`
- 追加タブ: 「週目標・達成率」「テスト記録」
- 既存の日本語UI/アンケート統計/グラフ/月目標はそのまま

## デプロイ（Streamlit Cloud）
1. このzipをアップロード（またはGitHubにpushして指定）
2. Main file に `andst_women_app/staff_recommend_app_women.py` を指定
3. Secrets に以下を設定（例）

[toml]
[gcp_service_account]
type = "service_account"
project_id = "YOUR_PROJECT_ID"
private_key_id = "YOUR_PRIVATE_KEY_ID"
private_key = """
-----BEGIN PRIVATE KEY-----
...（多行・改行を保持）...
-----END PRIVATE KEY-----
"""
client_email = "YOUR_SA_EMAIL"
client_id = "YOUR_CLIENT_ID"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"

[sheets]
url = "https://docs.google.com/spreadsheets/d/XXXXXXXXXXXX/edit"
[/toml]

- Service Account を対象のスプレッドシートに「編集者」で共有すること
- Google Sheets API / Google Drive API を有効化

## よくあるエラー
- DuplicateElementId → すでに修正済み（ウィジェットに一意キー付与）
- PERMISSION_DENIED → シート共有 or API 有効化を確認
- Not a valid private key → private_key の1行目と2行目の間に改行が必要
