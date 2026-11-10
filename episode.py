"""单集素材构建：读取 episode.json，自动产出图片 / 音频 / SRT / 分镜表。"""

import json
import os
import re
import wave
from pathlib import Path

from media_generator import QwenMediaGenerator
from prompts import (
    CHARACTER_PROMPT,
    CHARACTER_PROMPTS,
    DEFAULT_SIZE,
    SUPPORTING_PROMPTS,
    build_scene_prompt,
)
from subtitle import write_srt


class Episode:
    def __init__(
        self,
        episode_dir: str | Path,
        gen: QwenMediaGenerator | None = None,
        speed: float | None = None,
    ):
        self.dir = Path(episode_dir).resolve()
        self.meta = json.loads((self.dir / "episode.json").read_text(encoding="utf-8"))

        # 系列目录 = episodes/ 的上一级
        series_dir = self.dir.parent.parent
        self.series = json.loads((series_dir / "series.json").read_text(encoding="utf-8"))
        self.character = series_dir / self.series["character"]
        self.size = self.series.get("image_size", DEFAULT_SIZE)
        # 语速优先用调用方传入的（页面上可调），否则用系列默认值
        self.speed = float(speed if speed is not None else self.series.get("tts_speed", 1.0))
        self.voices = self.series.get("voices", {})
        self.character_prompt = CHARACTER_PROMPTS.get(
            self.series.get("character_style", "elder_woman"), CHARACTER_PROMPT
        )
        self.supporting_prompt = SUPPORTING_PROMPTS.get(
            self.series.get("supporting_style", ""), ""
        )

        self.images_dir = self.dir / "images"
        self.audio_dir = self.dir / "audio"
        self.gen = gen or QwenMediaGenerator(output_dir=str(self.dir))

    # ------------------------------------------------------------------

    def build(self, dry_run: bool = False, resume: bool = False) -> None:
        if dry_run:
            print(f"[dry-run] 角色参考图: {self.character}")
            print(f"[dry-run] 输出分辨率: {self.size}\n")

        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        cursor = 0.0
        srt_entries = []
        rows = []
        clips = []

        for idx, scene in enumerate(self.meta["scenes"], 1):
            scene_id = scene["id"]
            prefix = f"{idx:02d}_{scene_id}"
            scene_start = cursor

            # 1. 图片
            image_name = f"{prefix}.png"
            image_path = self.images_dir / image_name
            if not dry_run and not (resume and image_path.exists()):
                self.gen.gen_image(
                    prompt=build_scene_prompt(
                        scene["image_prompt"], self.character_prompt, self.supporting_prompt
                    ),
                    image=str(self.character),
                    size=self.size,
                    prompt_extend=True,
                    filename=str(image_path),
                )
            print(f"[图片] {image_name}")

            # 2. 台词音频 + 字幕
            for line_idx, line in enumerate(scene.get("lines", []), 1):
                speaker = line["speaker"]
                voice = line.get("voice") or self.voices.get(speaker, "Cherry")
                audio_name = f"{prefix}_{line_idx:02d}_{speaker}.wav"

                if dry_run:
                    duration = self._estimate_duration(line["text"])
                else:
                    audio_path = self.audio_dir / audio_name
                    if not (resume and audio_path.exists()):
                        audio_path = Path(self.gen.gen_tts(
                            text=line["text"], voice=voice,
                            filename=str(audio_path), speed=self.speed,
                        ))
                    duration = self._audio_duration(str(audio_path))

                srt_entries.append({
                    "start": cursor,
                    "end": cursor + duration,
                    "text": line.get("subtitle", line["text"]),
                })
                if not dry_run:
                    clips.append((cursor, str(audio_path)))
                print(f"[音频] {audio_name}  {duration:.1f}s")
                cursor += duration + line.get("gap", 0.0)

            # 3. 场景末尾停留（留给观众消化 / 跟读）
            cursor += scene.get("hold", 1.5)

            rows.append({
                "prefix": prefix,
                "image": image_name,
                "start": scene_start,
                "end": cursor,
                "title": scene.get("title", scene_id),
                "overlay": scene.get("overlay", ""),
            })

        if not dry_run:
            write_srt(srt_entries, self.dir / "subtitles.srt")
            if clips:
                self._merge_audio(clips, cursor, self.audio_dir / "full_narration.wav")
        self._write_storyboard(rows, cursor)

        print(f"\n总时长: {self._fmt(cursor)}")
        print(f"整轨音频: {self.audio_dir / 'full_narration.wav'}")
        print(f"字幕: {self.dir / 'subtitles.srt'}")
        print(f"分镜表: {self.dir / 'storyboard.md'}")

    # ------------------------------------------------------------------

    @staticmethod
    def _merge_audio(clips: list[tuple[float, str]], total: float, out_path: Path) -> None:
        """把各段音频按时间轴合并成一条含静音的完整音轨。

        剪映里只需拖这一条音频到 00:00，就与画面完全对齐。
        """
        with wave.open(clips[0][1], "rb") as w:
            rate, width, channels = w.getframerate(), w.getsampwidth(), w.getnchannels()

        frame_bytes = width * channels
        buf = bytearray(int(total * rate) * frame_bytes)

        for start, path in clips:
            with wave.open(path, "rb") as w:
                data = w.readframes(w.getnframes())
            offset = int(start * rate) * frame_bytes
            buf[offset:offset + len(data)] = data

        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(channels)
            w.setsampwidth(width)
            w.setframerate(rate)
            w.writeframes(bytes(buf))

    def _write_storyboard(self, rows: list[dict], total: float) -> None:
        lines = [
            f"# {self.meta.get('title', self.dir.name)}",
            "",
            f"- 系列：{self.series.get('name', '')}",
            f"- 总时长：{self._fmt(total)}",
            f"- 图片规格：{self.size}（剪映项目选 1080P / 9:16 / 30fps）",
            "",
            "| # | 时间 | 时长 | 图片 | 画面 | 叠加文字 |",
            "|---|---|---|---|---|---|",
        ]
        for r in rows:
            lines.append(
                f"| {r['prefix'].split('_')[0]} | {self._fmt(r['start'])} - {self._fmt(r['end'])} "
                f"| {r['end'] - r['start']:.1f}s | images/{r['image']} "
                f"| {r['title']} | {r['overlay']} |"
            )
        lines += [
            "",
            "## 剪辑说明",
            "1. 新建项目：9:16 / 1080P / 30fps",
            "2. 按表格顺序拖入 images/，**每张图时长必须按上表的「时长」拉长**（默认 5 秒不够）",
            "3. 拖入 audio/full_narration.wav 一条整轨音频到 00:00（已含停顿，原样对齐）",
            "4. 文本 → 导入字幕 → 选择 subtitles.srt（自动对齐时间码）",
            "5. 每张图片加 1.0→1.06 的缓推关键帧，避免画面像 PPT",
            "6. 转场统一用「叠化」，时长 0.3s",
            "7. 开头 3 秒叠加「叠加文字」，字号不小于画面高度 8%",
        ]
        (self.dir / "storyboard.md").write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _audio_duration(path: str) -> float:
        """按文件实际大小计算时长。

        Qwen TTS 返回的 WAV 头部尺寸字段是流式占位值，
        不能用 getnframes()，只能用真实字节数换算。
        """
        try:
            with wave.open(path, "rb") as w:
                frame_bytes = w.getsampwidth() * w.getnchannels() * w.getframerate()

            size = os.path.getsize(path)
            with open(path, "rb") as f:
                head = f.read(1024)
            idx = head.find(b"data")
            audio_bytes = size - (idx + 8) if idx >= 0 else size - 44
            return round(max(audio_bytes, 0) / frame_bytes, 2)
        except (wave.Error, EOFError, OSError):
            return 2.0

    @staticmethod
    def _estimate_duration(text: str) -> float:
        """dry-run 用：中文按字、英文按词粗略估算。"""
        cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
        words = len(re.findall(r"[A-Za-z']+", text))
        return round(cjk * 0.28 + words * 0.45, 2)

    @staticmethod
    def _fmt(seconds: float) -> str:
        m, s = divmod(int(round(seconds)), 60)
        return f"{m:02d}:{s:02d}"
