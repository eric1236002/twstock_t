# twstock 稿本爬蟲 + K 線回測

抓取台股上市/上櫃的公司債、增資稿本/生效公告，存進 SQLite，並在網頁上瀏覽事件、看 K 線、疊事件標記、做 T+N 報酬回測與籌碼面板（外資/投信/自營/融資/融券）。後端 FastAPI，前端 React 打包成單一 `web/static/bundle.html` 由後端直接提供。

## 環境設定

`.env`（不進 git）需要：

```
FINMIND_TOKENS=token1,token2,token3   # FinMind，免費版每把 600 次/小時
PROXY_USERNAME=...                     # 爬 TWSE 用的住宅代理
PROXY_PASSWORD=...
PROXY_HOST=...
PROXY_PORT=...
```

Python 套件（需裝在執行 uvicorn 的那個環境）：

```
fastapi uvicorn httpx requests beautifulsoup4 tenacity python-dotenv urllib3
```

> 本機是用 miniconda 的 Python 跑（已裝好上述套件）：`/Users/eric/miniconda3/bin/python3`。

## 開（啟動）

```bash
/Users/eric/miniconda3/bin/python3 -m uvicorn web.app:app --host 127.0.0.1 --port 8765
```

啟動後開瀏覽器到 **http://127.0.0.1:8765** 。

背景執行（關掉終端機也不會停）：

```bash
/Users/eric/miniconda3/bin/python3 -m uvicorn web.app:app --host 127.0.0.1 --port 8765 > /tmp/uvicorn.log 2>&1 &
```

## 關（停止）

```bash
pkill -f "web.app:app"
```

確認已停：

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/   # 連不上代表已關
```

## 重建前端

改了 `frontend/src` 後要重新打包，bundle 才會更新：

```bash
cd frontend && pnpm build          # 產生 dist/
# 把 dist 的 JS/CSS 內聯成單檔
python3 - <<'PY'
import re, pathlib
dist = pathlib.Path("dist"); html = (dist/"index.html").read_text(encoding="utf-8")
m = re.search(r'<script[^>]*src="(/assets/[^"]+\.js)"[^>]*>\s*</script>', html)
html = html[:m.start()] + '<script type="module">' + (dist/m.group(1).lstrip("/")).read_text(encoding="utf-8") + '</script>' + html[m.end():]
m = re.search(r'<link[^>]*href="(/assets/[^"]+\.css)"[^>]*>', html)
html = html[:m.start()] + '<style>' + (dist/m.group(1).lstrip("/")).read_text(encoding="utf-8") + '</style>' + html[m.end():]
pathlib.Path("../web/static/bundle.html").write_text(html, encoding="utf-8")
print("bundle updated")
PY
```

> 注意：專案在 Google Drive 同步資料夾上，檔案 I/O 較慢；build 前先確認沒有殘留的 build 行程在搶 I/O：`pkill -f "vite.js"`。

前端開發模式（熱更新，API 代理到 8765）：

```bash
cd frontend && pnpm dev            # http://127.0.0.1:5173
```

## 常用操作

- **抓資料**：網頁右上「一鍵抓取」（預設抓當月），或 `POST /api/scrape?year=115`（整年回填）/`?year=115&month=4`（單月）。
- **更新名單**：`POST /api/update-codes`（從 TWSE ISIN 重抓 `codes/listed.csv` + `codes/otc.csv`）。
- **查配額**：`GET /api/quota`。

更多架構細節見 [CLAUDE.md](CLAUDE.md)。
