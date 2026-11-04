@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "VENV=.venv"
set "PY=%VENV%\Scripts\python.exe"

if not exist "%PY%" (
    echo [1/2] 未找到虚拟环境，正在创建 .venv ...
    where py >nul 2>nul
    if errorlevel 1 (
        set "LAUNCHER=python"
    ) else (
        set "LAUNCHER=py -3"
    )
    %LAUNCHER% -m venv "%VENV%"
    if not exist "%PY%" (
        echo.
        echo [错误] 创建虚拟环境失败，请确认已安装 Python 3 并加入 PATH。
        pause
        exit /b 1
    )
    echo [2/2] 正在安装依赖，首次运行需要几分钟 ...
    "%PY%" -m pip install --upgrade pip
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [错误] 依赖安装失败，请检查网络或 requirements.txt。
        pause
        exit /b 1
    )
    echo 环境准备完成。
)

if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo.
        echo 已根据 .env.example 生成 .env，请填入 OPENAI_API_KEY 后保存。
        notepad ".env"
    )
)

set "STREAMLIT_BROWSER_GATHER_USAGE_STATS=false"

echo.
echo 正在启动 http://localhost:8501 ，按 Ctrl+C 停止。
echo.
start "" http://localhost:8501
"%PY%" -m streamlit run app.py --server.headless=true

if errorlevel 1 (
    echo.
    echo [错误] 服务异常退出，请查看上方日志。
    pause
)
endlocal
