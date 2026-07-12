"""
discovery.py — Endpoint 探索

負責產出「這個站台有哪些 API」的清單，交給 test_generator 生成腳本。

本 demo 提供兩種來源：
  1. from_spec()      — 讀 JSON endpoint 清單（最單純，適合已有 API 文件的情境）
  2. from_openapi()   — 讀 OpenAPI / Swagger schema 自動展開

實務上還可以再接第三種來源：瀏覽器流量側錄（Playwright 攔截 network request，
把使用者操作過程中真正打出去的 API 錄下來）。那條路徑能抓到「文件沒寫、但實際存在」
的端點，代價是需要處理登入流程、動態渲染與雜訊過濾——不在本 demo 範圍內。

設計重點：不論來源是什麼，對下游都輸出同一種格式，
       所以要換來源只要換這一層，test_generator 完全不用改。
"""

from __future__ import annotations

import json
import os
from urllib.parse import urlparse

from config import IGNORE_EXTENSIONS, IGNORE_DOMAINS, IGNORE_PATHS


# ===================================================================
# 統一輸出格式（contract）
# ===================================================================
# 每個 endpoint 一律長這樣，下游只認這個結構：
#   {
#       "name":    "get_user_profile",   # 測試 id，需為合法識別字
#       "method":  "GET",                # GET / POST
#       "path":    "/user/profile",      # 相對路徑
#       "data":    {"id": "1"},          # query params 或 form body
#       "auth":    True,                 # True = 需登入後才能呼叫
#   }
# ===================================================================


def _should_ignore(path: str) -> bool:
    """過濾靜態資源、第三方網域、危險路徑"""
    lowered = path.lower()

    if any(lowered.endswith(ext) for ext in IGNORE_EXTENSIONS):
        return True

    host = urlparse(path).netloc.lower()
    if host and any(bad in host for bad in IGNORE_DOMAINS):
        return True

    if any(bad in lowered for bad in IGNORE_PATHS):
        return True

    return False


def _normalize(raw: dict) -> dict | None:
    """把單一 endpoint 正規化成統一格式；不合格回傳 None"""
    path = raw.get("path", "").strip()
    if not path or _should_ignore(path):
        return None

    method = raw.get("method", "GET").upper()
    if method not in ("GET", "POST"):
        return None  # demo 只處理 GET / POST

    return {
        "name": raw.get("name") or path.strip("/").replace("/", "_") or "root",
        "method": method,
        "path": path,
        "data": raw.get("data") or {},
        "auth": bool(raw.get("auth", False)),
    }


def from_spec(spec_path: str) -> tuple[list[dict], list[dict]]:
    """
    從 JSON endpoint 清單讀取。

    回傳 (pre_login_apis, post_login_apis)，依 auth 旗標分流——
    這個分流是整套設計的關鍵：登入前 / 登入後的 API 用不同 session 呼叫，
    產出的測試也分成不同 class，失敗時一眼看得出是「公開 API 掛了」
    還是「登入後才掛」。
    """
    if not os.path.exists(spec_path):
        raise FileNotFoundError(f"找不到 endpoint 清單：{spec_path}")

    with open(spec_path, "r", encoding="utf-8") as f:
        raw_list = json.load(f)

    pre, post = [], []
    skipped = 0

    for raw in raw_list:
        api = _normalize(raw)
        if api is None:
            skipped += 1
            continue
        (post if api["auth"] else pre).append(api)

    print(f"  🔍 探索完成：登入前 {len(pre)} 支 / 登入後 {len(post)} 支"
          f"{f'（過濾掉 {skipped} 筆）' if skipped else ''}")

    return pre, post


def from_openapi(schema_path: str) -> tuple[list[dict], list[dict]]:
    """
    從 OpenAPI / Swagger schema 展開 endpoint。

    判定「需不需要登入」的規則：該 operation 有 security 設定，或
    schema 有全域 security 且該 operation 沒有明確覆寫成空。
    """
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    global_security = bool(schema.get("security"))
    pre, post = [], []

    for path, methods in schema.get("paths", {}).items():
        for method, operation in methods.items():
            if method.upper() not in ("GET", "POST"):
                continue

            security = operation.get("security", None)
            needs_auth = bool(security) if security is not None else global_security

            api = _normalize({
                "name": operation.get("operationId"),
                "method": method,
                "path": path,
                "auth": needs_auth,
            })
            if api is None:
                continue
            (post if api["auth"] else pre).append(api)

    print(f"  🔍 OpenAPI 展開：登入前 {len(pre)} 支 / 登入後 {len(post)} 支")
    return pre, post
