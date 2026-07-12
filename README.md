# API Test Generator

從 endpoint 清單自動產生 pytest API 測試腳本的產生器。

解決的問題：API 測試案例大量重複——同樣的 session 管理、同樣的登入流程、
同樣的斷言結構，差別只在打哪支 API。這類機械性工作交給機器，
人力留給真正需要判斷的部分：邊界條件、業務邏輯、測試資料設計。

工作流設計為三段：**自動生成 → 人工精修 → 框架執行**。

---

## 兩個 repo 的分工

這個產生器**不執行測試**，它只負責產出腳本。

```
api-test-generator  ──產出腳本──>  api-tests（測試框架 repo）
    產生器                              執行、維護、CI
```

兩者刻意分開：

- **產生器可以隨時抽換**——換 LLM、換探索來源、換模板，測試框架不受影響
- **產出的腳本是人工精修的起點，不是終點**——進了框架 repo 之後由人接手維護
- 產生器的輸出目錄是**交接點**，不是它自己的一部分

以環境變數把輸出直接指向框架 repo：

```bash
export TEST_OUTPUT_DIR=../api-tests/tests/generated
python generator/main.py
```

未設定時，輸出到本地的 `output/`（已列入 `.gitignore`）。

---

## 快速開始

以下指令在**專案根目錄**執行。

```bash
pip install -r requirements.txt

# 產生測試腳本 → 預設輸出到 output/
python generator/main.py

# 執行看看（實務上這一步在測試框架 repo 做）
pytest output/ -v
```

不想連外網也能驗證——起一個本地假網站，用環境變數把目標指過去：

```bash
python mock_server.py &
HTTPBIN_BASE_URL=http://127.0.0.1:8888 pytest output/ -v
```

產出長什麼樣子，可以直接看 `examples/sample_output.py`（不用跑generator）。

---

## 架構

```
generator/
    config.py          目標站台設定（帳密走環境變數，不進 git）
    discovery.py       Endpoint 探索：JSON 清單 / OpenAPI schema
    test_generator.py  核心：把 endpoint 清單組成 pytest 腳本
    main.py            CLI 入口，多目標並行

examples/              endpoint 清單範例 + 產出範例
output/                產出的交接目錄（gitignored）
mock_server.py         本地假網站，供離線驗證
```

資料流：

```
endpoint 清單 ──> discovery ──> 統一格式 ──> test_generator ──> pytest 腳本
                （來源可換）                 （template 組裝）      （交給框架）
```

`discovery` 這層的存在是為了讓「endpoint 從哪來」和「腳本怎麼產」。
換來源（JSON 清單 / OpenAPI / 瀏覽器流量側錄）只需要動 discovery，
產生器完全不用改。

---

## 設計決策

**template 用純字串 + `.replace()`，不用 f-string**

產出的內容本身就充滿 `{}`——dict 字面值、f-string、正規表示式。
用 f-string 當 template 的話，每個 `{` 都得逃逸成 `{{`；漏掉一個，
錯誤會出現在「產出的檔案」而不是產生器本身，除錯成本極高。
改用 `__TOKEN__` 佔位加 `.replace()`，這整類問題直接消失。

**登入流程在產生時注入，不在產出的腳本裡做 runtime 分支**

產出的腳本應該是一份人看得懂的普通測試檔，而不是塞滿
`if auth_type == ...` 的四不像。分支留在產生器這一層，
產出的檔案只有它自己需要的那條路徑。
目前支援三種認證：`basic` / `token` / `form`。

**兩層斷言：HTTP 200 不等於成功**

很多 API 會用 HTTP 200 包一個 `{"status": "401"}` 回來。
只驗 HTTP 狀態碼會把這類失敗全部誤判為通過。
產出的腳本一律先驗 HTTP，回應是 JSON 且含 `status` 欄位時再驗業務層。

**登入前 / 登入後的 API 分成不同 test class**

兩者用不同 session，也各自代表不同的失敗意義，
分開之後紅燈一眼看得出是「公開 API 掛了」還是「登入後才掛」。
認證流程本身也獨立成一個 test class，且排在 post-login 測試之前——
憑證失效時只會看到一個明確的認證失敗，而不是一整排原因不明的紅燈。

**帳密一律走環境變數**

產生時寫入的值只是 fallback，執行時優先讀
`{TARGET}_LOGIN` / `{TARGET}_PASSWORD` / `{TARGET}_BASE_URL`。
產出的腳本可以直接進 CI 不必改檔，也不會有人不小心把測試帳密 commit 上去。

---

## 加一個新目標網站

在 `config.py` 的 `TARGETS` 加一筆：

```python
"myapi": {
    "base_url": os.environ.get("MYAPI_BASE_URL", "https://api.example.com"),
    "login_name": os.environ.get("MYAPI_LOGIN", ""),
    "password": os.environ.get("MYAPI_PASSWORD", ""),
    "auth_type": "token",
    "spec": _path("examples", "myapi_endpoints.json"),
},
```

endpoint 清單格式：

```json
[
  { "name": "get_profile", "method": "GET", "path": "/user/profile", "auth": true },
  { "name": "health_check", "method": "GET", "path": "/health", "auth": false }
]
```

`auth` 決定這支 API 進登入前還是登入後的測試類別。

---

## 範圍說明

這是公開的示範版本，測試網站使用 [httpbin.org](https://httpbin.org)。

Endpoint 探索目前提供 JSON 清單與 OpenAPI 兩種來源。
另一條可行的路徑是瀏覽器流量側錄——用 Playwright 攔截 network request，
把使用者操作時實際打出去的 API 錄下來，能抓到「文件沒寫但實際存在」的端點。
代價是要處理登入流程、動態渲染與雜訊過濾，不在本示範範圍內。

## 授權

MIT
