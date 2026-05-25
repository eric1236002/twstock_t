# 系統架構：資料來源、更新觸發、保留與刪除

> 對象:`web/` FastAPI 應用 + 單一本機 SQLite `twstock.db`。前端為打包後的 `web/static/bundle.html`(由 `frontend/` build)。
> 本文描述「**什麼資料、從哪來、何時/被誰觸發更新、多久被刪、資料庫長怎樣**」。

---

## 1. 總覽

- **唯一資料庫**:`twstock.db`(本機 SQLite,`web/db.py` 的 `connect()` / `connect_local()` 都指向它;`PARSE_DECLTYPES` 開啟 → `DATE`/`DATETIME` 欄位讀回來是 `datetime` 物件)。
- **唯一雲端**:Turso(libSQL),**只備份 `events` 一張表**。
- **外部資料源**:FinMind REST(價格/籌碼/股名/新聞)、TPEx open API(可轉債)、TWSE doc 端點(稿本爬蟲)、MOPS(調整後轉換價,**尚未整合**)。
- **更新模式**有四種:**啟動時**、**看個股時惰性補抓**、**手動按鈕**、**每日首次呼叫**。

---

## 2. 資料庫 Schema(`web/db.py` `SCHEMA`)

```
events(id PK, code, market, doc_type, case_status, file_link,
       filed_at DATETIME, source_month, created_at, UNIQUE(code,file_link))
  idx: code, filed_at
stock_names(code PK, name)
cb(bond_code PK, stock_code, name, conv_price,
   conv_start, conv_end, issue_date, maturity_date,
   issue_amount, outstanding_amount, coupon_rate,
   put_date, put_price, listing_status, fetched_at)
  idx: stock_code
scrape_jobs(id PK, started_at, finished_at, status, log, rows_inserted)
kline(code, date, open, high, low, close, volume, PK(code,date))
kline_meta(code PK, last_accessed DATE)
institutional(code, date, foreign_net, trust_net, dealer_net, PK(code,date))
margin(code, date, margin_balance, short_balance, PK(code,date))
news(code, published_at, title, source, link, PK(code,published_at,link))
news_fetched(code, date, PK(code,date))
```
建表用 `CREATE TABLE IF NOT EXISTS`(`init_db()` 於啟動時跑;`rebuild_events()` 會 `DROP TABLE events` 後重建,僅手動 backfill 時用)。

---

## 3. 各資料表:來源 / 更新觸發 / 刪除保留

| 表 | 內容 | 來源 | 更新觸發 | 刪除 / 保留 |
|---|---|---|---|---|
| **events** | 公司債/增資 申報(稿本/生效) | TWSE `doc.twse.com.tw/server-java/t57sb01`(`web/scraper.py`,多工 + tenacity + 住宅代理;代號取自 `codes/listed.csv`+`codes/otc.csv`) | **手動**:`POST /api/scrape`(「一鍵抓取」;無參數=當月、給 year=整年回補)。**啟動**:背景 `sync_from_turso` 從雲端拉缺漏 | **不自動刪**。`UNIQUE(code,file_link)` 去重。只有手動 `rebuild_events()` 會整表重建 |
| **stock_names** | 代號→中文名 | FinMind `TaiwanStockInfo`(一次抓全部) | `ensure_names()` 惰性(第一次需要股名時);`force=True` 重抓 | 不刪 |
| **cb** | 可轉債發行資料(**發行時**轉換價、到期/賣回日、流通額…) | TPEx open API `bond_ISSBD5_data`(公開、一次回所有掛牌中) | `ensure_cb()`:**每天第一次**呼叫時整表刷新(看 K 線 `/api/cb`、開雷達、雷達 refresh 都會觸發);當天已抓過則 no-op | **每日整表 `DELETE` + 重灌**。→ **無歷史、含存活者偏差**(到期/下市的 CB 直接消失);這是策略分析的硬限制 |
| **kline** | 日 OHLCV | FinMind `TaiwanStockPrice` | `get_kline()` **惰性**(看個股 K 線時補缺的尾巴);**雷達「重新整理」**批次補所有 CB 股 | **LRU 30 天**:`cleanup_old(30)` 刪掉「`last_accessed` 超過 30 天」的整檔(**啟動時跑**)。注意:只有 `get_kline()` 會更新 `last_accessed`,直接讀表不算 |
| **kline_meta** | 每檔最後存取日 | `get_kline()` 寫入 | 同 kline | 隨 kline 一起被 LRU 刪 |
| **institutional** | 三大法人買賣超(外資/投信/自營) | FinMind `TaiwanStockInstitutionalInvestorsBuySell` | `ensure_institutional()` 惰性(看個股 chip/backtest 時);雷達 refresh 批次 | **>5 年(1825 天)裁切**:`cleanup_old(1825)`(**啟動時跑**)。只刪舊日期、不刪整檔 |
| **margin** | 融資/融券餘額 | FinMind `TaiwanStockMarginPurchaseShortSale` | 同 institutional | 同上(>5 年裁切) |
| **news** | 個股新聞 | FinMind `TaiwanStockNews`(逐日) | `ensure_news()` 惰性(看個股時,事件日 ±5 日窗) | **不刪** |
| **news_fetched** | 已抓新聞的日期標記 | `news.py` | 同 news(記 `(code,date)` 避免重抓) | 不刪 |
| **scrape_jobs** | 爬蟲工作記錄 + log | `web/scraper_job.py` | 每次 `POST /api/scrape` 新增一列 | **不刪**(會累積) |

> **雷達更新狀態**(`web/radar.py` 的 `_state`:running/done/total)是**記憶體內**,非資料表,重啟即歸零。

---

## 4. 觸發時機詳解

**① 啟動時**（`@app.on_event("startup")`，`web/app.py`）
- `init_db()` 建表(IF NOT EXISTS)。
- `kline.cleanup_old(30)` + `chip.cleanup_old(1825)` ← **唯二的自動刪除**。
- 背景 thread `sync_from_turso()`:若雲端 events 比本機多就拉下來。

**② 看個股(詳細分析)時惰性補抓** — 開啟某股會打這些端點,各自「補缺的尾巴」:
- `GET /api/kline/{code}` → `get_kline`(補價格 + 更新 last_accessed)
- `GET /api/chip/{code}`、`GET /api/backtest/{code}` → `ensure_institutional`/`ensure_margin`(backtest 也會先補籌碼)
- `GET /api/cb/{code}` → `ensure_cb`(每日首次)
- `GET /api/news/{code}` → `ensure_news`

**③ 手動按鈕**
- **「一鍵抓取」** → `POST /api/scrape` → `web/scraper.py` 爬 events。
- **CB 雷達「重新整理」** → `POST /api/radar/refresh` → 背景對所有掛牌中 CB 股**增量**補 kline/投信/融券到最新交易日(`GET /api/radar/status` 輪詢進度)。同一天資料已最新則幾乎不抓;遇新交易日約 3–4 分鐘。
- **`POST /api/update-codes`** → 重抓 `codes/listed.csv`+`codes/otc.csv`(TWSE ISIN)。
- **`POST /api/sync-from-cloud`** → 手動觸發 `sync_from_turso`。

**④ 每日首次** — `ensure_cb()`(cb 整表刷新)、`ensure_names()`(股名,實務上一次就夠)。

---

## 5. 外部服務與額度

| 服務 | 用途 | 認證/限制 |
|---|---|---|
| **FinMind REST** | kline、institutional、margin、stock_names、news | `FINMIND_TOKENS`(逗號分隔);每 token 600 次/小時;`web/finmind.py` 自動挑「用最少且未爆」的 token,402/401 標記耗盡至下個整點。`quota_remaining()` 彙總 |
| **TPEx** `bond_ISSBD5_data` | cb 發行資料 | 公開無認證,一次回全部 |
| **TWSE** `t57sb01` | 稿本/增資 爬蟲 | 需 `.env` 住宅代理(`PROXY_*`);`verify=False`(端點透過代理會出問題,刻意關閉) |
| **MOPS** `t120sg01` | **調整後**轉換價(最新轉換價 + 生效日) | 公開、UTF-8;**尚未整合**(已驗證可由 `bond_code` 推導參數抓取) |
| **Turso (libSQL)** | events 雲端備份 | `TURSO_DATABASE_URL` + `TURSO_AUTH_TOKEN`;未設定則略過 |

---

## 6. 雲端備份(Turso，只有 events)

- **寫**:`import_rows()`(爬蟲寫入 events)成功後,背景 thread `_sync_events_to_turso()` 把新列推上雲端。
- **讀/還原**:啟動時 + `POST /api/sync-from-cloud` → `sync_from_turso()`,若雲端列數 > 本機就補進本機。
- 其餘所有表(kline/chip/cb/news…)**只在本機**,不備份。

---

## 7. 刪除 / 保留速查

| 何時刪 | 刪什麼 |
|---|---|
| **每次 app 啟動** | kline:30 天未經 `get_kline` 存取的整檔;institutional/margin:超過 5 年的日期 |
| **每天第一次 `ensure_cb`** | 整張 `cb` 表(DELETE 後重灌當日快照) |
| 永不自動刪 | events、stock_names、news、news_fetched、scrape_jobs |
| 僅手動 | `rebuild_events()` 會 DROP+重建 events |

---

## 8. 已知限制 & 待辦

- **cb 無歷史**:每日覆蓋 → 存活者偏差 + 只有發行時轉換價(未還原調整)。**雷達的「靠近轉換價」用的就是發行價**。
- **調整後轉換價(MOPS t120sg01)尚未整合**:已驗證可抓「最新轉換價」,計畫為「看 K 線時惰性抓 + 小快取表」,雷達以發行價為主、看過的才精準。
- **kline 30 天 LRU**:研究用的回測 universe 若 30 天沒被 `get_kline` 碰到(直接讀表不算),啟動清理時會被刪 → 需重抓。
- **scrape_jobs 無上限**:長期會累積。
