"""用 ffmpeg 把已生成的图片 / 音频 / 字幕直接合成成片。

用法：
    python build_video.py series/02_restaurant/episodes/ep01_bill_and_pack
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from episode import Episode

FPS = 30
WIDTH, HEIGHT = 1920, 1080

# 跨平台中文字体：macOS 用苹方，Windows 用微软雅黑
if sys.platform == "darwin":
    FONT_FILE = "/System/Library/Fonts/PingFang.ttc"
    FONT_NAME = "PingFang SC"
elif sys.platform.startswith("win"):
    FONT_FILE = "C:/Windows/Fonts/msyh.ttc"
    FONT_NAME = "Microsoft YaHei"
else:
    FONT_FILE = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    FONT_NAME = "Noto Sans CJK SC"

# drawtext 里冒号是参数分隔符，Windows 盘符需要转义
FONT_ARG = FONT_FILE.replace(":", "\\:")

# 字幕样式：白字黑边，底部居中，字号偏大（照顾老年受众）
SUB_STYLE = (
    f"FontName={FONT_NAME},FontSize=16,PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,"
    "Alignment=2,MarginV=36"
)

# 钩子文案样式预设，颜色取自插画色板，保证与画面同一套色系
OVERLAY_PRESETS = {
    # 砖红色块 + 白字：对比最强，远景也看得清
    "band": {
        "fontcolor": "white",
        "bordercolor": "0x3D2B1F",
        "borderw": 3,
        "box": True,
        "boxcolor": "0xC8553D@0.92",
        "boxborderw": 28,
        "fontsize": 58,
        "y": 60,
    },
    # 暖黄字 + 深棕粗描边：绘本标签感，更活泼
    "highlight": {
        "fontcolor": "0xF2C94C",
        "bordercolor": "0x3D2B1F",
        "borderw": 7,
        "box": False,
        "boxcolor": "0x000000@0",
        "boxborderw": 0,
        "fontsize": 62,
        "y": 60,
    },
}
OVERLAY_STYLE = "band"

# 主题压在首个场景画面上方的字号与纵向位置
TITLE_FONTSIZE = 90
TITLE_Y = 44


def _esc(text: str) -> str:
    """转义 drawtext 里会引起解析问题的字符。"""
    return text.replace("'", "’").replace(":", "：")


def _run(cmd: list[str], cwd: Path) -> None:
    print(" ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def build_timeline(ep: Episode) -> tuple[list[dict], float]:
    """按 episode.json + 实际音频长度还原分镜时间轴。"""
    cursor = 0.0
    scenes = []
    for idx, scene in enumerate(ep.meta["scenes"], 1):
        prefix = f"{idx:02d}_{scene['id']}"
        start = cursor
        for line_idx, line in enumerate(scene.get("lines", []), 1):
            speaker = line["speaker"]
            audio = ep.audio_dir / f"{prefix}_{line_idx:02d}_{speaker}.wav"
            if not audio.exists():
                raise FileNotFoundError(f"缺少音频: {audio}")
            cursor += Episode._audio_duration(str(audio)) + line.get("gap", 0.0)
        cursor += scene.get("hold", 1.5)

        image = ep.images_dir / f"{prefix}.png"
        if not image.exists():
            raise FileNotFoundError(f"缺少图片: {image}")
        scenes.append({
            "image": image,
            "start": start,
            "end": cursor,
            "overlay": scene.get("overlay", ""),
        })
    return scenes, cursor


def _clip_filter(duration: float, overlay: str, title: str = "") -> str:
    """2 倍放大后做缓慢推近，避免缩放抖动。"""
    frames = max(int(round(duration * FPS)), 1)
    step = 0.06 / frames
    vf = (
        f"scale={WIDTH * 2}:{HEIGHT * 2}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH * 2}:{HEIGHT * 2},"
        f"zoompan=z='min(zoom+{step:.6f},1.06)':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS},"
        f"format=yuv420p"
    )
    s = OVERLAY_PRESETS[OVERLAY_STYLE]
    y = s["y"]

    # 主题：白字深色描边，无底色，固定在画面上方
    if title:
        vf += (
            f",drawtext=fontfile={FONT_ARG}:text='{_esc(title)}':"
            f"fontcolor=white:fontsize={TITLE_FONTSIZE}:"
            f"borderw=7:bordercolor=0x3D2B1F:"
            f"x='(w-text_w)/2':y={TITLE_Y}"
        )
        y = TITLE_Y + TITLE_FONTSIZE + 24

    if overlay:
        vf += (
            f",drawtext=fontfile={FONT_ARG}:text='{_esc(overlay)}':"
            f"fontcolor={s['fontcolor']}:fontsize={s['fontsize']}:"
            f"borderw={s['borderw']}:bordercolor={s['bordercolor']}:"
            f"box={1 if s['box'] else 0}:boxcolor={s['boxcolor']}:"
            f"boxborderw={s['boxborderw']}:"
            f"x='(w-text_w)/2*min(1,t/0.5)':y={y}"
        )
    return vf


def compose(ep_dir: str | Path) -> Path:
    global WIDTH, HEIGHT

    ep = Episode(ep_dir)
    WIDTH, HEIGHT = (int(v) for v in ep.size.split("*"))

    scenes, total = build_timeline(ep)
    out = ep.dir / "final.mp4"
    narration = ep.audio_dir / "full_narration.wav"
    srt = ep.dir / "subtitles.srt"
    if not narration.exists() or not srt.exists():
        raise FileNotFoundError("缺少 full_narration.wav 或 subtitles.srt，请先生成该集素材")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        clip_list = []

        # 1. 每张图生成一段带缓慢推近的视频；首帧压上主题
        for i, scene in enumerate(scenes, 1):
            duration = scene["end"] - scene["start"]
            title = ep.meta.get("title", "") if i == 1 else ""
            clip = tmp_dir / f"clip_{i:02d}.mp4"
            _run([
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(scene["image"]),
                "-vf", _clip_filter(duration, scene["overlay"], title),
                "-frames:v", str(max(int(round(duration * FPS)), 1)),
                "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-pix_fmt", "yuv420p", "-r", str(FPS),
                str(clip),
            ], ep.dir)
            clip_list.append(clip)
            print(f"[片段] {i}/{len(scenes)}  {duration:.2f}s")

        # 2. 拼接画面
        concat_txt = tmp_dir / "clips.txt"
        concat_txt.write_text(
            "".join(f"file '{c.name}'\n" for c in clip_list), encoding="utf-8"
        )
        silent = tmp_dir / "video_only.mp4"
        _run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", concat_txt.name,
            "-c", "copy", str(silent),
        ], tmp_dir)

        # 3. 叠加字幕 + 整轨音频（字幕用相对路径，避免 Windows 盘符冒号被误解析）
        _run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(silent),
            "-i", str(narration),
            "-vf", f"subtitles={srt.name}:force_style='{SUB_STYLE}'",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            str(out),
        ], ep.dir)

    print(f"\n成片: {out}  总时长 {total:.1f}s")
    return out


if __name__ == "__main__":
    compose(sys.argv[1])
