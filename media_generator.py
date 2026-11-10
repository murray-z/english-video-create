import base64
import os
import subprocess
import time
from pathlib import Path

import requests

# 不硬编码 Key：优先用调用方传入的，其次读环境变量
API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")

API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

SUPPORTED_IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp", ".gif"}
MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


class QwenMediaGenerator:
    """封装 Qwen 图片生成 + TTS 语音合成，方便短视频批量制作。"""

    def __init__(
        self,
        api_key: str | None = None,
        output_dir: str = "./output",
        timeout: int = 300,
    ):
        self.api_key = api_key or API_KEY
        self.output_dir = Path(output_dir)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    # ------------------------------------------------------------------
    # 图片生成（图生图 / 图像编辑）
    # ------------------------------------------------------------------

    def gen_image(
        self,
        prompt: str,
        image: str | list[str] | None = None,
        model: str = "qwen-image-2.1-turbo",
        size: str = "720*1280",
        n: int = 1,
        seed: int | None = None,
        prompt_extend: bool = True,
        watermark: bool = False,
        filename: str | None = None,
    ) -> list[str]:
        """生成图片。

        Args:
            prompt: 画面描述 / 编辑指令。
            image: 参考图（公网 URL 或本地路径）。None 表示文生图；
                   单张传字符串，多张传列表（最多 10 张）。
            model: 模型名称。
            size: 输出分辨率，如 "720*1280"（竖屏）。
            n: 生成数量，1~6。
            prompt_extend: 是否启用 prompt 智能扩写。
            watermark: 是否加水印。
            seed: 随机种子。
            filename: 保存文件名或完整路径。为 None 时自动命名；
                   只传文件名时保存到 output_dir，多张输出时自动追加序号。

        Returns:
            生成图片的本地路径列表。
        """
        if not prompt or not prompt.strip():
            raise ValueError("prompt 不能为空")

        content = []
        if image is not None:
            images = [image] if isinstance(image, str) else image
            for img in images:
                content.append({"image": self._image_to_input(img)})
        content.append({"text": prompt})

        parameters = {
            "n": n,
            "prompt_extend": prompt_extend,
            "watermark": watermark,
            "size": size,
        }
        if seed is not None:
            parameters["seed"] = seed

        payload = {
            "model": model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": parameters,
        }

        data = self._post(payload)
        image_urls = [
            item["image"]
            for item in data["output"]["choices"][0]["message"]["content"]
            if "image" in item
        ]
        if not image_urls:
            raise RuntimeError(f"API 返回中未包含图片: {data}")

        total = len(image_urls)
        saved = []
        for idx, url in enumerate(image_urls):
            path = self._save_path(
                filename,
                default_name=f"image_{int(time.time())}",
                suffix=".png",
                idx=idx if total > 1 else None,
            )
            self._download(url, path)
            saved.append(str(path))
        return saved

    # ------------------------------------------------------------------
    # TTS 语音合成
    # ------------------------------------------------------------------

    def gen_tts(
        self,
        text: str,
        voice: str = "Cherry",
        filename: str | None = None,
        instructions: str | None = None,
        speed: float = 1.0,
    ) -> str:
        """合成语音。

        Args:
            text: 要合成的文本。
            voice: 音色名，如 Cherry / Maia / Jennifer 等。
            filename: 保存文件名或完整路径（默认自动生成 .wav）。
            instructions: 自然语言风格指令（需模型支持，当前账号不可用）。
            speed: 语速倍率，1.0 为原速，0.85 表示放慢 15%。用 ffmpeg 变速，
                保持音高不变，适合老年受众。

        Returns:
            音频文件的本地路径。
        """
        parameters = {"language_type": "Auto"}
        model = "qwen3-tts-flash"
        if instructions:
            model = "qwen3-tts-instruct-flash"
            parameters["instructions"] = instructions
            parameters["optimize_instructions"] = True

        payload = {
            "model": model,
            "input": {
                "text": text,
                "voice": voice,
            },
            "parameters": parameters,
        }

        data = self._post(payload)
        try:
            audio_url = data["output"]["audio"]["url"]
        except (KeyError, TypeError):
            raise RuntimeError(f"未获取到音频地址，响应内容: {data}")

        path = self._save_path(filename, default_name=f"tts_{int(time.time())}", suffix=".wav")
        self._download(audio_url, path)
        self._fix_wav_header(path)
        if speed != 1.0:
            self._change_speed(path, speed)
        return str(path)

    @staticmethod
    def _change_speed(path: Path, speed: float) -> None:
        """用 ffmpeg 变速（atempo 滤镜保持音高不变）。"""
        tmp = path.with_name(path.stem + "_tmp.wav")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path),
             "-filter:a", f"atempo={speed}", str(tmp)],
            check=True,
        )
        tmp.replace(path)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _fix_wav_header(path: Path) -> None:
        """修正 WAV 头部的尺寸字段。

        Qwen TTS 返回的 WAV 是流式生成的，RIFF 和 data 的长度字段写成了
        占位值（约 2^31），会导致播放器和剪映识别出上百小时的错误时长。
        """
        import struct

        data = path.read_bytes()
        if data[:4] != b"RIFF":
            return

        idx = data.find(b"data")
        if idx < 0:
            return

        buf = bytearray(data)
        struct.pack_into("<I", buf, 4, len(data) - 8)
        struct.pack_into("<I", buf, idx + 4, len(data) - (idx + 8))
        path.write_bytes(bytes(buf))

    def _save_path(
        self,
        filename: str | None,
        default_name: str,
        suffix: str,
        idx: int | None = None,
    ) -> Path:
        """解析保存路径。

        - filename 为 None：在 output_dir 下自动命名；
        - 只传文件名：保存到 output_dir 下；
        - 传完整路径：直接使用；
        - idx 不为 None（多张输出）时自动追加 _序号；
        - 无后缀时补默认后缀。
        """
        if filename is None:
            name = default_name + (f"_{idx}" if idx is not None else "")
            path = self.output_dir / (name + suffix)
        else:
            path = Path(filename)
            if path.parent == Path("."):
                path = self.output_dir / path
            if idx is not None:
                path = path.with_stem(f"{path.stem}_{idx}")
            if path.suffix == "":
                path = path.with_suffix(suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _post(self, payload: dict) -> dict:
        """发送 POST 请求并返回 JSON。"""
        resp = self.session.post(API_URL, json=payload, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"API 调用失败 (HTTP {resp.status_code}): {resp.text}")
        return resp.json()

    def _image_to_input(self, image: str) -> str:
        """将输入图片转换为 API 可接受的字符串。"""
        if image.startswith(("http://", "https://")):
            return image

        if not os.path.isfile(image):
            raise FileNotFoundError(f"输入图片不存在: {image}")

        ext = os.path.splitext(image)[1].lower()
        if ext not in SUPPORTED_IMG_EXTS:
            raise ValueError(f"不支持的图片格式: {ext}")

        with open(image, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{MIME_MAP[ext]};base64,{b64}"

    def _download(self, url: str, path: Path) -> None:
        """下载文件到本地。

        注意：不能用 self.session，否则会带上 Authorization 头，
        导致 OSS 预签名 URL 鉴权失败（403）。
        """
        resp = requests.get(url, stream=True, timeout=self.timeout)
        resp.raise_for_status()
        with open(path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)


if __name__ == "__main__":
    gen = QwenMediaGenerator(output_dir="./output")

    # 示例 1：文生图（竖屏短视频）
    prompt_laolao = (
    "一位65岁左右的中国老年女性卡通角色定妆图。"
    "紫色短卷发，戴圆形细框眼镜，脖子上系一条红色围巾，"
    "身穿米色长风衣，内搭浅色高领毛衣，斜挎一个小包。"
    "面带亲切温和的微笑，站姿自信，半身正面像，角色居中。"
    "扁平矢量插画风格，线条干净，暖色调，色块平涂，柔和光线。"
    "纯浅米色背景，画面干净整洁，不出现任何文字、字母、水印、logo。"
    "手部自然放松，不露手指细节。"
)

    prompt_laoye = (
    "一位68岁左右的中国老年男性卡通角色定妆图。"
    "戴灰色鸭舌帽，身穿蓝色夹克，内搭灰色毛衣，"
    "一副老花镜挂在胸前，手里端着一个银色保温杯。"
    "表情憨厚朴实，微微皱眉、嘴角平，略带疑惑。"
    "站姿放松，半身正面像，角色居中。"
    "扁平矢量插画风格，线条干净，暖色调，色块平涂，柔和光线。"
    "纯浅米色背景，画面干净整洁，不出现任何文字、字母、水印、logo。"
    "手部自然放松，不露手指细节。"
)
    # gen.gen_image(
    #     prompt=prompt_laoye,
    #     size="1024*1024",
    #     filename="./img/laoye.png",
    # )

    # 示例 2：图生图（保持人物形象换场景）
    prompt_cover = (
    "参考图中老年卡通角色，保持与参考图完全一致的外貌特征和写实插画风格。图中老年人拿着手机头向左转，脸部面向左侧，手机放在耳边正在与他人通话。"
)
    gen.gen_image(
        image=["./img/laoye.png"],
        prompt=prompt_cover,
        size="512*512",
        filename="./part1/laoye_1.png",   # 也可传完整路径，如 "./part1/airport.png"
    )

    # 示例 3：TTS 合成
    # gen.gen_tts(text="can you help me?", voice="Jennifer", filename="Jennifer.wav")
