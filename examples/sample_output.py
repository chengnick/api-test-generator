"""
⚠️ 這是產生器輸出的「範例」，放在 examples/ 供閱讀。實際執行時腳本會產到 output/。

test_httpbin_api.py — 自動產生的 API 測試腳本

⚠️ 請勿手動編輯：重跑產生器即可更新。
   需要客製的斷言請另外開一支測試檔，不要改這裡——
   這份檔案的定位是「機器產出的回歸基線」，人寫的測試放在別處，
   兩者混在一起會導致重新產生時覆蓋掉手寫的內容。

目標站台 : httpbin
Base URL : https://httpbin.org
認證方式 : basic
產生時間 : 2026-07-12 07:55:56

執行方式：
    pytest test_httpbin_api.py -v
    pytest test_httpbin_api.py -v --html=report.html --self-contained-html
"""

import hashlib
import json
import os
import re

import pytest
import requests

# ===================== 設定區 =====================
# 帳密優先讀環境變數（CI 用），讀不到才用產生時寫入的預設值。
#   export HTTPBIN_LOGIN=xxx
#   export HTTPBIN_PASSWORD=xxx
BASE_URL = os.environ.get("HTTPBIN_BASE_URL", "https://httpbin.org")
LOGIN_NAME = os.environ.get("HTTPBIN_LOGIN", "demo_user")
PASSWORD = os.environ.get("HTTPBIN_PASSWORD", "demo_pass")
TIMEOUT = 15

# 業務失敗的 status 碼：HTTP 200 不等於業務成功。
# 很多 API 會用 200 包一個 {"status": "401"} 回來，只驗 HTTP 會全部誤判為通過。
ERROR_STATUS = {'400', '401', '403', '404', '500', '999'}


def assert_api_ok(resp, name):
    """兩層斷言：先驗 HTTP，再驗業務 status（若回應為 JSON 且含 status 欄位）"""
    assert resp.status_code == 200, f"{name} HTTP {resp.status_code}"
    try:
        body = resp.json()
    except Exception:
        return  # 非 JSON 回應（頁面 / 檔案）→ 只驗 HTTP
    if isinstance(body, dict):
        status = str(body.get("status", ""))
        if status:
            msg = body.get("message") or body.get("msg") or ""
            assert status not in ERROR_STATUS, f"{name} 業務失敗 status={status} {msg}"


# ===================== Session（整支測試只認證一次）=====================
_plain_session = None
_auth_session = None


def make_base_session():
    s = requests.Session()
    s.headers.update({
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "api-test-generator-demo/1.0",
    })
    return s


def get_plain_session():
    """未認證的 session，供登入前 API 使用"""
    global _plain_session
    if _plain_session is None:
        _plain_session = make_base_session()
    return _plain_session


def get_auth_session():
    """Basic Auth：帳密直接掛在 session 上，後續請求自動帶。"""
    global _auth_session
    if _auth_session is None:
        s = make_base_session()
        s.auth = (LOGIN_NAME, PASSWORD)
        # 先打一支已知需要認證的端點，確認憑證有效再繼續。
        # 這一步是刻意的：與其讓後面每一支測試都因為登入失敗而紅，
        # 不如在這裡一次擋下來，錯誤訊息才指得出真正的原因。
        resp = s.get(f"{BASE_URL}/basic-auth/{LOGIN_NAME}/{PASSWORD}", timeout=TIMEOUT)
        assert resp.status_code == 200, f"認證失敗：HTTP {resp.status_code}"
        print("  ✅ 認證成功")
        _auth_session = s
    return _auth_session


def log(name, status, resp=None):
    symbol = "✅" if status == 200 else "❌"
    print(f"\n  {symbol} [{status}] {name}")
    if status != 200 and resp is not None:
        try:
            print(f"     ↳ {json.dumps(resp.json(), ensure_ascii=False)[:300]}")
        except Exception:
            print(f"     ↳ {resp.text[:300]}")


def call_api(session, api):
    url = BASE_URL + api["path"]
    if api["method"] == "GET":
        return session.get(url, params=api.get("data", {}), timeout=TIMEOUT)
    return session.post(url, data=api.get("data", {}), timeout=TIMEOUT)


# ===================== 登入前 API（自動產生，共 7 支）=====================
PRE_LOGIN_APIS = [
    {
        "name": 'get_request_echo',
        "method": 'GET',
        "path": '/get',
        "data": {'page': '1', 'size': '20'},
    },
    {
        "name": 'post_form_submit',
        "method": 'POST',
        "path": '/post',
        "data": {'name': 'demo', 'action': 'submit'},
    },
    {
        "name": 'get_status_ok',
        "method": 'GET',
        "path": '/status/200',
        "data": {},
    },
    {
        "name": 'get_response_headers',
        "method": 'GET',
        "path": '/response-headers',
        "data": {'Content-Type': 'application/json'},
    },
    {
        "name": 'get_user_agent',
        "method": 'GET',
        "path": '/user-agent',
        "data": {},
    },
    {
        "name": 'get_json_payload',
        "method": 'GET',
        "path": '/json',
        "data": {},
    },
    {
        "name": 'get_encoding_utf8',
        "method": 'GET',
        "path": '/encoding/utf8',
        "data": {},
    },
]

# ===================== 登入後 API（自動產生，共 4 支）=====================
POST_LOGIN_APIS = [
    {
        "name": 'get_bearer_protected',
        "method": 'GET',
        "path": '/headers',
        "data": {},
    },
    {
        "name": 'get_hidden_basic_auth',
        "method": 'GET',
        "path": '/cookies',
        "data": {},
    },
    {
        "name": 'get_authenticated_ip',
        "method": 'GET',
        "path": '/ip',
        "data": {},
    },
    {
        "name": 'post_authenticated_action',
        "method": 'POST',
        "path": '/anything',
        "data": {'op': 'update', 'id': '42'},
    },
]


# ===================== 測試類別 =====================
class TestPreLoginAPIs:
    """不需認證即可存取的 API"""

    @pytest.mark.parametrize(
        "api", PRE_LOGIN_APIS, ids=[a["name"] for a in PRE_LOGIN_APIS]
    )
    def test_pre_login_api(self, api):
        resp = call_api(get_plain_session(), api)
        log(api["name"], resp.status_code, resp)
        assert_api_ok(resp, api["name"])


class TestAuth:
    """認證流程本身。放在 post-login 測試之前，讓失敗原因一目了然。"""

    def test_auth_success(self):
        get_auth_session()
        print("\n  ✅ 認證流程驗證通過")


class TestPostLoginAPIs:
    """需認證才能存取的 API"""

    @pytest.mark.parametrize(
        "api", POST_LOGIN_APIS, ids=[a["name"] for a in POST_LOGIN_APIS]
    )
    def test_post_login_api(self, api):
        resp = call_api(get_auth_session(), api)
        log(api["name"], resp.status_code, resp)
        assert_api_ok(resp, api["name"])


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
