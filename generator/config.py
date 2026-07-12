"""
config.py — 目標站台設定

新增一個目標站台，只要在 TARGETS 加一筆，其他不用動。

⚠️ 設計原則：這份檔案不放任何真實憑證。
   帳密一律從環境變數讀取，讀不到才用 demo 預設值。
   實務上請搭配 .env（已列入 .gitignore）或 CI secrets。
"""

import os

# 專案根目錄。路徑一律以此為錨點，不依賴 cwd——
# 否則從 generator/ 跑和從專案根跑會得到不同結果，CI 上尤其容易踩到。
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _path(*parts: str) -> str:
    return os.path.join(ROOT, *parts)


# ===================== 目標站台設定 =====================
# demo 使用 httpbin.org —— 一個公開的 HTTP 測試靶站。
#   pre-login  : 不需要認證的端點
#   post-login : 需要 Basic Auth 的端點（模擬「登入後」才能存取的 API）
TARGETS = {
    "httpbin": {
        "base_url": os.environ.get("HTTPBIN_BASE_URL", "https://httpbin.org"),
        "login_name": os.environ.get("HTTPBIN_LOGIN", "demo_user"),
        "password": os.environ.get("HTTPBIN_PASSWORD", "demo_pass"),
        "auth_type": "basic",          # basic | token | form
        "spec": _path("examples", "httpbin_endpoints.json"),
    },
    # 新增站台照格式加一筆：
    # "myapi": {
    #     "base_url": os.environ.get("MYAPI_BASE_URL", "https://api.example.com"),
    #     "login_name": os.environ.get("MYAPI_LOGIN", ""),
    #     "password": os.environ.get("MYAPI_PASSWORD", ""),
    #     "auth_type": "token",
    #     "spec": "examples/myapi_endpoints.json",
    # },
}

# ===================== 產生器設定 =====================
# output_dir 是「交接點」，不是本專案的一部分。
#
# 產生器與測試框架是兩個獨立的 repo：
#   產生器負責產出腳本 → 交給測試框架 repo 執行與維護
#
# 預設輸出到本地的 output/（已列入 .gitignore），實務上以環境變數
# 指向測試框架 repo 的測試目錄，產出即落地到正確的位置：
#   export TEST_OUTPUT_DIR=../api-tests/tests/generated
GENERATOR = {
    "output_dir": os.environ.get("TEST_OUTPUT_DIR", _path("output")),
    "timeout": 15,              # 產出腳本內的 request timeout（秒）
    "include_pre_login": True,  # 是否產生登入前 API 的測試類別
    "include_post_login": True, # 是否產生登入後 API 的測試類別
}

# ===================== 並行設定 =====================
# 一個「產生單元」= 一個 target。多目標時的並行上限。
MAX_CONCURRENT = 3

# ===================== 過濾設定 =====================
# 從 endpoint 清單中排除的項目：靜態資源不是 API，不該進測試清單
IGNORE_EXTENSIONS = [
    ".js", ".css", ".png", ".jpg", ".jpeg", ".gif",
    ".webp", ".ico", ".svg", ".woff", ".woff2", ".ttf",
    ".mp4", ".mp3", ".html",
    # 註：.json 不排除 —— API 回應大多是 JSON，排除會誤殺真正的端點
]

IGNORE_DOMAINS = [
    "google", "facebook", "gtm", "analytics", "cloudflare",
    "doubleclick", "tiktok",
]

IGNORE_PATHS = [
    "/cdn-cgi/",
    "/logout",      # ⚠️ 絕不可觸發：一踩到 session 就失效，後續測試全數連鎖失敗
    "/signout",
]

# 業務失敗的 status 碼。回應 JSON 若含 status 欄位，會據此判定業務層失敗。
# 這是 demo 值，實務上依各平台的 API 契約調整。
ERROR_STATUS = {"400", "401", "403", "404", "500", "999"}
