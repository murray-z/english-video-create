"""本地网页界面：上传对话文本 → 自动出图/配音/字幕 → 合成成片。

给不写代码的人用：双击启动脚本后，把对话文本贴进去，点一次生成即可。
"""

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

# 关闭 Gradio 遥测：国内网络访问不到统计接口，会在启动时卡顿
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

# Windows 英文环境下控制台编码是 cp1252，直接打印中文会抛 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

import gradio as gr

from episode import Episode
from media_generator import QwenMediaGenerator
from script_parser import build_scenes, parse_script
from video import compose


def _app_dir() -> Path:
    """打包成 exe 后配置和素材放在 exe 同级目录；源码运行时用项目目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _use_bundled_ffmpeg(base: Path) -> None:
    """安装包自带 ffmpeg，优先使用，免得同事自己装。"""
    bundled = base / "ffmpeg"
    exe = bundled / ("ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg")
    if exe.exists():
        os.environ["PATH"] = str(bundled) + os.pathsep + os.environ.get("PATH", "")


ROOT = _app_dir()
_use_bundled_ffmpeg(ROOT)
SERIES_DIR = ROOT / "series"
CONFIG_PATH = ROOT / "config.json"

EXAMPLE_SCRIPT = """情景模拟：结账与打包
顾客 You：Excuse me. The bill, please.
服务员 Waiter：Sure. How would you like to pay?
顾客 You：Can I pay by card?
服务员 Waiter：Of course. Here is the machine.
顾客 You：Thank you. Could I have a doggy bag?
服务员 Waiter：No problem. I'll bring you a box."""


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def series_choices() -> list[tuple[str, str]]:
    """返回 [(系列显示名, 系列目录名)]。"""
    choices = []
    for p in sorted(SERIES_DIR.glob("*/series.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        choices.append((data.get("name", p.parent.name), p.parent.name))
    return choices


def next_episode_no(series_id: str) -> int:
    episodes = SERIES_DIR / series_id / "episodes"
    nums = [int(m.group(1)) for p in episodes.glob("ep*") if (m := re.match(r"ep(\d+)", p.name))]
    return max(nums, default=0) + 1


def load_script_file(path):
    """上传 .txt 后把内容填进文本框。"""
    if not path:
        return gr.update()
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return f"读取失败：{exc}"


def _default_series() -> str:
    """系列不让人选，默认用 config 里指定的，没有就用第一个。"""
    cfg = load_config()
    series_id = cfg.get("series_id", "")
    if series_id and (SERIES_DIR / series_id / "series.json").exists():
        return series_id
    choices = series_choices()
    return choices[0][1] if choices else ""


def generate(api_key, script_text, speed):
    if not (api_key or "").strip():
        yield "", None, "请先填写阿里云 API Key", ""
        return
    if not (script_text or "").strip():
        yield "", None, "请上传或粘贴对话文本", ""
        return
    if shutil.which("ffmpeg") is None:
        yield "", None, "未检测到 ffmpeg，请先安装后再运行（Mac: brew install ffmpeg）", ""
        return

    series_id = _default_series()
    if not series_id:
        yield "", None, "series/ 下没有找到系列配置", ""
        return

    parsed_title, lines = parse_script(script_text)
    if not lines:
        yield "", None, "没有识别到台词，请按「顾客：英文台词」的格式填写", ""
        return

    # 集数自动递增，主题从文本第一行自动识别
    ep_no = next_episode_no(series_id)
    ep_dir = SERIES_DIR / series_id / "episodes" / f"ep{ep_no:02d}"

    log = f"识别到 {len(lines)} 句台词，正在生成分镜……\n"
    yield log, None, "正在生成分镜，请稍候……", str(ep_dir)

    series_meta = json.loads((SERIES_DIR / series_id / "series.json").read_text(encoding="utf-8"))
    final_title = parsed_title or "情景对话"
    scenes, note = build_scenes(
        api_key=api_key.strip(),
        title=final_title,
        lines=lines,
        series_desc=series_meta.get("description", ""),
    )
    log += note + "\n"

    meta = {"title": final_title, "scenes": []}
    for idx, scene in enumerate(scenes, 1):
        scene_lines = []
        for line in scene["lines"]:
            item = {"speaker": line["speaker"], "text": line["text"], "gap": 0.8}
            zh = (line.get("zh") or "").strip()
            if zh:
                item["subtitle"] = f'{line["text"]}\n{zh}'
            scene_lines.append(item)
        meta["scenes"].append({
            "id": f"s{idx}",
            "title": f"场景{idx}",
            "hold": 1.0,
            "image_prompt": scene["image_prompt"],
            "overlay": "",
            "lines": scene_lines,
        })

    ep_dir.mkdir(parents=True, exist_ok=True)
    (ep_dir / "episode.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 记住 Key 和语速，下次打开不用重填
    cfg = load_config()
    cfg["api_key"] = api_key.strip()
    cfg["series_id"] = series_id
    cfg["tts_speed"] = float(speed)
    save_config(cfg)

    q: queue.Queue = queue.Queue()
    state: dict = {}

    class _Writer:
        def write(self, text):
            if text:
                q.put(text)

        def flush(self):
            pass

    def worker():
        try:
            with redirect_stdout(_Writer()), redirect_stderr(_Writer()):
                print(f"开始生成：{final_title}（{len(meta['scenes'])} 个场景）\n")
                gen = QwenMediaGenerator(api_key=api_key.strip(), output_dir=str(ep_dir))
                Episode(ep_dir, gen=gen, speed=float(speed)).build()
                print("\n合成视频中……")
                out = compose(ep_dir)
            state["video"] = str(out)
        except Exception as exc:  # 把异常显示到页面，而不是让程序崩掉
            state["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    while True:
        try:
            item = q.get(timeout=0.5)
        except queue.Empty:
            yield log[-8000:], None, "生成中，请勿关闭页面……", str(ep_dir)
            continue
        if item is None:
            break
        log += item
        yield log[-8000:], None, "生成中，请勿关闭页面……", str(ep_dir)

    if "error" in state:
        yield log[-8000:], None, f"生成失败：{state['error']}", str(ep_dir)
    else:
        yield log[-8000:], state["video"], f"完成：{state['video']}", str(ep_dir)


def open_output(ep_dir):
    if not ep_dir:
        return "还没有生成过视频"
    path = Path(ep_dir)
    if not path.exists():
        return f"目录还不存在：{path}"
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    elif sys.platform.startswith("win"):
        os.startfile(str(path))  # noqa: S606
    else:
        subprocess.run(["xdg-open", str(path)], check=False)
    return f"已打开：{path}"


def build_ui() -> gr.Blocks:
    cfg = load_config()
    default_series = _default_series()

    # 语速默认跟随系列配置，之后以用户上次调过的为准
    default_speed = 0.75
    if default_series:
        series_meta = json.loads((SERIES_DIR / default_series / "series.json").read_text(encoding="utf-8"))
        default_speed = float(series_meta.get("tts_speed", 0.75))
    if cfg.get("tts_speed"):
        default_speed = float(cfg["tts_speed"])

    with gr.Blocks(title="英语短视频生成器") as demo:
        gr.Markdown(
            "# 英语短视频生成器\n"
            "填写 API Key、粘贴对话文本、调好语速，点「开始生成」，"
            "分镜、中文翻译、画面、配音、字幕、成片全自动完成。"
        )

        api_key = gr.Textbox(
            label="阿里云 API Key",
            type="password",
            value=cfg.get("api_key", ""),
            placeholder="sk-...",
            info="在阿里云百炼控制台创建，只保存在本机 config.json",
        )

        script_file = gr.File(label="上传对话文本（.txt）", file_types=[".txt", ".md"], type="filepath")
        script_text = gr.Textbox(
            label="对话文本（也可以直接粘贴到这里）",
            lines=14,
            placeholder=EXAMPLE_SCRIPT,
        )
        gr.Markdown(
            "格式要求：每句一行，`说话人：英文台词`。说话人可写「顾客 / 服务员 / 旁白」，"
            "第一行可用 `情景模拟：主题` 指定主题。中文翻译和画面描述会自动生成。"
        )

        speed = gr.Slider(
            minimum=0.5, maximum=1.2, value=default_speed, step=0.05,
            label="英文语速",
            info="数值越小越慢，0.75 适合老年受众，建议 0.7–0.9",
        )

        generate_btn = gr.Button("开始生成", variant="primary", size="lg")

        log = gr.Textbox(label="生成日志", lines=10, max_lines=18, autoscroll=True)
        with gr.Row():
            video = gr.Video(label="成片预览")
            status = gr.Markdown()
        last_dir = gr.State("")
        open_btn = gr.Button("打开输出文件夹")

        script_file.change(load_script_file, inputs=script_file, outputs=script_text)
        generate_btn.click(
            generate,
            inputs=[api_key, script_text, speed],
            outputs=[log, video, status, last_dir],
        )
        open_btn.click(open_output, inputs=last_dir, outputs=status)

    return demo


if __name__ == "__main__":
    # 打包后的冒烟测试入口：只构建界面，不启动服务
    if "--self-check" in sys.argv:
        build_ui()
        print("OK: UI built")
        sys.exit(0)

    build_ui().launch(
        inbrowser=True,
        server_name="127.0.0.1",
        server_port=7860,
        allowed_paths=[str(ROOT)],
        show_api=False,
    )
