"""
分镜 Agent
调用 LLM 根据小说原文生成结构化分镜 patch
Agent 只能返回 JSON patch, 由服务端校验后应用
"""
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from . import llm


def now():
    return datetime.utcnow().isoformat()


# ============ LLM Prompt 模板 ============
STORYBOARD_SYSTEM = """你是一个专业的小说改编漫剧分镜师.
你的任务是把小说原文切分成若干个 15 秒视频段, 每段包含:
- summary: 剧情摘要 (一句话)
- start_transition: 段首衔接描述
- end_transition: 段尾衔接描述
- characters: 出场角色名列表
- scenes: 涉及场景名列表
- beats: 段内节拍列表, 每个节拍 1-3 秒, 包含:
  - start_ms / end_ms: 起止毫秒
  - shot_size: 景别 (远景/全景/中景/近景/特写)
  - camera_movement: 运镜 (固定/推近/拉远/摇移/跟随)
  - character_action: 角色动作描述
  - scene_change: 场景变化
  - lighting: 光线描述
  - composition: 构图描述
  - emotion: 情绪氛围
  - transition: 与下一节拍的衔接方式 (直切/淡入淡出/叠化)

要求:
1. 每段总时长严格等于 15000 毫秒
2. 节拍不得重叠, 不得有空洞
3. 返回合法 JSON, 不要有任何解释文字
4. 输出格式:
{
  "segments": [
    {
      "summary": "...",
      "start_transition": "...",
      "end_transition": "...",
      "characters": ["角色A"],
      "scenes": ["场景X"],
      "beats": [
        {"start_ms":0, "end_ms":2500, "shot_size":"中景", "camera_movement":"缓慢推近",
         "character_action":"...", "scene_change":"...", "lighting":"...",
         "composition":"...", "emotion":"...", "transition":"直切"}
      ]
    }
  ],
  "characters": [{"name":"...", "description":"...", "appearance_anchor":"...", "costume_anchor":"...", "temperament_anchor":"..."}],
  "scenes": [{"name":"...", "description":"...", "time":"...", "weather":"...", "lighting":"...", "color_tendency":"..."}]
}
"""


def generate_storyboard(source_text: str, target_duration_seconds: int = 180,
                        style_prompt: Optional[str] = None,
                        segment_duration_seconds: int = 15) -> Dict[str, Any]:
    """
    调用 LLM 生成完整分镜 (段 + 节拍 + 角色 + 场景)
    返回结构化 JSON
    """
    n_segments = max(1, target_duration_seconds // segment_duration_seconds)
    user_prompt = f"""请把以下小说原文改编为 {n_segments} 个 {segment_duration_seconds} 秒视频段的漫剧分镜.

全局风格: {style_prompt or '写实漫剧风格'}

小说原文:
{source_text}
"""
    return llm.chat_json(
        [{"role": "system", "content": STORYBOARD_SYSTEM},
         {"role": "user", "content": user_prompt}],
        temperature=0.5,
        max_tokens=8000,
        schema_hint='{"segments":[...],"characters":[...],"scenes":[...]}'
    )


def build_h3_prompt_for_segment(segment: Dict[str, Any],
                                beats: List[Dict[str, Any]],
                                characters: List[Dict[str, Any]],
                                scenes: List[Dict[str, Any]],
                                style_prompt: Optional[str] = None) -> str:
    """调用 LLM 把节拍汇总为 H3 连续 prompt (可选; 也可以用 prompt_builder 规则拼接)"""
    system = """你是专业的视频生成 prompt 工程师.
把分镜节拍汇总成一段连续的 H3 视频生成 prompt.
要求:
- 按时序描述每个节拍的内容
- 包含角色外貌锚点、场景锚点、光线、氛围
- 强调时间连续性和画面一致性
- 返回纯文本 prompt, 不要 JSON, 不要解释"""
    beats_text = "\n".join([
        f"[{b.get('start_ms',0)/1000:.1f}s-{b.get('end_ms',0)/1000:.1f}s] "
        f"{b.get('shot_size','')}, {b.get('camera_movement','')}, "
        f"{b.get('character_action','')}, {b.get('scene_change','')}, "
        f"{b.get('lighting','')}, {b.get('emotion','')}"
        for b in sorted(beats, key=lambda x: x.get("start_ms", 0))
    ])
    chars_text = "; ".join([f"{c.get('name')}: {c.get('appearance_anchor','')}, {c.get('costume_anchor','')}" for c in characters])
    scenes_text = "; ".join([f"{s.get('name')}: {s.get('time','')}, {s.get('lighting','')}, {s.get('color_tendency','')}" for s in scenes])
    user = f"""剧情: {segment.get('summary','')}
风格: {style_prompt or '写实漫剧'}
角色: {chars_text}
场景: {scenes_text}
节拍:
{beats_text}
段首衔接: {segment.get('start_transition','')}
段尾衔接: {segment.get('end_transition','')}
"""
    return llm.chat_text(system, user, temperature=0.4, max_tokens=2000)


# ============ Patch 校验 ============
ALLOWED_PATCH_TYPES = {
    "create_segment", "update_segment", "delete_segment",
    "create_shotbeat", "update_shotbeat", "delete_shotbeat",
    "compress_segment", "rewrite_segment",
    "fill_missing_fields", "build_h3_prompt", "build_keyframe_prompt",
}


def validate_patch(patch: Dict[str, Any]) -> List[str]:
    """校验 patch 结构, 返回错误列表 (空=通过)"""
    errors = []
    if "ops" not in patch:
        errors.append("missing 'ops' field")
        return errors
    if not isinstance(patch["ops"], list):
        errors.append("'ops' must be a list")
        return errors
    for i, op in enumerate(patch["ops"]):
        if "type" not in op:
            errors.append(f"op[{i}] missing 'type'")
            continue
        if op["type"] not in ALLOWED_PATCH_TYPES:
            errors.append(f"op[{i}] unknown type: {op['type']}")
        if "target" not in op and op["type"] not in ("create_segment",):
            errors.append(f"op[{i}] missing 'target'")
    return errors
