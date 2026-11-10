"""生成固定主角形象模板（后期所有场景沿用）。

风格：温暖扁平插画风
流程：先生成标准正面半身像，再以它为参考图生成其余视图，保证一致性。

用法：
    python gen_character.py              # 老奶奶（默认）
    python gen_character.py young_woman  # 年轻中国女性
"""

import sys

from media_generator import QwenMediaGenerator
from prompts import (
    CHARACTER_PROMPT,
    NO_TEXT,
    STYLE_PROMPT,
    YOUNG_WOMAN_PROMPT,
    build_scene_prompt,
)

CHARACTERS = {
    "elder_woman": {
        "prompt": CHARACTER_PROMPT,
        "dir": "./img/template",
        "label": "老奶奶",
        "scene": (
            "机场问询柜台。画面中必须有两个人："
            "主角老奶奶站在柜台前，手里拿着登机牌，表情困惑地看向柜台内；"
            "柜台内站着一位穿深蓝色制服的年轻女性机场工作人员，正微笑看向主角。"
        ),
    },
    "young_woman": {
        "prompt": YOUNG_WOMAN_PROMPT,
        "dir": "./img/template_young",
        "label": "年轻女性",
        "scene": (
            "机场问询柜台。画面中必须有两个人："
            "主角年轻女性站在柜台前，手里拿着登机牌，表情礼貌地向柜台内询问；"
            "柜台内站着一位穿深蓝色制服的机场女工作人员，正抬手为她指路。"
        ),
    },
}


def build_prompt(scene: str, character: str = CHARACTER_PROMPT) -> str:
    return f"{STYLE_PROMPT}\n{character}\n{scene}\n{NO_TEXT}"


def gen_scene(gen: QwenMediaGenerator, main_img: str, cfg: dict) -> str:
    prompt = build_scene_prompt(
        cfg["scene"]
        + "必须画出柜台（带台面）和一块机场指示牌，其余环境保持米白留白。"
        "竖屏构图，人物居中偏下，画面上方留出约 25% 空白用于后期叠加台词气泡。",
        cfg["prompt"],
    )
    path = gen.gen_image(
        prompt=prompt,
        image=main_img,
        size="720*1280",
        prompt_extend=True,
        filename="05_场景示例_机场问询.png",
    )[0]
    print("生成完成:", path)
    return path


def main(key: str = "elder_woman"):
    cfg = CHARACTERS[key]
    ch = cfg["prompt"]
    gen = QwenMediaGenerator(output_dir=cfg["dir"])

    print(f"开始生成 {cfg['label']} 模板 → {cfg['dir']}\n")

    # 1. 标准正面半身像：作为全系列的形象基准
    main_img = gen.gen_image(
        prompt=build_prompt(
            "画一张主角正面半身肖像。人物正面朝向镜头，微微微笑，双手自然交叠在身前，"
            "人物占满画面高度的 85%，全身完整入画，脚底贴近画面下边缘。"
            "人物比例准确，五官简化：圆点眼睛、弧线嘴巴，表情亲切友善。",
            ch,
        ),
        size="720*1280",
        prompt_extend=False,
        filename="01_主角正面半身像.png",
    )[0]
    print("生成完成:", main_img)

    # 2. 全身站姿：用于场景图的人物参考
    full_img = gen.gen_image(
        prompt=build_prompt(
            "画主角的全身站立姿势。人物正面站立，双脚并拢，双手自然下垂，"
            "背好斜挎包，面带微笑看向镜头，人物占满画面高度的 85%，"
            "全身完整入画，脚底贴近画面下边缘。",
            ch,
        ),
        image=main_img,
        size="720*1280",
        prompt_extend=False,
        filename="02_主角全身站姿.png",
    )[0]
    print("生成完成:", full_img)

    # 3. 角色三视图：用于保证不同角度下人物不走形
    turnaround = gen.gen_image(
        prompt=build_prompt(
            "画一张角色设定三视图：同一人物并排展示正面、四分之三侧面、背面三个视角，"
            "三个人物身高一致、服装配色完全一致，站立姿态统一，"
            "背景纯米白，构图整齐。",
            ch,
        ),
        image=full_img,
        size="1024*1024",
        prompt_extend=False,
        filename="03_主角三视图.png",
    )[0]
    print("生成完成:", turnaround)

    # 4. 表情参考表：供后期挑选情绪
    expressions = gen.gen_image(
        prompt=build_prompt(
            "画一张同一人物的表情参考图，2x2 四宫格排列："
            "左上微笑、右上困惑皱眉、左下惊讶睁大眼、右下开心大笑。"
            "四格中人物的发型、服装完全一致，仅是表情变化，"
            "每格为胸部以上特写，背景纯米白。",
            ch,
        ),
        image=main_img,
        size="1024*1024",
        prompt_extend=False,
        filename="04_主角表情表.png",
    )[0]
    print("生成完成:", expressions)

    # 5. 场景应用示例：验证主角形象在具体场景中是否稳定
    gen_scene(gen, main_img, cfg)

    print("\n全部模板已生成，目录:", cfg["dir"])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "elder_woman")
