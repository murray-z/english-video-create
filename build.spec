# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（Windows 安装包用），产物是 dist/EnglishVideo/ 目录。

Gradio 有大量动态导入和前端静态文件，必须用 collect_all 收全，
否则打出来的 exe 启动时会报模板缺失或模块找不到。
"""

from PyInstaller.utils.hooks import collect_all, copy_metadata

datas, binaries, hiddenimports = [], [], []

# 这些包需要连子模块和静态资源一起收进来
for pkg in ("gradio", "gradio_client", "safehttpx", "groovy", "pydub"):
    try:
        d, b, h = collect_all(pkg)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h

# gradio 启动时会用 importlib.metadata 读版本号，缺 dist-info 会直接崩
for dist in (
    "gradio", "gradio_client", "huggingface_hub", "safehttpx", "semantic_version",
    "fastapi", "starlette", "uvicorn", "typer", "click",
):
    try:
        datas += copy_metadata(dist)
    except Exception:
        pass

# ASGI 服务端和音频处理里靠字符串动态加载的模块
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    "anyio._backends._asyncio",
    "multipart",
    "python_multipart",
    "orjson",
    "tomlkit",
    "semantic_version",
    "httpx",
    "httpcore",
    "h11",
    "pandas",
    "numpy",
    "PIL",
    "requests",
    "ffmpy",
    "wave",
    "audioop",
]

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest", "IPython", "notebook"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EnglishVideo",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="EnglishVideo",
)
