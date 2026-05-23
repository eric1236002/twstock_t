@echo off
REM 啟動 twstock 後端（首次執行會自動建立 .venv 並安裝套件）
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [setup] 第一次執行：建立虛擬環境...
    python -m venv .venv
    if errorlevel 1 (
        echo [error] 找不到 python，請先安裝 Python 3 並勾選 Add to PATH
        pause
        exit /b 1
    )
    call ".venv\Scripts\activate.bat"
    echo [setup] 安裝套件...
    python -m pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call ".venv\Scripts\activate.bat"
)

if not exist "twstock.db" (
    findstr /C:"TURSO_DATABASE_URL" .env >nul 2>&1
    if errorlevel 1 (
        echo [warn] 找不到 twstock.db，資料庫是空的；請把舊機器的 twstock.db 複製過來
    ) else (
        echo [info] 使用 Turso 雲端資料庫，kline 快取將在首次查詢時自動建立
    )
)
if not exist ".env" (
    echo [warn] 找不到 .env，爬蟲與 FinMind 會失效；請建立 .env 並填入 token / proxy
)

echo.
echo  twstock 後端啟動中  ^>  http://127.0.0.1:8765
echo  按 Ctrl+C 可停止
echo.
python -m uvicorn web.app:app --host 127.0.0.1 --port 8765
pause
