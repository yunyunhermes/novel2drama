"""
Prompt 构建器
把项目/段/节拍/资产 汇总成 Z-Image 段首图 prompt 和 H3 连续 prompt
"""
from typing import List, Dict, Any, Optional


def build_asset_anchor(asset: Dict[str, Any]) -> str:
    """从资产记录提取锚点描述"""
    parts = []
    if asset.get("asset_type") == "character":
        if asset.get("appearance_anchor"):
            parts.append(asset["appearance_anchor"])
        if asset.get("costume_anchor"):
            parts.append(asset["costume_anchor"])
        if asset.get("temperament_anchor"):
            parts.append(asset["temperament_anchor"])
    elif asset.get("asset_type") == "scene":
        if asset.get("time"):
            parts.append(asset["time"])
        if asset.get("weather"):
            parts.append(asset["weather"])
        if asset.get("lighting"):
            parts.append(asset["lighting"])
        if asset.get("color_tendency"):
            parts.append(asset["color_tendency"])
    return ", ".join(parts)


def build_keyframe_prompt(segment: Dict[str, Any],
                          characters: List[Dict[str, Any]],
                          scenes: List[Dict[str, Any]],
                          style_prompt: Optional[str] = None,
                          first_beat: Optional[Dict[str, Any]] = None) -> str:
    """构建 Z-Image 段首图 prompt"""
    parts = []
    if style_prompt:
        parts.append(style_prompt)
    # 段摘要
    if segment.get("summary"):
        parts.append(segment["summary"])
    # 角色锚点
    for c in characters:
        anchor = build_asset_anchor(c)
        if anchor:
            parts.append(f"角色 {c.get('name','')}: {anchor}")
    # 场景锚点
    for s in scenes:
        anchor = build_asset_anchor(s)
        if anchor:
            parts.append(f"场景 {s.get('name','')}: {anchor}")
    # 段首节拍补充 (景别/构图/光线)
    if first_beat:
        for k in ("shot_size", "composition", "lighting", "style", "emotion"):
            v = first_beat.get(k)
            if v:
                parts.append(v)
    return ", ".join(p for p in parts if p)


def build_h3_prompt(segment: Dict[str, Any],
                    beats: List[Dict[str, Any]],
                    characters: List[Dict[str, Any]],
                    scenes: List[Dict[str, Any]],
                    style_prompt: Optional[str] = None) -> str:
    """构建 H3 15秒连续 prompt (按时序节拍展开)"""
    parts = []
    if style_prompt:
        parts.append(style_prompt)
    if segment.get("summary"):
        parts.append(f"剧情: {segment['summary']}")
    # 角色锚点
    for c in characters:
        anchor = build_asset_anchor(c)
        if anchor:
            parts.append(f"角色 {c.get('name','')}: {anchor}")
    # 场景锚点
    for s in scenes:
        anchor = build_asset_anchor(s)
        if anchor:
            parts.append(f"场景 {s.get('name','')}: {anchor}")
    # 节拍序列
    if beats:
        parts.append("镜头节奏:")
        sorted_beats = sorted(beats, key=lambda b: b.get("start_ms", 0))
        for i, b in enumerate(sorted_beats, 1):
            start_s = b.get("start_ms", 0) / 1000.0
            end_s = b.get("end_ms", 0) / 1000.0
            beat_desc = []
            for k in ("shot_size", "camera_movement", "character_action",
                      "scene_change", "lighting", "emotion", "transition"):
                v = b.get(k)
                if v:
                    beat_desc.append(v)
            parts.append(f"{i}. [{start_s:.1f}s-{end_s:.1f}s] " + ", ".join(beat_desc))
    # 段首/段尾衔接
    if segment.get("start_transition"):
        parts.append(f"段首衔接: {segment['start_transition']}")
    if segment.get("end_transition"):
        parts.append(f"段尾衔接: {segment['end_transition']}")
    return "\n".join(parts)


def build_negative_prompt(segment: Optional[Dict[str, Any]] = None,
                          characters: Optional[List[Dict[str, Any]]] = None,
                          scenes: Optional[List[Dict[str, Any]]] = None) -> str:
    """汇总负面 prompt"""
    parts = []
    if segment and segment.get("negative_prompt"):
        parts.append(segment["negative_prompt"])
    for c in (characters or []):
        if c.get("negative_prompt"):
            parts.append(c["negative_prompt"])
    for s in (scenes or []):
        if s.get("negative_prompt"):
            parts.append(s["negative_prompt"])
    # 默认通用负面
    parts.append("低质量, 模糊, 变形, 多余手指, 多余肢体, 崩坏, 噪点")
    return ", ".join(dict.fromkeys(parts))  # 去重保序
