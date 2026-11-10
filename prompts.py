"""全系列共用的风格与主角设定提示词。"""

STYLE_PROMPT = (
    "扁平插画风格（flat vector illustration），现代治愈系绘本质感。"
    "深棕色柔和粗描边，线宽统一，不使用纯黑描边；"
    "低饱和暖色板（米白、暖黄、砖红、墨绿、灰蓝），不使用高饱和荧光色；"
    "扁平色块加少量柔和渐变，不使用写实光影和复杂阴影；"
    "背景为简化的室内或室外环境（墙面、地面、必要的家具与道具），"
    "不绘制繁杂细节，但不要出现大片纯白空白背景。"
)

COMPOSITION_PROMPT = (
    "构图要求：人物必须占满画面高度的 80% 以上，全身完整入画，"
    "头顶距画面上边缘不超过画面高度的 8%，脚底或腿部底端贴近画面下边缘；"
    "绝对不要出现人物过小、只占画面中间一小块的情况；"
    "不要裁掉腿部或脚，不要在人物周围留出大面积空白。"
    "参考图只用于保持人物长相与服装配色，构图必须按本场景描述重新安排，"
    "不要照搬参考图中的留白比例。"
)

CHARACTER_PROMPT = (
    "固定主角：中国老奶奶，68岁左右，银灰色蓬松短卷发，圆框细边眼镜，"
    "温暖偏黄的肤色，圆脸，体态微胖，面容和蔼，眼神温和有神。"
    "固定装束：米白色长款风衣、酒红色围巾、棕色斜挎小包、深灰色长裤、黑色平底鞋。"
    "酒红色围巾是标志性元素，必须始终出现。"
)

YOUNG_WOMAN_PROMPT = (
    "固定主角：中国年轻女性，26岁左右，鹅蛋脸，杏眼，笑容阳光自然，"
    "乌黑齐肩短发，发尾微卷，肤色白皙，身材匀称。"
    "固定装束：暖黄色针织开衫、白色圆领T恤、浅蓝色直筒牛仔裤、小白鞋、米白色帆布单肩包。"
    "暖黄色针织开衫是标志性元素，必须始终出现。"
)

NO_TEXT = "画面中不要出现任何文字、字幕或水印。"

CHARACTER_PROMPTS = {
    "elder_woman": CHARACTER_PROMPT,
    "young_woman": YOUNG_WOMAN_PROMPT,
}

WAITER_PROMPT = (
    "固定配角：国外餐厅男服务员，28岁左右，深棕色短发，浓眉，高鼻梁，白人肤色，"
    "身材高瘦。固定装束：白色长袖衬衫（袖口挽起）、黑色长围裙、黑色长裤、黑色皮鞋。"
    "黑色长围裙是标志性元素，任何画面都必须出现，不要更换为马甲或其他服装。"
)

SUPPORTING_PROMPTS = {
    "waiter": WAITER_PROMPT,
}

DEFAULT_SIZE = "1080*1920"


def build_scene_prompt(
    scene: str, character: str = CHARACTER_PROMPT, supporting: str = ""
) -> str:
    """场景图专用：场景描述放在最前，避免参考图权重压过场景要求。"""
    parts = [f"场景画面：{scene}", STYLE_PROMPT, character]
    if supporting:
        parts.append(supporting)
    parts.append(COMPOSITION_PROMPT)
    parts.append(NO_TEXT)
    return "\n".join(parts)
