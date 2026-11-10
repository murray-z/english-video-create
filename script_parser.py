"""把一段情景对话文本解析成分镜。

- parse_script: 从「顾客：English...」这类文本里提取主题和台词
- build_scenes: 调文本大模型自动拆分镜、写画面描述、补中文翻译；失败时用默认分镜兜底
"""

import json
import re

import requests

CHAT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
MODEL = "qwen-plus"

ROLE_CN = {"you": "顾客", "waiter": "服务员", "narrator": "旁白"}

# 说话人标签：支持「顾客」「顾客 You」「Waiter」等写法
_LABEL = r"(?:顾客|服务员|店员|旁白|画外音|主角|You|Waiter|Narrator)"
_SPEAKER_RE = re.compile(rf"({_LABEL}(?:\s+{_LABEL})?)\s*[：:]", re.IGNORECASE)


def _speaker_key(label: str) -> str:
    text = label.lower()
    if "服务员" in text or "店员" in text or "waiter" in text:
        return "waiter"
    if "旁白" in text or "画外音" in text or "narrator" in text:
        return "narrator"
    return "you"


def parse_script(text: str) -> tuple[str, list[dict]]:
    """解析对话文本，返回 (主题, 台词列表)。"""
    text = (text or "").replace("\r\n", "\n")
    matches = list(_SPEAKER_RE.finditer(text))
    if not matches:
        return "", []

    # 第一句台词之前的内容视为标题，取最后一行
    prefix = [ln.strip() for ln in text[:matches[0].start()].strip().splitlines() if ln.strip()]
    title = prefix[-1] if prefix else ""
    title = re.sub(r"^情景模拟\s*[：:]?\s*", "", title).strip()

    lines = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = re.sub(r"\s+", " ", text[match.end():end]).strip()
        if body:
            lines.append({"speaker": _speaker_key(match.group(1)), "text": body})
    return title, lines


def build_scenes(api_key, title: str, lines: list[dict], series_desc: str = ""):
    """返回 (分镜列表, 提示信息)。"""
    try:
        scenes = _llm_scenes(api_key, title, lines, series_desc)
        if _valid(scenes, len(lines)):
            return scenes, "分镜与中文翻译已由 AI 生成。"
        note = "AI 分镜结果不完整，已使用默认分镜。"
    except Exception as exc:  # 网络、额度、解析失败都退回默认分镜
        note = f"AI 分镜不可用（{type(exc).__name__}），已使用默认分镜。"
    return _fallback_scenes(title, lines, series_desc), note


def _llm_scenes(api_key, title, lines, series_desc):
    if not api_key:
        from media_generator import API_KEY

        api_key = API_KEY

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "你是一名短视频分镜师，擅长把英语情景对话改写成适合插画绘制的分镜脚本。"},
            {"role": "user", "content": _prompt(title, lines, series_desc)},
        ],
        "temperature": 0.7,
    }
    resp = requests.post(
        CHAT_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    data = json.loads(_json_content(content))

    scenes = []
    idx = 0
    for scene in data.get("scenes", []):
        prompt = str(scene.get("image_prompt", "")).strip()
        items = []
        for zh_item in scene.get("lines", []):
            if idx >= len(lines):
                break
            zh = zh_item.get("zh", "") if isinstance(zh_item, dict) else str(zh_item)
            items.append({"speaker": lines[idx]["speaker"], "text": lines[idx]["text"], "zh": zh.strip()})
            idx += 1
        if prompt and items:
            scenes.append({"image_prompt": prompt, "lines": items})
    return scenes


def _prompt(title, lines, series_desc):
    script = "\n".join(
        f"{i}. [{ROLE_CN.get(line['speaker'], '顾客')}] {line['text']}"
        for i, line in enumerate(lines, 1)
    )
    return f"""请根据下面的英语情景对话，输出分镜脚本 JSON。
已知设定：{series_desc or "通用生活场景"}
主题：{title or "情景对话"}

要求：
1. 台词顺序不能变，不能增删；每 2 句合成一个场景，最后不足 2 句单独成场景。
2. 每个场景写一条中文画面描述：写明人物、动作、表情、环境与必要道具；只描述画面，不要出现任何文字、字幕、对话框；不要写“留白”。
3. 为每句英文写准确、口语化的中文翻译。
4. 只输出 JSON，不要 markdown 代码块。

JSON 结构：
{{"title": "主题", "scenes": [{{"image_prompt": "画面描述", "lines": [{{"zh": "中文翻译"}}]}}]}}

对话：
{script}"""


def _valid(scenes: list[dict], total: int) -> bool:
    if not scenes:
        return False
    count = sum(len(scene["lines"]) for scene in scenes)
    return count == total and all(scene["image_prompt"] and scene["lines"] for scene in scenes)


def _fallback_scenes(title, lines, series_desc):
    scenes = []
    for i in range(0, len(lines), 2):
        chunk = lines[i:i + 2]
        names = []
        for line in chunk:
            name = ROLE_CN.get(line["speaker"], "顾客")
            if name not in names:
                names.append(name)
        who = "和".join(names)
        prompt = (
            f"{series_desc or '生活场景'}。{who}正在围绕“{title or '日常交流'}”对话，"
            "表情自然、动作符合语境；必须画出必要的环境和道具，横屏 16:9 构图，人物左右分居。"
        )
        scenes.append({
            "image_prompt": prompt,
            "lines": [
                {"speaker": line["speaker"], "text": line["text"], "zh": ""} for line in chunk
            ],
        })
    return scenes


def _json_content(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("返回内容里没有 JSON")
    return text[start:end + 1]
