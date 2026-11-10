@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY=python"
where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 (
    echo 未检测到 Python 3。请先安装：https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"。
    pause
    exit /b 1
  )
  set "PY=py -3"
)

rem 环境不可用（如从 Mac 拷过来）就重建
if not exist ".venv\Scripts\python.exe" (
  if exist ".venv" rmdir /s /q ".venv"
  echo 首次运行，正在准备运行环境（只需一次）……
  %PY% -m venv .venv || goto :error
)

call .venv\Scripts\activate.bat
python -c "import gradio" >nul 2>nul || python -m pip install -q -r requirements.txt

echo 正在打开网页，请稍候……
python app.py
goto :eof

:error
echo 环境准备失败，请把上面的报错发给管理员。
pause
