"""
资产生成流水线
Image2 生成候选 -> 人工选定 -> 确认入库

- 资产生成统一走 image2 (smmmc gpt-image-2), 不再用 Z-Image 出资产图 (Z-Image 仅段首图关键帧)。
- 画幅: 默认 ASSET_DEFAULT_ASPECT (4:3), 可调; 角色多视角 (view_mode=character_multi) 例外为 16:9 单张三格图。
- 物品 (asset_type=item): 统一类型, 默认单视角; 可上传。
- 角色多视角: image2 单张 16:9 画面内并排/分格呈现「半身特写 / 正面全身 / 背面全身」三视角;
  支持用已确认正面图做 --local-ref reference 衍生 (refs 参数), 提升一致性。
"""
import os
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from . import storage
from .prompt_builder import build_asset_anchor, build_asset_prompt
from . import image2_client
from .config import ASSET_DEFAULT_ASPECT


def now():
    return datetime.utcnow().isoformat()


# 资产类型 -> 存储子目录
ASSET_SUBDIR = {"character": "assets/characters", "scene": "assets/scenes", "item": "assets/items"}


def _subdir_for(asset_type: str) -> str:
    return ASSET_SUBDIR.get(asset_type, "assets/scenes")


def generate_candidates(db, asset_id: str, count: int = 4,
                        prompt_override: Optional[str] = None,
                        size: Optional[str] = None,
                        aspect: Optional[str] = None,
                        view_mode: str = "single",
                        quality: Optional[str] = None,
                        resolution: Optional[str] = None,
                        use_ref: bool = False) -> List[str]:
    """
    调用 image2 为资产生成 count 张候选图。
    返回 candidate_id 列表。

    参数:
    - size: 像素字符串 (如 1536x864) 或 None; 为空时用 aspect 比例 (默认 4:3)。
    - aspect: 比例字符串 (4:3 / 16:9 / 1:1); 角色多视角忽略, 强制 16:9。
    - view_mode: 'single'(默认) / 'character_multi'(角色三格图 16:9)。
    - use_ref: 若 True 且该资产已有选定的候选图 (已确认正面图), 作为 image2 reference 衍生。
    """
    asset = db.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
    if not asset:
        raise ValueError("asset not found")
    asset = dict(asset)
    project_id = asset["project_id"]
    asset_type = asset["asset_type"]

    # 构建 prompt
    if prompt_override:
        prompt = prompt_override
    else:
        prompt = build_asset_prompt(asset, view_mode=view_mode)

    negative = asset.get("negative_prompt") or "低质量, 模糊, 变形"

    # 目标画幅: 角色多视角强制 16:9, 其余用 aspect 或默认
    effective_aspect = aspect or ASSET_DEFAULT_ASPECT
    if view_mode == "character_multi":
        effective_aspect = "16:9"

    # 参考图: use_ref 且已有选定候选图
    refs: Optional[List[bytes]] = None
    if use_ref:
        sel_id = asset.get("selected_candidate_id")
        if sel_id:
            sel_row = db.execute("SELECT * FROM asset_candidates WHERE id=?", (sel_id,)).fetchone()
            if sel_row and sel_row["image_path"]:
                abs_path = storage.get_abs_path(project_id, sel_row["image_path"])
                if os.path.exists(abs_path):
                    with open(abs_path, "rb") as f:
                        refs = [f.read()]

    candidate_ids = []
    for i in range(count):
        img_bytes_list = image2_client.image2_generate(
            prompt, size=size, aspect=effective_aspect, view_mode=view_mode,
            n=1, refs=refs, quality=quality or None, resolution=resolution or None,
        )
        # image2 一次生成可能返回多张 (n>1); 这里在循环内取第一张, 保候选数稳定
        img_bytes = img_bytes_list[0] if img_bytes_list else b""
        if not img_bytes:
            raise ValueError(f"image2 returned no image for asset {asset_id}")
        # 本地像素校验 (无 vision): 读实际像素/通道范围防坏图
        vinfo = image2_client.validate_result_images([img_bytes], size or "auto")
        if vinfo["images"] and vinfo["images"][0].get("problem"):
            raise ValueError(f"image2 output flagged: {vinfo['images'][0]['problem']}")
        fname = f"{uuid.uuid4().hex[:8]}_{i}.png"
        sub = _subdir_for(asset_type)
        abs_path = storage.save_bytes(project_id, sub, fname, img_bytes)
        rel_path = storage.get_rel_path(project_id, abs_path)

        cid = str(uuid.uuid4())
        db.execute(
            "INSERT INTO asset_candidates (id, asset_id, generator, prompt, negative_prompt, image_path, seed, status, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (cid, asset_id, "image2", prompt, negative, rel_path, None, "generated", now())
        )
        candidate_ids.append(cid)
    db.execute("UPDATE assets SET status='generated', updated_at=? WHERE id=?", (now(), asset_id))
    db.commit()
    return candidate_ids


def select_candidate(db, candidate_id: str) -> None:
    """选定某个候选 (不锁定, 可改选)"""
    row = db.execute("SELECT * FROM asset_candidates WHERE id=?", (candidate_id,)).fetchone()
    if not row:
        raise ValueError("candidate not found")
    row = dict(row)
    asset_id = row["asset_id"]
    # 重置同 asset 的其他候选状态
    db.execute("UPDATE asset_candidates SET status='generated' WHERE asset_id=?", (asset_id,))
    db.execute("UPDATE asset_candidates SET status='selected' WHERE id=?", (candidate_id,))
    db.execute("UPDATE assets SET selected_candidate_id=?, status='selected', updated_at=? WHERE id=?",
               (candidate_id, now(), asset_id))
    db.commit()


def confirm_asset(db, asset_id: str) -> None:
    """确认资产入库"""
    db.execute("UPDATE assets SET status='confirmed', updated_at=? WHERE id=?", (now(), asset_id))
    db.commit()


# ============ 角色多视角: 三格图切分工具 ============
# 16:9 三格图为单张 contact sheet, 后续关键帧引用需能切出单视角 (如正面全身格)。
VIEW_ORDER = ["half_body", "front_full", "back_full"]


def split_character_view(image_abs_path: str, view: str = "front_full") -> str:
    """从 16:9 三格图切出单个视角 (左半身 / 中正面全身 / 右背面全身)。
    返回切出子图保存的绝对路径 (与源图同目录, 后缀 _view_{view}.png)。
    用 PIL 按三等分横切 (contact sheet 通常三分水平排列)。

    Args:
        image_abs_path: 三格图绝对路径
        view: VIEW_ORDER 之一 (half_body / front_full / back_full)
    """
    if view not in VIEW_ORDER:
        raise ValueError(f"unknown view: {view}")
    from PIL import Image
    img = Image.open(image_abs_path)
    w, h = img.size
    col = VIEW_ORDER.index(view)
    left = round(w * col / 3)
    right = round(w * (col + 1) / 3)
    crop = img.crop((left, 0, right, h))
    base, _ = os.path.splitext(image_abs_path)
    out_path = f"{base}_view_{view}.png"
    crop.save(out_path, "PNG")
    return out_path


def ensure_asset_from_storyboard(db, project_id: str, asset_type: str, data: Dict[str, Any]) -> Optional[str]:
    """
    根据 LLM 分镜返回的 character/scene/item dict 创建资产（幂等：同名同类型已存在则复用）。
    返回 asset_id；name 为空/未提供时返回 None。
    """
    name = (data.get("name") or "").strip()
    if not name:
        return None
    existing = db.execute(
        "SELECT id FROM assets WHERE project_id=? AND asset_type=? AND name=?",
        (project_id, asset_type, name)).fetchone()
    if existing:
        return existing["id"]
    aid = str(uuid.uuid4())
    ts = now()
    db.execute(
        "INSERT INTO assets (id,project_id,asset_type,name,description,appearance_anchor,costume_anchor,"
        "temperament_anchor,time,weather,lighting,color_tendency,negative_prompt,status,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (aid, project_id, asset_type, name,
         data.get("description", ""), data.get("appearance_anchor", ""),
         data.get("costume_anchor", ""), data.get("temperament_anchor", ""),
         data.get("time", ""), data.get("weather", ""), data.get("lighting", ""),
         data.get("color_tendency", ""), data.get("negative_prompt", ""),
         "draft", ts, ts))
    return aid
