"""
test_generator.py — 把 endpoint 清單產生成 pytest 測試腳本

設計決策（踩過坑之後的結論）：

1. **template 用純字串 + .replace()，不用 f-string / .format()**
   產出的內容本身含大量 {} （dict、f-string、正規表示式），
   用 f-string 當 template 必須把每個 { 逃逸成 {{，
   一旦漏掉一個，錯誤會出現在「產出的檔案」而不是產生器本身，
   極難除錯。改用 __TOKEN__ 佔位 + .replace()，這類問題直接消失。

2. **登入流程依 auth_type 注入，不在產出的腳本裡做 runtime 分支**
   產出的腳本應該是「一份給人看得懂的普通測試檔」，
   而不是塞滿 if is_agent 分支的四不像。分支留在產生器這一層。

3. **帳密優先讀環境變數**
   產出的腳本可以直接進 CI，不必手動改檔。產生時寫入的值只是 fallback。
"""

from __future__ import annotations

import os
import re
from datetime import datetime


def _safe_name(name: str) -> str:
    """把 API 名稱轉成合法識別字，供 pytest parametrize 當測試 id"""
    cleaned = re.sub(r"[^0-9a-zA-Z_]", "_", name)
    if cleaned and cleaned[0].isdigit():
        cleaned = "_" + cleaned
    return cleaned or "unnamed_api"


def _format_api(api: dict) -> str:
    """把單一 endpoint 轉成產出腳本中的 dict 字面值"""
    return (
        "    {\n"
        f"        \"name\": {_safe_name(api['name'])!r},\n"
        f"        \"method\": {api['method']!r},\n"
        f"        \"path\": {api['path']!r},\n"
        f"        \"data\": {api.get('data', {})!r},\n"
        "    },"
    )


# ===================================================================
# 登入流程：依 auth_type 注入不同版本
# 以下都是「要寫進產出檔案的原始碼」，用 .replace 塞進 TEMPLATE
# ===================================================================

_BASIC_AUTH_FLOW = '''def get_auth_session():
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
    return _auth_session'''


_TOKEN_AUTH_FLOW = '''def get_auth_session():
    """Token Auth：先換 token，再掛進 Authorization header。"""
    global _auth_session
    if _auth_session is None:
        s = make_base_session()
        resp = s.post(
            f"{BASE_URL}/auth/login",
            json={"username": LOGIN_NAME, "password": PASSWORD},
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200, f"取得 token 失敗：HTTP {resp.status_code}"
        token = resp.json().get("token")
        assert token, "回應中沒有 token 欄位"
        s.headers["Authorization"] = f"Bearer {token}"
        print(f"  🔑 Token: {token[:8]}...")
        _auth_session = s
    return _auth_session'''


_FORM_AUTH_FLOW = '''def get_auth_session():
    """Form Auth：表單登入，session cookie 由 requests.Session 自動保存。

    許多站台會在登入前先發一個一次性的 session key / CSRF token，
    密碼需與其合併雜湊後才送出。這裡示範該模式的骨架。
    """
    global _auth_session
    if _auth_session is None:
        s = make_base_session()
        session_key = get_session_key(s)
        payload = {
            "loginName": LOGIN_NAME,
            "password": encrypt_password(PASSWORD, session_key),
            "rememberMe": "false",
        }
        resp = s.post(f"{BASE_URL}/auth/login", data=payload, timeout=TIMEOUT)
        assert resp.status_code == 200, f"登入 HTTP 失敗：{resp.status_code}"
        body = resp.json()
        assert str(body.get("status")) not in ERROR_STATUS, \\
            f"登入失敗：{body.get('message')}"
        print("  ✅ 登入成功")
        _auth_session = s
    return _auth_session


def get_session_key(session):
    """從登入頁抓一次性 session key"""
    resp = session.get(f"{BASE_URL}/", timeout=TIMEOUT)
    m = re.search(r'name=["\\']sessionKey["\\'][^>]*value=["\\']([^"\\']+)["\\']', resp.text)
    if not m:
        raise ValueError("找不到 sessionKey，請確認登入頁是否正常載入")
    return m.group(1)


def encrypt_password(password, session_key):
    """密碼雜湊：sha1(sha1(password) + session_key)

    實際公式依各平台而異，需比對前端 JS 的實作。
    """
    return sha1(sha1(password) + session_key)


def sha1(text):
    return hashlib.sha1(text.encode()).hexdigest()'''


_AUTH_FLOWS = {
    "basic": _BASIC_AUTH_FLOW,
    "token": _TOKEN_AUTH_FLOW,
    "form": _FORM_AUTH_FLOW,
}


# ===================================================================
# 主 template：純字串，無 f-string，靠 __TOKEN__ 做 .replace
# ===================================================================

_TEMPLATE = '''"""
__FILENAME__ — 自動產生的 API 測試腳本

⚠️ 請勿手動編輯：重跑產生器即可更新。
   需要客製的斷言請另外開一支測試檔，不要改這裡——
   這份檔案的定位是「機器產出的回歸基線」，人寫的測試放在別處，
   兩者混在一起會導致重新產生時覆蓋掉手寫的內容。

目標站台 : __TARGET__
Base URL : __BASE_URL__
認證方式 : __AUTH_TYPE__
產生時間 : __NOW__

執行方式：
    pytest __FILENAME__ -v
    pytest __FILENAME__ -v --html=report.html --self-contained-html
"""

import hashlib
import json
import os
import re

import pytest
import requests

# ===================== 設定區 =====================
# 帳密優先讀環境變數（CI 用），讀不到才用產生時寫入的預設值。
#   export __ENV_LOGIN__=xxx
#   export __ENV_PASSWORD__=xxx
BASE_URL = os.environ.get("__ENV_BASE_URL__", "__BASE_URL__")
LOGIN_NAME = os.environ.get("__ENV_LOGIN__", "__LOGIN_NAME__")
PASSWORD = os.environ.get("__ENV_PASSWORD__", "__PASSWORD__")
TIMEOUT = __TIMEOUT__

# 業務失敗的 status 碼：HTTP 200 不等於業務成功。
# 很多 API 會用 200 包一個 {"status": "401"} 回來，只驗 HTTP 會全部誤判為通過。
ERROR_STATUS = {__ERROR_STATUS__}


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


__AUTH_FLOW__


def log(name, status, resp=None):
    symbol = "✅" if status == 200 else "❌"
    print(f"\\n  {symbol} [{status}] {name}")
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


# ===================== 登入前 API（自動產生，共 __PRE_COUNT__ 支）=====================
PRE_LOGIN_APIS = [
__PRE_BLOCK__
]

# ===================== 登入後 API（自動產生，共 __POST_COUNT__ 支）=====================
POST_LOGIN_APIS = [
__POST_BLOCK__
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


@pytest.mark.skipif(
    not POST_LOGIN_APIS,
    reason="此目標沒有登入後 API，認證流程無需驗證",
)
class TestAuth:
    """認證流程本身。放在 post-login 測試之前，讓失敗原因一目了然。"""

    def test_auth_success(self):
        get_auth_session()
        print("\\n  ✅ 認證流程驗證通過")


@pytest.mark.skipif(
    not POST_LOGIN_APIS,
    reason="此目標沒有登入後 API",
)
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
'''


def generate_pytest_script(
    target: str,
    base_url: str,
    login_name: str,
    password: str,
    pre_login_apis: list,
    post_login_apis: list,
    auth_type: str = "basic",
    error_status: set | None = None,
    timeout: int = 15,
    output_dir: str = "generated_tests",
) -> str:
    """產生一支 pytest 腳本，回傳檔案路徑"""

    if auth_type not in _AUTH_FLOWS:
        raise ValueError(
            f"未支援的 auth_type：{auth_type}（可用：{', '.join(_AUTH_FLOWS)}）"
        )

    error_status = error_status or {"401", "403", "500"}
    filename = f"test_{_safe_name(target)}_api.py"

    pre_block = "\n".join(_format_api(a) for a in pre_login_apis) \
        or "    # （沒有登入前 API）"
    post_block = "\n".join(_format_api(a) for a in post_login_apis) \
        or "    # （沒有登入後 API）"

    # 環境變數名稱：{TARGET}_BASE_URL / _LOGIN / _PASSWORD
    env_prefix = re.sub(r"[^0-9A-Za-z]+", "_", target).upper()

    replacements = {
        "__FILENAME__": filename,
        "__TARGET__": target,
        "__BASE_URL__": base_url,
        "__AUTH_TYPE__": auth_type,
        "__NOW__": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "__LOGIN_NAME__": login_name,
        "__PASSWORD__": password,
        "__TIMEOUT__": str(timeout),
        "__ERROR_STATUS__": ", ".join(repr(s) for s in sorted(error_status)),
        "__ENV_BASE_URL__": f"{env_prefix}_BASE_URL",
        "__ENV_LOGIN__": f"{env_prefix}_LOGIN",
        "__ENV_PASSWORD__": f"{env_prefix}_PASSWORD",
        "__AUTH_FLOW__": _AUTH_FLOWS[auth_type],
        "__PRE_COUNT__": str(len(pre_login_apis)),
        "__POST_COUNT__": str(len(post_login_apis)),
        "__PRE_BLOCK__": pre_block,
        "__POST_BLOCK__": post_block,
    }

    script = _TEMPLATE
    for token, value in replacements.items():
        script = script.replace(token, value)

    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(script)

    return filepath
