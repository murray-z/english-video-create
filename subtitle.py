"""SRT 字幕生成。"""

from pathlib import Path


def format_timestamp(seconds: float) -> str:
    """秒 -> SRT 时间戳 HH:MM:SS,mmm"""
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(entries: list[dict], path: str | Path) -> None:
    """写入 SRT 文件。

    entries: [{"start": 秒, "end": 秒, "text": "字幕内容"}]
    """
    lines = []
    for i, item in enumerate(entries, 1):
        lines.append(str(i))
        lines.append(f"{format_timestamp(item['start'])} --> {format_timestamp(item['end'])}")
        lines.append(item["text"])
        lines.append("")

    Path(path).write_text("\n".join(lines), encoding="utf-8")
