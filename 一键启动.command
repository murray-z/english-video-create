#!/bin/bash
# 双击启动：首次运行会自动安装依赖，之后直接打开网页
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "未检测到 Python 3。请先安装：https://www.python.org/downloads/"
  read -n 1 -s -r -p "按任意键退出……"
  exit 1
fi

# 环境不可用（如从别的系统拷过来）就重建
if [ ! -x ".venv/bin/python" ]; then
  rm -rf .venv
  echo "首次运行，正在准备运行环境（只需一次）……"
  python3 -m venv .venv || exit 1
fi

source .venv/bin/activate
python -c "import gradio" >/dev/null 2>&1 || python -m pip install -q -r requirements.txt

echo "正在打开网页，请稍候……"
python app.py
