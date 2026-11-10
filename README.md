# 英语短视频生成器

把一段情景对话文本，自动做成一集带插画、英文配音、中英字幕的横屏教学短视频（1920×1080）。

面向中老年英语学习场景：只需填 Key、贴对话、调语速，其余全自动。

## 功能

- **自动分镜**：识别主题和说话人，自动拆分场景、写画面描述、补中文翻译
- **角色统一**：同一系列所有场景沿用固定的角色参考图，形象不跑偏
- **英文配音**：Qwen TTS 多音色，语速可调（默认 0.75，适合慢速跟读）
- **一次产出**：场景插画、分段音频、整轨音频、SRT 中英字幕、分镜表、成片 MP4
- **本地合成**：FFmpeg 完成缓推镜头、字幕烧录和音画对齐，不依赖第三方剪辑服务

## 快速开始

### Windows（推荐发给同事）

1. 打开仓库 **Actions → Build Windows Installer → Run workflow**（推送 `v*` 标签也会自动触发）
2. 构建完成后在 Artifacts 下载 `EnglishVideo-Windows`
3. 双击 `EnglishVideoSetup-x.x.x.exe` 安装，桌面会生成快捷方式
4. 首次运行若被 SmartScreen 拦截：点「更多信息」→「仍要运行」

安装包自带 FFmpeg，无需另装 Python 或任何环境。

### macOS / 源码运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

也可以直接双击 `一键启动.command`，首次运行会自动创建虚拟环境并安装依赖。
Windows 已装 Python 的话可双击 `一键启动.bat`。

源码运行需要本机已安装 FFmpeg（macOS：`brew install ffmpeg`）。

## 使用

页面只有三个输入：

| 输入 | 说明 |
|---|---|
| 阿里云 API Key | 在[百炼控制台](https://bailian.console.aliyun.com/)创建；只保存在本机 `config.json`，下次自动带出 |
| 对话文本 | 上传 `.txt` 或直接粘贴到输入框 |
| 英文语速 | 0.5–1.2，默认 0.75；数值越小越慢 |

点「开始生成」，看日志跑完即可，右侧会显示成片预览。

### 对话文本格式

```text
情景模拟：结账与打包
顾客 You：Excuse me. The bill, please.
服务员 Waiter：Sure. How would you like to pay?
顾客 You：Can I pay by card?
服务员 Waiter：Of course. Here is the machine.
```

- 每句一行，格式为 `说话人：英文台词`
- 说话人支持 `顾客 / 服务员 / 店员 / 旁白 / 画外音`，也认 `You / Waiter / Narrator`
- 第一行的 `情景模拟：xxx` 会作为视频主题（也支持留空，自动取「情景对话」）
- 中文翻译和画面描述由模型自动补全，不需要手写

## 输出结构

```
series/02_restaurant/episodes/ep03/
├── episode.json      # 分镜数据（场景、台词、画面描述）
├── images/           # 每个场景一张 1920×1080 插画
├── audio/            # 分段音频 + full_narration.wav 整轨音频
├── subtitles.srt     # 中英双语字幕，时间码已对齐
├── storyboard.md     # 分镜表
└── final.mp4         # 成片
```

集数自动递增，已完成的集不会被覆盖。

## 项目结构

| 文件 | 作用 |
|---|---|
| `app.py` | Gradio 本地网页界面，唯一入口 |
| `script_parser.py` | 对话文本解析 + 调大模型生成分镜和中文翻译 |
| `media_generator.py` | `QwenMediaGenerator`：生图、TTS、变速封装 |
| `episode.py` | `Episode`：按分镜生成图片、音频、字幕、整轨音轨、分镜表 |
| `video.py` | FFmpeg 合成成片（缓推、字幕烧录、音画对齐） |
| `subtitle.py` | SRT 字幕生成 |
| `prompts.py` | 画风、构图、角色提示词 |
| `gen_character.py` | 生成新的系列角色形象模板（扩展系列时用） |
| `build.spec` | PyInstaller 打包配置 |
| `installer.iss` | Inno Setup 安装包脚本 |
| `.github/workflows/build-windows.yml` | Windows 安装包云端构建流水线 |
| `series/<系列>/series.json` | 系列配置：角色图、音色、语速、分辨率 |
| `series/<系列>/assets/character.png` | 角色参考图 |

## 自己构建 Windows 安装包

CI（推荐，无需 Windows 电脑）：推送 `v*` 标签或手动触发 `workflow_dispatch`，流水线会装依赖、打 exe、塞入 series 与 FFmpeg、启动自检，再用 Inno Setup 生成安装包。

本地 Windows 构建：

```powershell
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean build.spec
# 把 series/、config.json、ffmpeg\ffmpeg.exe 放进 dist\EnglishVideo\
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

## 环境要求

- Python 3.10+
- FFmpeg（安装包已自带；源码运行需本机安装）
- 阿里云百炼 API Key，需开通 `qwen-image-2.1-turbo`、`qwen3-tts-flash`、`qwen-plus`
- 中文字体：macOS 用苹方，Windows 用微软雅黑，脚本会自动选择

## 常见问题

- **提示「没有识别到台词」**：检查是否每句都以 `说话人：` 开头
- **日志提示「已使用默认分镜」**：大模型调用失败（Key、额度或网络），流程会自动兜底继续
- **端口 7860 被占用**：关掉占用该端口的程序后重启
- **生成的视频没有声音**：确认 FFmpeg 可用；安装包自带，源码运行需 `ffmpeg -version` 能跑通

## 安全说明

`config.json` 保存 API Key，已在 `.gitignore` 中排除，请勿提交到仓库。
仓库与安装包都不预置任何 Key，每位使用者填写自己的。
