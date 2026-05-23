#!/usr/bin/env bash
# 啟動 twstock 後端（首次執行會自動建立 .venv 並安裝套件）
# Finder 雙擊即可；首次需先 chmod +x start.command
set -e
cd "$(dirname "$0")"

if [ ! -f ".venv/bin/activate" ]; then
    echo "[setup] 第一次執行：建立虛擬環境..."
    python3 -m venv .venv
    source .venv/bin/activate
    echo "[setup] 安裝套件..."
    python -m pip install --upgrade pip
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

if [ ! -f "twstock.db" ]; then
    if grep -q "TURSO_DATABASE_URL" .env 2>/dev/null; then
        echo "[info] 使用 Turso 雲端資料庫，kline 快取將在首次查詢時自動建立"
    else
        echo "[warn] 找不到 twstock.db，資料庫是空的；請複製舊機器的 twstock.db 過來"
    fi
fi
[ -f ".env" ] || echo "[warn] 找不到 .env，爬蟲與 FinMind 會失效；請建立 .env 並填入 token / proxy"

echo
echo " twstock 後端啟動中  >  http://127.0.0.1:8765"
echo " 按 Ctrl+C 可停止"
echo
exec python -m uvicorn web.app:app --host 127.0.0.1 --port 8765
